"""Full-corpus near-dup: sig pass + cross-shard clustering + drop list."""

import json

import numpy as np

from shuddhi import cli as factory
from shuddhi.neardup import load_droplist
from shuddhi.shards import doc_hash64

BASE = (
    "the quick brown fox jumps over the lazy dog while the cat watches from the "
    "windowsill and the birds sing in the garden as morning light spreads slowly "
    "across the quiet village where nothing much ever happens except the market "
    "gathering every thursday when farmers arrive with vegetables and stories. "
)
VARIANT = BASE + "with a small note appended at the end"       # near-dup of BASE
DISTINCT = (
    "completely different content about railway timetables and the economics of "
    "freight corridors in northern regions with entirely separate vocabulary "
    "signal systems locomotives wagons junctions platforms schedules and cargo "
    "moving between terminals overnight under new operating rules this season. "
)


DISTINCT2 = (
    "an unrelated essay on classical music traditions where composers arrange "
    "melodies for orchestras with strings woodwinds brass and percussion while "
    "audiences gather in concert halls to hear symphonies performed by skilled "
    "musicians rehearsing daily under demanding conductors through the winter. "
)


def make(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("\n\n".join([BASE, DISTINCT, "tiny"]) + "\n\n", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("\n\n".join([VARIANT, DISTINCT2]) + "\n\n", encoding="utf-8")
    reg = {
        "registry_version": 1, "corpus_id": "nd-fixture",
        "shards": [
            {"shard_id": "a", "path": str(a), "source": "fixture", "license": "CC-BY-4.0",
             "date_acquired": "2026-08-11", "data_class": "public", "language": "eng"},
            {"shard_id": "b", "path": str(b), "source": "fixture", "license": "CC-BY-4.0",
             "date_acquired": "2026-08-11", "data_class": "public", "language": "eng"},
        ],
    }
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg))
    run_dir = tmp_path / "run"
    for sid in ("a", "b"):
        assert factory.main(["run", "--registry", str(reg_path), "--shard", sid,
                             "--out", str(run_dir), "--sample-every", "1"]) == 0
    assert factory.main(["merge", "--registry", str(reg_path), "--out", str(run_dir)]) == 0
    return str(reg_path), str(run_dir)


def neardup_pass(tmp_path, reg_path, run_dir):
    sig_dir = tmp_path / "sigs"
    for sid in ("a", "b"):
        assert factory.main(["neardup-sig", "--registry", reg_path, "--shard", sid,
                             "--sig-dir", str(sig_dir)]) == 0
    drop_path = tmp_path / "neardup-drop.u64"
    assert factory.main(["neardup-merge", "--registry", reg_path, "--run-dir", run_dir,
                         "--sig-dir", str(sig_dir), "--out", str(drop_path)]) == 0
    return str(drop_path)


def test_cross_shard_near_dup_detected_with_min_hash_exemplar(tmp_path):
    reg_path, run_dir = make(tmp_path)
    drop_path = neardup_pass(tmp_path, reg_path, run_dir)
    drop = load_droplist(drop_path)
    # documents are whitespace-stripped by the shard iterator before hashing
    h_base = doc_hash64(BASE.strip().encode())
    h_var = doc_hash64(VARIANT.strip().encode())
    # exactly one of the pair is dropped, and it is the LARGER hash
    # (exemplar rule: keep min doc-hash — order-independent)
    assert drop.size == 1
    assert int(drop[0]) == max(h_base, h_var)
    stats = json.loads(open(drop_path + ".stats.json").read())
    assert stats["clusters"] == 1
    assert stats["params"]["exemplar_rule"] == "min-doc-hash-in-cluster"


def test_droplist_deterministic(tmp_path):
    reg_path, run_dir = make(tmp_path)
    d1 = neardup_pass(tmp_path, reg_path, run_dir)
    s1 = json.loads(open(d1 + ".stats.json").read())["droplist_sha256"]
    sig2 = tmp_path / "sigs2"
    for sid in ("a", "b"):
        assert factory.main(["neardup-sig", "--registry", reg_path, "--shard", sid,
                             "--sig-dir", str(sig2)]) == 0
    d2 = tmp_path / "drop2.u64"
    assert factory.main(["neardup-merge", "--registry", reg_path, "--run-dir", run_dir,
                         "--sig-dir", str(sig2), "--out", str(d2)]) == 0
    s2 = json.loads(open(str(d2) + ".stats.json").read())["droplist_sha256"]
    assert s1 == s2


def test_build_applies_neardup_drop(tmp_path):
    reg_path, run_dir = make(tmp_path)
    drop_path = neardup_pass(tmp_path, reg_path, run_dir)
    out = tmp_path / "build"
    assert factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                         "--build-out", str(out), "--neardup-drop", drop_path]) == 0
    bm = json.loads((out / "BUILD-MANIFEST.json").read_text())
    assert bm["dropped_by_reason"]["near_dup"] == 1
    assert len(bm["filter_config"]["neardup_droplist_sha256"]) == 64
    # 5 docs total: 1 near-dup dropped, "tiny" dropped by quality cap
    assert bm["kept_docs"] == 3


def test_sig_count_mismatch_fails_loudly(tmp_path):
    reg_path, run_dir = make(tmp_path)
    sig_dir = tmp_path / "sigs"
    for sid in ("a", "b"):
        assert factory.main(["neardup-sig", "--registry", reg_path, "--shard", sid,
                             "--sig-dir", str(sig_dir)]) == 0
    # corrupt: append one fake signature row to shard a
    with open(sig_dir / "a.sigs.u64", "ab") as f:
        f.write(b"\x00" * (32 * 8))
    with open(sig_dir / "a.valid.u8", "ab") as f:
        f.write(b"\x00")
    import pytest

    with pytest.raises(RuntimeError, match="disagree"):
        factory.main(["neardup-merge", "--registry", reg_path, "--run-dir", run_dir,
                      "--sig-dir", str(sig_dir), "--out", str(tmp_path / "d.u64")])
