"""End-to-end: registry -> run -> merge over tiny fixture shards, including a
customer-class shard that must be refused and surface in the manifest."""

import json

import pytest

import factory

HINDI_DOC = "भारत एक विशाल देश है और यहाँ अनेक भाषाएँ बोली जाती हैं। " * 8
ENG_DOC = (
    "The monsoon arrived early this year across the western coast and farmers "
    "welcomed the rains after a long dry spell that had threatened the season. "
)
DUP_DOC = "this exact document appears twice in the shard " * 6


def build_corpus(tmp_path):
    hin = tmp_path / "hin.txt"
    hin.write_text(
        "\n\n".join([HINDI_DOC + str(i) for i in range(30)] + [DUP_DOC, DUP_DOC]) + "\n\n",
        encoding="utf-8",
    )
    eng = tmp_path / "eng.txt"
    eng.write_text(
        "\n\n".join([ENG_DOC + str(i) for i in range(30)] + [DUP_DOC]) + "\n\n",
        encoding="utf-8",
    )
    cust = tmp_path / "cust.txt"
    cust.write_text("customer ticket text that must never be read\n\n", encoding="utf-8")

    reg = {
        "registry_version": 1,
        "corpus_id": "fixture-corpus",
        "shards": [
            {"shard_id": "hin", "path": str(hin), "source": "fixture", "license": "CC-BY-4.0",
             "date_acquired": "2026-08-10", "data_class": "public", "language": "hin"},
            {"shard_id": "eng", "path": str(eng), "source": "fixture", "license": "CC-BY-4.0",
             "date_acquired": "2026-08-10", "data_class": "public", "language": "eng"},
            {"shard_id": "cust", "path": str(cust), "source": "a customer export",
             "date_acquired": "2026-08-10", "data_class": "customer", "language": "eng",
             "license": "n/a"},
        ],
    }
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(reg))
    return str(reg_path)


def run_all(tmp_path, reg_path, out_name):
    out = tmp_path / out_name
    for shard in ("hin", "eng"):
        rc = factory.main([
            "run", "--registry", reg_path, "--shard", shard, "--out", str(out),
            "--sample-every", "1", "--minhash-every", "1",
        ])
        assert rc == 0
    rc = factory.main(["merge", "--registry", reg_path, "--out", str(out)])
    assert rc == 0
    return json.loads((out / "MANIFEST.json").read_text())


def test_check_flags_refusals(tmp_path, capsys):
    reg_path = build_corpus(tmp_path)
    rc = factory.main(["check", "--registry", reg_path])
    assert rc == 2  # refusals present
    out = capsys.readouterr().out
    assert "✗ cust" in out and "never training" in out


def test_run_refuses_customer_shard(tmp_path):
    reg_path = build_corpus(tmp_path)
    with pytest.raises(SystemExit) as e:
        factory.main(["run", "--registry", reg_path, "--shard", "cust",
                      "--out", str(tmp_path / "out")])
    assert e.value.code == 2


def test_end_to_end_manifest(tmp_path):
    reg_path = build_corpus(tmp_path)
    manifest = run_all(tmp_path, reg_path, "out")

    fp = manifest["full_pass"]
    assert fp["total_docs"] == 63          # 32 + 31
    assert fp["unique_docs"] == 61         # DUP_DOC counted once
    assert fp["duplicate_docs"] == 2
    assert fp["intra_shard_dup_docs"] == 1  # hin has it twice
    assert fp["cross_shard_dup_docs"] == 1  # eng shares it with hin

    refused = manifest["provenance_gate"]["refused"]
    assert [r["shard_id"] for r in refused] == ["cust"]

    # per-shard receipts present
    assert all(len(s["file_sha256"]) == 64 for s in manifest["shards"])

    # composition sampled at stride 1: full coverage of the fixture
    assert manifest["sampled"]["doc_coverage"] == 1.0
    domains = manifest["sampled"]["domains"]
    assert domains.get("indic", 0) >= 30   # hindi shard
    assert len(manifest["corpus_build_hash"]) == 64


def test_build_hash_reproducible(tmp_path):
    reg_path = build_corpus(tmp_path)
    m1 = run_all(tmp_path, reg_path, "out1")
    m2 = run_all(tmp_path, reg_path, "out2")
    assert m1["corpus_build_hash"] == m2["corpus_build_hash"]


def test_merge_partial_records_missing(tmp_path):
    reg_path = build_corpus(tmp_path)
    out = tmp_path / "out"
    rc = factory.main(["run", "--registry", reg_path, "--shard", "hin", "--out", str(out),
                       "--sample-every", "1"])
    assert rc == 0
    # without --partial: refuse to pretend eng was covered
    assert factory.main(["merge", "--registry", reg_path, "--out", str(out)]) == 2
    assert factory.main(["merge", "--registry", reg_path, "--out", str(out), "--partial"]) == 0
    manifest = json.loads((out / "MANIFEST.json").read_text())
    assert manifest["provenance_gate"]["not_yet_processed"] == ["eng"]
