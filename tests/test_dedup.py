import numpy as np

from shuddhi import dedup

BASE = (
    "the quick brown fox jumps over the lazy dog while the cat watches from the "
    "windowsill and the birds sing in the garden as morning light spreads slowly "
    "across the quiet village where nothing much ever happens except the market"
)
# Near-dup: identical text plus a short appended tail — high true Jaccard
# (only the tail shingles differ), safely above the detection threshold.
VARIANT = BASE + " with a small note appended at the end"
DISTINCT = (
    "completely different content about railway timetables and the economics of "
    "freight corridors in northern regions with entirely separate vocabulary "
    "signal systems locomotives wagons junctions platforms schedules and cargo"
)


def test_shingles_deterministic():
    a = dedup.shingle_hashes(BASE)
    b = dedup.shingle_hashes(BASE)
    assert np.array_equal(a, b)


def test_too_short_returns_none():
    assert dedup.shingle_hashes("only four words here"[:9]) is None


def test_signature_shape_and_determinism():
    sig1 = dedup.minhash_signature(dedup.shingle_hashes(BASE))
    sig2 = dedup.minhash_signature(dedup.shingle_hashes(BASE))
    assert sig1.shape == (dedup.NUM_PERM,)
    assert np.array_equal(sig1, sig2)


def test_near_dup_similarity_ordering():
    sig_base = dedup.minhash_signature(dedup.shingle_hashes(BASE))
    sig_var = dedup.minhash_signature(dedup.shingle_hashes(VARIANT))
    sig_dist = dedup.minhash_signature(dedup.shingle_hashes(DISTINCT))
    agree_var = int((sig_base == sig_var).sum())
    agree_dist = int((sig_base == sig_dist).sum())
    assert agree_var > agree_dist
    assert agree_var >= dedup.VERIFY_MIN_AGREE
    assert agree_dist < dedup.VERIFY_MIN_AGREE


def test_index_clusters_near_dups_and_separates_distinct():
    idx = dedup.NearDupIndex()
    idx.add(BASE)
    idx.add(VARIANT)
    idx.add(DISTINCT)
    s = idx.summary()
    assert s["minhashed_docs"] == 3
    assert s["clusters"] == 2          # {BASE, VARIANT} + {DISTINCT}
    assert s["near_dup_docs"] == 1
    assert 0 < s["near_dup_rate"] < 1


def test_index_counts_exact_repeats():
    idx = dedup.NearDupIndex()
    for _ in range(5):
        idx.add(BASE)
    s = idx.summary()
    assert s["clusters"] == 1
    assert s["near_dup_docs"] == 4
    assert s["largest_cluster"] == 5


def test_unique_counts():
    arr = np.array([1, 2, 2, 3, 3, 3], dtype=np.uint64)
    total, unique = dedup.unique_counts(arr)
    assert (total, unique) == (6, 3)
