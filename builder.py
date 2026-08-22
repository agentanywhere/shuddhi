"""Applied-filter builds — stage 7b. Measurement becomes production.

`factory.py build` consumes a *measured* run (run → merge → build, in that
order) and produces a filtered corpus build: the subset of documents that
survive the configured filters, identified by a `filtered_build_hash` that is
**chained** to the parent measurement:

    parent corpus_build_hash  (from MANIFEST.json of the measured run)
      + filter_config sha256  (canonical JSON of every threshold used)
      -> filtered_build_hash  (blake2b over the sorted kept doc-hash set)

Determinism: same raw files + same config => same filtered hash, whether or
not text is emitted. Emission (--emit text) additionally writes the kept
documents per shard and records each output file's sha256.

Integrity: build recomputes every document hash and requires it to exist in
the measured run's hash set — if a shard file changed after measurement, the
build fails loudly instead of silently building something unmeasured.

Filter precedence per document (first hit wins, counted by reason):
    exact-dup -> near-dup -> quality -> perplexity -> toxicity
    -> contamination -> plugins -> pii

Third-party and commercial filters plug in at the `plugins` position without
forking the engine; see plugins.py. Their identities enter the filter config
sha, so the receipt covers them too.
"""

from __future__ import annotations

import hashlib
import json
import os
from array import array
from dataclasses import dataclass, field

import numpy as np

import pii as pii_mod
import quality as quality_mod
import shards as shards_mod

DROP_REASONS = ("exact_dup", "near_dup", "quality", "perplexity", "toxicity",
                "contamination", "pii")


@dataclass
class FilterConfig:
    min_quality: float = 0.5
    # per-language bits/char cutoffs (from the measured run's percentiles);
    # empty dict disables the perplexity filter for languages not listed.
    max_bits_per_char: dict = field(default_factory=dict)
    pii_policy: str = "redact"  # keep | redact | drop
    drop_contaminated: bool = True
    # sha256 of the near-dup drop list (neardup-drop.u64); "" = filter off
    neardup_droplist_sha256: str = ""
    # sha256 of the toxicity lexicon; "" = filter off
    toxicity_lexicon_sha256: str = ""
    # identities of enabled filter plugins, in application order (plugins.py).
    # These are part of the config identity: a plugin that changes verdicts
    # must change its identity, or two different corpora could claim one hash.
    plugin_identities: list = field(default_factory=list)

    def canonical(self) -> str:
        # scorer probe sizes are part of the config identity: the same
        # thresholds with different probes are a different filter
        import ngram_lm

        return json.dumps(
            {
                "min_quality": self.min_quality,
                "max_bits_per_char": {k: self.max_bits_per_char[k] for k in sorted(self.max_bits_per_char)},
                "pii_policy": self.pii_policy,
                "drop_contaminated": self.drop_contaminated,
                "neardup_droplist_sha256": self.neardup_droplist_sha256,
                "toxicity_lexicon_sha256": self.toxicity_lexicon_sha256,
                "plugins": self.plugin_identities,
                "scorer_params": {
                    "ppx_probe_chars": ngram_lm.SCORE_PROBE_CHARS,
                    "quality_probe_chars": quality_mod.PROBE_CHARS,
                    "quality_probe_words": quality_mod.PROBE_WORDS,
                },
            },
            sort_keys=True,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical().encode()).hexdigest()


class HashSetIndex:
    """Membership + consumed-marking over the measured run's unique hashes.
    ~8 bytes/doc for the sorted array + 1 byte/doc for the bitmap."""

    def __init__(self, unique_sorted: np.ndarray):
        self._u = unique_sorted
        self._consumed = np.zeros(unique_sorted.size, dtype=bool)

    @classmethod
    def from_run_dir(cls, run_dir: str, shard_ids: list[str]) -> "HashSetIndex":
        arrays = [
            np.fromfile(os.path.join(run_dir, f"{sid}.hashes.u64"), dtype=np.uint64)
            for sid in shard_ids
        ]
        return cls(np.unique(np.concatenate(arrays)))

    def claim_first(self, h: int) -> bool | None:
        """True if h is the first occurrence (kept), False if already consumed
        (exact dup), None if h was never measured (integrity violation)."""
        idx = int(np.searchsorted(self._u, np.uint64(h)))
        if idx >= self._u.size or int(self._u[idx]) != h:
            return None
        if self._consumed[idx]:
            return False
        self._consumed[idx] = True
        return True


