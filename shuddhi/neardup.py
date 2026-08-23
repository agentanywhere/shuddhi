"""Applied near-duplicate detection — full-corpus MinHash/LSH (v1.2).

v1 measured near-dups on a sample; this module finds them across EVERY
document so the build can drop them. Two phases, both CPU-frugal and
disk-backed so a 33M-doc corpus fits a small VM:

  sig    per shard: MinHash signature (32 perms, same parameters as the
         sampled stage in dedup.py) for every document, written in stream
         order to <shard>.sigs.u64 (n×32 uint64) + <shard>.valid.u8
         (1 = shingleable; docs under 5 words cannot near-dup match).

  merge  across shards: for each LSH band, derive a 64-bit band key per doc
         (numpy-vectorized), sort, and verify every collision group against
         its representative (>= VERIFY_MIN_AGREE of 32 rows). Verified pairs
         feed a union-find; each cluster keeps ONE exemplar and the rest go
         to the drop list.

Determinism: fixed permutation seeds, arithmetic band keys with fixed odd
constants, and an order-independent exemplar rule — the kept exemplar is the
MINIMUM doc-hash in the cluster — so the drop list (and therefore the
filtered build hash) does not depend on shard order or parallelism.

Output: neardup-drop.u64 — ascending unique doc-hashes to drop — plus a
stats JSON. The build cites the drop list's sha256 in its filter config.
"""

from __future__ import annotations

import hashlib
import json
import os

import numpy as np

from .dedup import NUM_PERM, LSH_BANDS, LSH_ROWS, VERIFY_MIN_AGREE, minhash_signature, shingle_hashes

SIG_COLS = NUM_PERM
# fixed odd multipliers for the arithmetic band key (collisions are fine —
# every collision group is signature-verified before it can drop anything)
_BAND_MULT = np.array(
    [0x9E3779B97F4A7C15, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0x27D4EB2F165667C5],
    dtype=np.uint64,
)


def write_shard_sigs(shard_path: str, out_dir: str, shard_id: str) -> dict:
    """Phase 'sig' for one shard. Returns counts."""
    from . import shards as shards_mod

    sig_path = os.path.join(out_dir, f"{shard_id}.sigs.u64")
    valid_path = os.path.join(out_dir, f"{shard_id}.valid.u8")
    n = 0
    n_valid = 0
    with open(sig_path, "wb") as sf, open(valid_path, "wb") as vf:
        for _idx, doc in shards_mod.iter_docs(shard_path):
            text = doc.decode("utf-8", "replace")
            sh = shingle_hashes(text)
            if sh is None:
                sf.write(b"\x00" * (SIG_COLS * 8))
                vf.write(b"\x00")
            else:
                minhash_signature(sh).astype(np.uint64).tofile(sf)
                vf.write(b"\x01")
                n_valid += 1
            n += 1
    return {"docs": n, "shingleable": n_valid}


class _UnionFind:
    def __init__(self, n: int):
        self.parent = np.arange(n, dtype=np.int64)

    def find(self, i: int) -> int:
        p = self.parent
        root = i
        while p[root] != root:
            root = p[root]
        while p[i] != root:  # path compression
            p[i], i = root, p[i]
        return root

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            if ri < rj:
                self.parent[rj] = ri
            else:
                self.parent[ri] = rj


