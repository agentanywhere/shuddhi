"""A worked example of a Shuddhi filter plugin.

Deliberately trivial — it drops documents with fewer than N words — so that
the *mechanics* are the lesson rather than the filtering logic:

  * the four members Shuddhi requires (name, version, identity, check)
  * why identity() must contain every knob that changes a verdict
  * that a plugin is an ordinary installable package, not a fork

Install and use:

    pip install -e examples/plugin
    python3 factory.py plugins
    python3 factory.py build ... --plugin example-min-words
"""

from __future__ import annotations

import os


class MinWordsFilter:
    name = "example-min-words"
    version = "1.0.0"

    def __init__(self, min_words: int | None = None):
        # Configured from the environment so the example stays dependency-free.
        # A real plugin would read a config file, a rule pack, or a model.
        self.min_words = int(min_words or os.environ.get("EXAMPLE_MIN_WORDS", 25))

    def identity(self) -> dict:
        """Everything that changes this filter's verdicts.

        This is the contract that keeps receipts honest: it is folded into the
        build's filter_config_sha256, so changing min_words changes the hash.
        A plugin whose behaviour can drift without its identity changing would
        let two different corpora claim the same build hash — which is the one
        thing Shuddhi exists to prevent. Put model file shas and rule-pack
        versions here.
        """
        return {"min_words": self.min_words}

    def check(self, text: str) -> str | None:
        """Return a drop reason, or None to keep."""
        if len(text.split()) < self.min_words:
            return f"fewer than {self.min_words} words"
        return None
