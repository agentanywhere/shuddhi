"""Filter plugin API — third-party and commercial filters, without a fork.

Shuddhi's built-in filters cover corpus hygiene. Everything beyond that —
domain-specific policy, model-based classifiers, regulatory redaction — is
somebody's specialised problem, and specialised problems do not belong in a
general engine. This module is the seam: any installed Python package can
contribute a filter that the build applies as if it were built in.

## The contract

A plugin is an object with:

    name      str   stable identifier, e.g. "acme-medical-phi"
    version   str   its own version, e.g. "1.4.0"
    identity()      -> dict   everything that changes its verdicts
    check(text)     -> str | None   a drop reason, or None to keep

`identity()` is the load-bearing method. Whatever it returns is folded into
the build's `filter_config_sha256`, which is recorded beside
`filtered_build_hash`. **A plugin that changes its behaviour without
changing its identity breaks the receipt** — the build manifest would then
claim a selection process that cannot account for the documents selected,
and a reviewer re-running your build would silently get a different corpus.
Include model file shas, thresholds, rule-pack versions: anything a reviewer
would need to reproduce your verdicts.

## Registering

Declare an entry point in the plugin package's pyproject.toml:

    [project.entry-points."shuddhi.filters"]
    acme-medical-phi = "acme_shuddhi:PhiFilter"

Then enable it per build:

    shuddhi build ... --plugin acme-medical-phi

Plugins are opt-in. Installing a package never silently changes what a build
keeps — you must name it on the command line, and once you do, its identity
is in the hash.

## Ordering

Plugins run after every built-in filter and before the PII policy, in the
order named on the command line. Their drops are counted separately, under
`plugin:<name>`, so a manifest always shows which filter removed what.

A worked example lives in `examples/plugin/`.
"""

from __future__ import annotations

import importlib.metadata as md
from typing import Protocol, runtime_checkable

ENTRY_POINT_GROUP = "shuddhi.filters"


@runtime_checkable
class FilterPlugin(Protocol):
    name: str
    version: str

    def identity(self) -> dict:
        """Everything that affects this filter's verdicts. Enters the build's
        filter_config_sha256."""

    def check(self, text: str) -> str | None:
        """Return a short drop reason, or None to keep the document."""


def available() -> dict[str, md.EntryPoint]:
    """All registered plugins, by name, from installed packages."""
    try:
        eps = md.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # importlib.metadata < 3.10 API
        eps = md.entry_points().get(ENTRY_POINT_GROUP, [])
    return {ep.name: ep for ep in eps}


def load(names: list[str]) -> list[FilterPlugin]:
    """Instantiate the named plugins, in the order given.

    Raises rather than skipping: a build that silently ignored a filter the
    operator asked for would produce a manifest that misrepresents itself.
    """
    found = available()
    missing = [n for n in names if n not in found]
    if missing:
        raise RuntimeError(
            f"filter plugin(s) not installed: {missing}. "
            f"Available: {sorted(found) or 'none'}. "
            f"Plugins register under the '{ENTRY_POINT_GROUP}' entry-point group."
        )
    loaded = []
    for n in names:
        obj = found[n].load()
        inst = obj() if isinstance(obj, type) else obj
        for attr in ("name", "version", "identity", "check"):
            if not hasattr(inst, attr):
                raise RuntimeError(
                    f"plugin '{n}' does not satisfy the FilterPlugin contract: "
                    f"missing '{attr}' (see plugins.py)"
                )
        if inst.name != n:
            raise RuntimeError(
                f"plugin entry point '{n}' reports name '{inst.name}' — these must "
                "match, because the name is what appears in the build manifest"
            )
        loaded.append(inst)
    return loaded


def identities(plugins: list[FilterPlugin]) -> list[dict]:
    """Receipt-bearing identities, in application order."""
    return [
        {"name": p.name, "version": p.version, "identity": p.identity()}
        for p in plugins
    ]