def merge_and_cluster(run_dir: str, sig_dir: str, shard_ids: list[str], out_path: str) -> dict:
    """Phase 'merge': cluster near-dups across all shards, write the drop list."""
    sigs_list = []
    valids = []
    hashes = []
    for sid in shard_ids:
        sig = np.memmap(os.path.join(sig_dir, f"{sid}.sigs.u64"), dtype=np.uint64, mode="r")
        sig = sig.reshape(-1, SIG_COLS)
        sigs_list.append(sig)
        valids.append(np.fromfile(os.path.join(sig_dir, f"{sid}.valid.u8"), dtype=np.uint8))
        h = np.fromfile(os.path.join(run_dir, f"{sid}.hashes.u64"), dtype=np.uint64)
        if h.size != sig.shape[0]:
            raise RuntimeError(
                f"{sid}: {h.size} hashes but {sig.shape[0]} signatures — "
                "sig pass and measured run disagree; re-run whichever is stale"
            )
        hashes.append(h)

    valid = np.concatenate(valids).astype(bool)
    all_hashes = np.concatenate(hashes)
    offsets = np.cumsum([0] + [s.shape[0] for s in sigs_list])
    n = int(offsets[-1])
    uf = _UnionFind(n)
    valid_idx = np.nonzero(valid)[0]

    def band_slice(band: int) -> np.ndarray:
        """(n_valid, LSH_ROWS) band rows for valid docs, in global order."""
        parts = []
        lo, hi = band * LSH_ROWS, (band + 1) * LSH_ROWS
        for i, sig in enumerate(sigs_list):
            v = valids[i].astype(bool)
            parts.append(np.asarray(sig[:, lo:hi])[v])
        return np.concatenate(parts, axis=0)

    verified_pairs = 0
    for band in range(LSH_BANDS):
        rows = band_slice(band)
        keys = np.zeros(rows.shape[0], dtype=np.uint64)
        for c in range(LSH_ROWS):
            keys ^= rows[:, c] * _BAND_MULT[c]
        order = np.argsort(keys, kind="stable")
        sorted_keys = keys[order]
        # boundaries of equal-key runs
        boundary = np.nonzero(np.diff(sorted_keys))[0] + 1
        starts = np.concatenate(([0], boundary))
        ends = np.concatenate((boundary, [sorted_keys.size]))
        for s, e in zip(starts, ends):
            if e - s < 2:
                continue
            members = valid_idx[order[s:e]]  # global doc indices
            rep = int(members[0])
            rep_sig = _sig_at(sigs_list, offsets, rep)
            for m in members[1:]:
                m = int(m)
                agree = int((_sig_at(sigs_list, offsets, m) == rep_sig).sum())
                if agree >= VERIFY_MIN_AGREE:
                    uf.union(rep, m)
                    verified_pairs += 1

    # clusters -> drop list (exemplar = min doc-hash in cluster)
    roots: dict[int, list[int]] = {}
    parent = uf.parent
    # only docs that were ever unioned matter
    moved = np.nonzero(parent != np.arange(n, dtype=np.int64))[0]
    for i in moved:
        roots.setdefault(uf.find(int(i)), []).append(int(i))
    for r in list(roots):
        roots[r].append(r)

    drop: set[int] = set()
    largest = 0
    docs_in_clusters = 0
    for members in roots.values():
        cluster_hashes = {int(all_hashes[m]) for m in members}
        largest = max(largest, len(members))
        docs_in_clusters += len(members)
        exemplar = min(cluster_hashes)
        drop.update(h for h in cluster_hashes if h != exemplar)

    drop_arr = np.array(sorted(drop), dtype=np.uint64)
    drop_arr.tofile(out_path)
    stats = {
        "docs": n,
        "shingleable": int(valid.sum()),
        "verified_pairs": verified_pairs,
        "clusters": len(roots),
        "docs_in_clusters": docs_in_clusters,
        "largest_cluster": largest,
        "dropped_unique_hashes": int(drop_arr.size),
        "droplist_sha256": hashlib.sha256(drop_arr.tobytes()).hexdigest(),
        "params": {
            "num_perm": NUM_PERM, "bands": LSH_BANDS, "rows": LSH_ROWS,
            "verify_min_agree": VERIFY_MIN_AGREE,
            "exemplar_rule": "min-doc-hash-in-cluster",
        },
    }
    with open(out_path + ".stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=1)
    return stats


def _sig_at(sigs_list, offsets, global_idx: int) -> np.ndarray:
    shard = int(np.searchsorted(offsets, global_idx, side="right")) - 1
    return np.asarray(sigs_list[shard][global_idx - int(offsets[shard])])


def load_droplist(path: str) -> np.ndarray:
    return np.fromfile(path, dtype=np.uint64)  # written sorted


def droplist_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
