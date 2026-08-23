"""Deduplication — stage 3.

Exact dedup: every document's 64-bit content hash (shards.doc_hash64) is
collected during the full streaming pass; per-shard and global unique counts
come from numpy set operations over those arrays. This runs over the FULL
corpus, not a sample.

Near-dup: MinHash signatures over 5-word shingles with LSH banding, computed
on sampled documents (cost scales with sample size, and the report labels the
coverage). A candidate pair from LSH is only counted after signature
verification, so the reported rate is an estimated-Jaccard threshold rate,
not a raw bucket-collision rate.

Everything is deterministic: permutation constants come from a fixed seed,
shingle hashing is CRC32 (stable across runs and machines).
"""

from __future__ import annotations

import re
import zlib
from array import array

import numpy as np

_WORD_SPLIT = re.compile(r"\s+")

NUM_PERM = 32
LSH_BANDS = 8
LSH_ROWS = NUM_PERM // LSH_BANDS  # 4
SHINGLE_WORDS = 5
MAX_SHINGLE_WORDS = 300
# Fraction of signature rows that must agree for a verified near-dup pair.
# 21/32 ≈ 0.656 estimated Jaccard.
VERIFY_MIN_AGREE = 21

_MERSENNE = (1 << 61) - 1
_rng = np.random.RandomState(7)
_A = _rng.randint(1, _MERSENNE, size=NUM_PERM, dtype=np.uint64)
_B = _rng.randint(0, _MERSENNE, size=NUM_PERM, dtype=np.uint64)


def shingle_hashes(text: str) -> np.ndarray | None:
    """CRC32 hashes of 5-word shingles over the first 300 words (lowercased).
    Returns None when the document is too short to shingle."""
    words = _WORD_SPLIT.split(text.lower().strip())[:MAX_SHINGLE_WORDS]
    if len(words) < SHINGLE_WORDS:
        return None
    grams = (
        " ".join(words[i : i + SHINGLE_WORDS])
        for i in range(len(words) - SHINGLE_WORDS + 1)
    )
    return np.fromiter(
        (zlib.crc32(g.encode("utf-8")) for g in grams), dtype=np.uint64
    )


def minhash_signature(shingles: np.ndarray) -> np.ndarray:
    """(NUM_PERM,) uint64 MinHash signature via universal hashing."""
    # (perm, shingle) matrix of permuted values; min over shingles.
    permuted = (_A[:, None] * shingles[None, :] + _B[:, None]) % _MERSENNE
    return permuted.min(axis=1)


class NearDupIndex:
    """LSH-banded MinHash index for one shard's sampled documents."""

    def __init__(self):
        self._sigs: list[np.ndarray] = []
        self._buckets: list[dict[bytes, int]] = [dict() for _ in range(LSH_BANDS)]
        # union-find parent per inserted doc
        self._parent = array("i")
        self.too_short = 0

    def _find(self, i: int) -> int:
        while self._parent[i] != i:
            self._parent[i] = self._parent[self._parent[i]]
            i = self._parent[i]
        return i

    def _union(self, i: int, j: int) -> None:
        ri, rj = self._find(i), self._find(j)
        if ri != rj:
            self._parent[max(ri, rj)] = min(ri, rj)

    def add(self, text: str) -> None:
        sh = shingle_hashes(text)
        if sh is None:
            self.too_short += 1
            return
        sig = minhash_signature(sh)
        idx = len(self._sigs)
        self._sigs.append(sig)
        self._parent.append(idx)
        for band in range(LSH_BANDS):
            key = sig[band * LSH_ROWS : (band + 1) * LSH_ROWS].tobytes()
            bucket = self._buckets[band]
            other = bucket.get(key)
            if other is None:
                bucket[key] = idx
            else:
                # verify against the bucket representative before uniting
                agree = int((self._sigs[other] == sig).sum())
                if agree >= VERIFY_MIN_AGREE:
                    self._union(other, idx)

    def summary(self) -> dict:
        n = len(self._sigs)
        clusters: dict[int, int] = {}
        for i in range(n):
            root = self._find(i)
            clusters[root] = clusters.get(root, 0) + 1
        n_clusters = len(clusters)
        near_dup_docs = n - n_clusters  # members beyond each cluster exemplar
        return {
            "minhashed_docs": n,
            "too_short_to_shingle": self.too_short,
            "clusters": n_clusters,
            "near_dup_docs": near_dup_docs,
            "near_dup_rate": near_dup_docs / n if n else 0.0,
            "largest_cluster": max(clusters.values()) if clusters else 0,
            "params": {
                "num_perm": NUM_PERM,
                "bands": LSH_BANDS,
                "rows": LSH_ROWS,
                "shingle_words": SHINGLE_WORDS,
                "verify_min_agree": VERIFY_MIN_AGREE,
                "est_jaccard_threshold": round(VERIFY_MIN_AGREE / NUM_PERM, 3),
            },
        }


def unique_counts(hashes: np.ndarray) -> tuple[int, int]:
    """(total, unique) for an array of 64-bit doc hashes."""
    return int(hashes.size), int(np.unique(hashes).size)
