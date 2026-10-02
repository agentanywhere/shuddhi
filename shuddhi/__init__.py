"""Shuddhi — a receipts-first data factory for training corpora.

Turns raw text into a filtered corpus *with a verifiable identity*: every
document is content-hashed, every shard carries provenance, every filter
threshold is pinned, and the whole build collapses into one hash that a
training run cites in its ledger.

    python -m shuddhi --help        # from a clone, no install needed
    shuddhi --help                  # after pip install

Programmatic use:

    from shuddhi import registry, builder
    meta, accepted, refused = registry.load_registry("registry.json")
"""

# A ".devN" suffix means unreleased code: receipts it writes say so, and are
# never mistaken for the last release's. Releasing = drop the suffix here and
# in pyproject.toml, date the CHANGELOG section, tag vX.Y.Z.
__version__ = "1.3.0"

__all__ = ["__version__"]
