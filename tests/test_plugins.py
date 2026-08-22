"""The filter-plugin seam: third-party filters without a fork, and — the
part that matters — plugin behaviour that cannot escape the receipt."""

import json

import pytest

import plugins
from builder import FilterConfig


class Stub:
    name = "stub"
    version = "0.1.0"

    def __init__(self, min_words=5):
        self.min_words = min_words

    def identity(self):
        return {"min_words": self.min_words}

    def check(self, text):
        return "too short" if len(text.split()) < self.min_words else None


def test_identity_enters_the_config_sha():
    bare = FilterConfig()
    withp = FilterConfig(plugin_identities=plugins.identities([Stub()]))
    assert bare.sha256() != withp.sha256()


def test_changing_plugin_config_changes_the_sha():
    """A plugin that changes verdicts MUST change the build's identity —
    otherwise two different corpora could claim the same hash."""
    a = FilterConfig(plugin_identities=plugins.identities([Stub(min_words=5)]))
    b = FilterConfig(plugin_identities=plugins.identities([Stub(min_words=50)]))
    assert a.sha256() != b.sha256()


def test_plugin_version_enters_the_sha():
    class Newer(Stub):
        version = "0.2.0"

    a = FilterConfig(plugin_identities=plugins.identities([Stub()]))
    b = FilterConfig(plugin_identities=plugins.identities([Newer()]))
    assert a.sha256() != b.sha256()


def test_order_is_part_of_identity():
    class Other(Stub):
        name = "other"

    a = FilterConfig(plugin_identities=plugins.identities([Stub(), Other()]))
    b = FilterConfig(plugin_identities=plugins.identities([Other(), Stub()]))
    assert a.sha256() != b.sha256()


def test_identities_shape():
    ids = plugins.identities([Stub()])
    assert ids == [{"name": "stub", "version": "0.1.0", "identity": {"min_words": 5}}]
    json.dumps(ids)  # must be serialisable into the manifest


def test_missing_plugin_raises_rather_than_skipping():
    """Silently ignoring a filter the operator asked for would produce a
    manifest that misrepresents the build."""
    with pytest.raises(RuntimeError, match="not installed"):
        plugins.load(["definitely-not-installed"])


def test_contract_is_enforced(monkeypatch):
    class Incomplete:
        name = "incomplete"
        version = "1.0"
        # no identity(), no check()

    class FakeEP:
        name = "incomplete"

        def load(self):
            return Incomplete

    monkeypatch.setattr(plugins, "available", lambda: {"incomplete": FakeEP()})
    with pytest.raises(RuntimeError, match="does not satisfy the FilterPlugin contract"):
        plugins.load(["incomplete"])


def test_name_mismatch_is_rejected(monkeypatch):
    class Mismatch(Stub):
        name = "something-else"

    class FakeEP:
        name = "registered-as"

        def load(self):
            return Mismatch

    monkeypatch.setattr(plugins, "available", lambda: {"registered-as": FakeEP()})
    with pytest.raises(RuntimeError, match="must\\s+match"):
        plugins.load(["registered-as"])


def test_build_applies_plugin_and_counts_it_separately(tmp_path):
    import factory

    # distinct documents — identical ones would be dropped as exact
    # duplicates before the plugin ever sees them
    docs = [f"document number {i} " + "word " * 80 for i in range(4)]
    docs.append("tiny doc here")
    shard = tmp_path / "s.txt"
    shard.write_text("\n\n".join(docs) + "\n\n", encoding="utf-8")
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "plug",
        "shards": [{"shard_id": "s", "path": str(shard), "source": "fixture",
                    "license": "CC0-1.0", "date_acquired": "2026-08-13",
                    "data_class": "synthetic-own", "language": "eng"}],
    }))
    run = tmp_path / "run"
    assert factory.main(["run", "--registry", str(reg), "--shard", "s",
                         "--out", str(run), "--sample-every", "1"]) == 0
    assert factory.main(["merge", "--registry", str(reg), "--out", str(run)]) == 0

    from builder import FilterConfig, HashSetIndex, build_shard
    import registry as registry_mod

    _meta, accepted, _ = registry_mod.load_registry(str(reg))
    idx = HashSetIndex.from_run_dir(str(run), ["s"])
    stub = Stub(min_words=20)
    cfg = FilterConfig(min_quality=0.0,
                       plugin_identities=plugins.identities([stub]))
    r = build_shard(accepted[0], idx, cfg, plugins=[stub])
    assert r["dropped"]["plugin:stub"] == 1      # the short document
    assert r["kept_docs"] == 4
    assert "plugin:stub" in r["dropped"]          # counted under its own name
