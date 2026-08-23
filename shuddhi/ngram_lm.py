"""Perplexity-proxy quality scoring — character-trigram language models.

The v1 heuristics screen junk; they cannot rank prose. This stage adds a
real (if small) statistical signal without new dependencies: a per-language
character-trigram LM with add-k smoothing, trained on a deterministic sample
of the shard itself, scoring documents in bits/char. Documents far above the
language's typical bits/char are gibberish, foreign-script noise, or byte
salad; far below are degenerate repetition. It is a *proxy*: a 3-gram char
model knows spelling and script, not meaning — reports must (and do) label
it as such.

Self-training on the shard is intentional: the model represents "what this
corpus typically looks like", so the score is a within-corpus outlier
measure, not an external judgement. Deterministic: fixed sampling stride,
fixed smoothing, sorted serialization.

Model files are gzipped JSON: {"k": add_k, "contexts": {"ab": {"c": n}}}.
Context table is capped to the most frequent contexts to bound size; unseen
contexts back off to the global character unigram distribution.
"""

from __future__ import annotations

import gzip
import json
import math
from collections import Counter

MAX_CONTEXTS = 100_000
MAX_CHARS_PER_CONTEXT = 64
# 512 chars is ample for the junk-vs-prose separation this proxy exists for
# (bits/char converges within a few hundred chars) and it is the dominant
# per-document cost in applied builds — measured 2026-08-10: a 2000-char
# probe put full-corpus builds at ~2.65 ms/doc, ~19 h for 33M docs.
SCORE_PROBE_CHARS = 512
ADD_K = 0.1


class CharTrigramLM:
    def __init__(self, contexts: dict[str, dict[str, int]], unigrams: dict[str, int], k: float = ADD_K):
        self._ctx = contexts
        self._ctx_totals = {c: sum(d.values()) for c, d in contexts.items()}
        self._uni = unigrams
        self._uni_total = sum(unigrams.values()) or 1
        self._vocab = max(len(unigrams), 2)
        self._k = k

    # -- training -----------------------------------------------------------
    @classmethod
    def train(cls, texts, k: float = ADD_K) -> "CharTrigramLM":
        ctx_counts: dict[str, Counter] = {}
        uni: Counter = Counter()
        for text in texts:
            t = " " + text.strip() + " "
            uni.update(t)
            for i in range(len(t) - 2):
                ctx = t[i : i + 2]
                nxt = t[i + 2]
                bucket = ctx_counts.get(ctx)
                if bucket is None:
                    bucket = ctx_counts[ctx] = Counter()
                bucket[nxt] += 1

        # cap for size: most frequent contexts, most frequent continuations
        kept_ctx = sorted(ctx_counts, key=lambda c: -sum(ctx_counts[c].values()))[:MAX_CONTEXTS]
        contexts = {
            c: dict(ctx_counts[c].most_common(MAX_CHARS_PER_CONTEXT)) for c in sorted(kept_ctx)
        }
        return cls(contexts, dict(uni), k)

    # -- scoring ------------------------------------------------------------
    def bits_per_char(self, text: str) -> float | None:
        """Mean -log2 p(char | prev 2 chars) over the probe. None for texts
        too short to score."""
        t = " " + text[:SCORE_PROBE_CHARS].strip() + " "
        if len(t) < 12:
            return None
        k, v = self._k, self._vocab
        bits = 0.0
        n = 0
        ctx_map = self._ctx
        totals = self._ctx_totals
        for i in range(len(t) - 2):
            ctx = t[i : i + 2]
            nxt = t[i + 2]
            bucket = ctx_map.get(ctx)
            if bucket is not None:
                p = (bucket.get(nxt, 0) + k) / (totals[ctx] + k * v)
            else:
                p = (self._uni.get(nxt, 0) + k) / (self._uni_total + k * v)
            bits -= math.log2(p)
            n += 1
        return bits / n if n else None

    # -- serialization ------------------------------------------------------
    def save(self, path: str) -> None:
        doc = {"k": self._k, "contexts": self._ctx, "unigrams": self._uni}
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, sort_keys=True)

    @classmethod
    def load(cls, path: str) -> "CharTrigramLM":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            doc = json.load(f)
        return cls(doc["contexts"], doc["unigrams"], doc.get("k", ADD_K))
