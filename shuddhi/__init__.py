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

__version__ = "1.2.0"

__all__ = ["__version__"]
