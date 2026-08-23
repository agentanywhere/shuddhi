"""Contamination check — stage 6. Protects benchmark integrity.

Screens corpus documents against our evaluation material (reliability-ab
battery prompts, honesty-trap prompts, and the eval fixture sources — see
build_eval_set.py). Two detectors:

  exact:   normalized full text of an eval item appearing as (or inside) a doc
  near:    any 8-word shingle of an eval item appearing in a doc

Matching is two-stage so it is both fast and false-positive-free: a CRC32
prefilter (cheap, C-speed) followed by exact string comparison of the
candidate gram against the eval gram it collided with. Every reported hit is
therefore a literal string match after normalization, never a hash accident.
"""

from __future__ import annotations

import json
import re

GRAM_WORDS = 8
DOC_PROBE_WORDS = 4000  # grams checked per doc (bounded cost per document)

_NORM = re.compile(r"\W+", re.UNICODE)


def normalize_words(text: str) -> list[str]:
    return [w for w in _NORM.split(text.lower()) if w]


def _crc(s: str) -> int:
    import zlib

    return zlib.crc32(s.encode("utf-8"))


class EvalSetIndex:
    """N-gram index over the eval set, loaded from eval-set.jsonl."""

    def __init__(self, items: list[dict]):
        self.n_items = len(items)
        self._gram_crc_to_grams: dict[int, dict[str, str]] = {}
        self._full_text: dict[str, str] = {}
        self._vocab: set[str] = set()  # every word occurring in any eval gram
        self.n_grams = 0
        for item in items:
            words = normalize_words(item["text"])
            norm = " ".join(words)
            if norm:
                self._full_text.setdefault(norm, item["id"])
            if len(words) < GRAM_WORDS:
                grams = [norm] if norm else []
            else:
                grams = [
                    " ".join(words[i : i + GRAM_WORDS])
                    for i in range(len(words) - GRAM_WORDS + 1)
                ]
            for g in grams:
                self._gram_crc_to_grams.setdefault(_crc(g), {})[g] = item["id"]
                self.n_grams += 1
            self._vocab.update(words)

    @classmethod
    def load(cls, path: str) -> "EvalSetIndex":
        items = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return cls(items)

    def check_doc(self, text: str) -> list[dict]:
        """Return verified contamination hits for one document."""
        words = normalize_words(text[: DOC_PROBE_WORDS * 12])[:DOC_PROBE_WORDS]
        if not words:
            return []
        hits: list[dict] = []
        seen_items: set[str] = set()

        norm = " ".join(words)
        for full, item_id in self._full_text.items():
            if len(full) >= 40 and full in norm and item_id not in seen_items:
                seen_items.add(item_id)
                hits.append({"eval_id": item_id, "kind": "exact"})

        if len(words) >= GRAM_WORDS:
            index = self._gram_crc_to_grams
            vocab = self._vocab
            for i in range(len(words) - GRAM_WORDS + 1):
                # Vocab prefilter with early exit: a gram can only match if all
                # 8 of its words occur somewhere in the eval set. This makes
                # the common case (any out-of-vocab word) a few set lookups,
                # so Indic documents cost ~nothing here.
                window = words[i : i + GRAM_WORDS]
                if any(w not in vocab for w in window):
                    continue
                gram = " ".join(window)
                cand = index.get(_crc(gram))
                if cand is None:
                    continue
                item_id = cand.get(gram)  # exact-string verification
                if item_id is not None and item_id not in seen_items:
                    seen_items.add(item_id)
                    hits.append({"eval_id": item_id, "kind": "near", "gram": gram})
        return hits