def build_shard(
    shard,
    index: HashSetIndex,
    cfg: FilterConfig,
    lm=None,
    eval_index=None,
    emit_path: str | None = None,
    neardup_drop: np.ndarray | None = None,
    tox_lexicon=None,
    plugins: list | None = None,
) -> dict:
    """Filter one shard. Returns counts + emitted-file receipt."""
    plugins = plugins or []
    counts = {r: 0 for r in DROP_REASONS}
    counts.update({f"plugin:{p.name}": 0 for p in plugins})
    kept = 0
    kept_hashes = array("Q")
    pii_redactions = 0
    out_f = None
    out_sha = hashlib.sha256() if emit_path else None
    max_bits = cfg.max_bits_per_char.get(shard.language)

    try:
        if emit_path:
            out_f = open(emit_path, "wb")
        for _idx, doc in shards_mod.iter_docs(shard.path):
            h = shards_mod.doc_hash64(doc)
            claim = index.claim_first(h)
            if claim is None:
                raise RuntimeError(
                    f"{shard.shard_id}: document at index {_idx} is not in the measured "
                    "run's hash set — the shard file changed after measurement. "
                    "Re-run measurement before building."
                )
            if claim is False:
                counts["exact_dup"] += 1
                continue
            if neardup_drop is not None and neardup_drop.size:
                j = int(np.searchsorted(neardup_drop, np.uint64(h)))
                if j < neardup_drop.size and int(neardup_drop[j]) == h:
                    counts["near_dup"] += 1
                    continue

            text = doc.decode("utf-8", "replace")
            if quality_mod.score_doc(text)["score"] < cfg.min_quality:
                counts["quality"] += 1
                continue
            if lm is not None and max_bits is not None:
                bits = lm.bits_per_char(text)
                if bits is not None and bits > max_bits:
                    counts["perplexity"] += 1
                    continue
            if tox_lexicon is not None and tox_lexicon.score(text)["flagged"]:
                counts["toxicity"] += 1
                continue
            if cfg.drop_contaminated and eval_index is not None and eval_index.check_doc(text):
                counts["contamination"] += 1
                continue

            dropped_by_plugin = False
            for plug in plugins:
                if plug.check(text) is not None:
                    counts[f"plugin:{plug.name}"] += 1
                    dropped_by_plugin = True
                    break
            if dropped_by_plugin:
                continue

            pii_counts = pii_mod.scan(text)
            if pii_counts and cfg.pii_policy == "drop":
                counts["pii"] += 1
                continue

            kept += 1
            kept_hashes.append(h)
            if out_f is not None:
                if pii_counts and cfg.pii_policy == "redact":
                    text, red = pii_mod.redact(text)
                    pii_redactions += sum(red.values())
                    payload = text.encode("utf-8") + b"\n\n"
                else:
                    payload = doc + b"\n\n"
                out_f.write(payload)
                out_sha.update(payload)
            elif pii_counts and cfg.pii_policy == "redact":
                # hash-only build: count what emission WOULD redact
                pii_redactions += sum(pii_counts.values())
    finally:
        if out_f is not None:
            out_f.close()

    result = {
        "kept_docs": kept,
        "dropped": counts,
        "pii_redactions": pii_redactions,
        "kept_hashes": np.frombuffer(kept_hashes, dtype=np.uint64),
    }
    if emit_path:
        result["emitted_file"] = {
            "path": emit_path,
            "sha256": out_sha.hexdigest(),
            "bytes": os.path.getsize(emit_path),
        }
    return result


def filtered_build_hash(kept_hash_arrays: list[np.ndarray]) -> str:
    """blake2b-256 over the ascending-sorted kept doc-hash set — the same
    definition as the parent corpus_build_hash, so the two are comparable."""
    if kept_hash_arrays:
        all_kept = np.sort(np.concatenate(kept_hash_arrays))
    else:
        all_kept = np.empty(0, dtype=np.uint64)
    return hashlib.blake2b(all_kept.tobytes(), digest_size=32).hexdigest()
