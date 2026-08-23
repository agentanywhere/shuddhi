"""Applied-filter build: measured run -> filtered build with chained hash."""

import json

import pytest

from shuddhi import cli as factory

# long enough to clear the short-doc quality cap (>200 chars)
GOOD = (
    "The monsoon arrived early this year across the western coast and farmers "
    "welcomed the rains after a long dry spell that had threatened the season. "
    "Agricultural officers said reservoir levels were recovering steadily and "
    "the outlook for the kharif crop had improved considerably across districts. "
)
JUNK = "buy cheap widgets online today\n" * 40  # dup-line junk, quality < 0.5
PII_DOC = GOOD + " Contact support@example.com or call +91 9876543210."


def make_corpus(tmp_path):
    docs = [GOOD + str(i) for i in range(20)]
    docs.append(docs[0])          # exact dup
    docs.append(JUNK)             # quality drop
    docs.append(PII_DOC)          # pii doc (kept+redacted by default policy)
    shard = tmp_path / "eng.txt"
    shard.write_text("\n\n".join(docs) + "\n\n", encoding="utf-8")
    reg = {
        "registry_version": 1,
        "corpus_id": "build-fixture",
        "shards": [
            {"shard_id": "eng", "path": str(shard), "source": "fixture",
             "license": "CC-BY-4.0", "date_acquired": "2026-08-10",
             "data_class": "public", "language": "eng"},
        ],
    }
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(json.dumps(reg))
    return str(reg_path), shard


def measure(tmp_path, reg_path):
    out = tmp_path / "run"
    assert factory.main(["run", "--registry", reg_path, "--shard", "eng",
                         "--out", str(out), "--sample-every", "1"]) == 0
    assert factory.main(["merge", "--registry", reg_path, "--out", str(out)]) == 0
    return str(out)


def test_build_filters_and_records_parent_hash(tmp_path):
    reg_path, _ = make_corpus(tmp_path)
    run_dir = measure(tmp_path, reg_path)
    build_out = tmp_path / "build"
    rc = factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                       "--build-out", str(build_out), "--emit", "text"])
    assert rc == 0
    bm = json.loads((build_out / "BUILD-MANIFEST.json").read_text())
    parent = json.loads((tmp_path / "run" / "MANIFEST.json").read_text())

    assert bm["parent_corpus_build_hash"] == parent["corpus_build_hash"]
    assert bm["dropped_by_reason"]["exact_dup"] == 1
    assert bm["dropped_by_reason"]["quality"] == 1
    assert bm["kept_docs"] == 21          # 20 good + pii doc (redacted)
    assert bm["pii_redactions"] == 2      # email + phone
    assert len(bm["filtered_build_hash"]) == 64
    assert bm["filtered_build_hash"] != parent["corpus_build_hash"]

    emitted = (build_out / "eng.filtered.txt").read_text(encoding="utf-8")
    assert "[PII:email]" in emitted and "support@example.com" not in emitted
    assert JUNK.splitlines()[0] not in emitted
    assert emitted.count("\n\n") == 21


def test_build_hash_reproducible_and_emit_invariant(tmp_path):
    reg_path, _ = make_corpus(tmp_path)
    run_dir = measure(tmp_path, reg_path)
    hashes = []
    for name, emit in (("b1", "text"), ("b2", "none")):
        out = tmp_path / name
        assert factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                             "--build-out", str(out), "--emit", emit]) == 0
        hashes.append(json.loads((out / "BUILD-MANIFEST.json").read_text())["filtered_build_hash"])
    assert hashes[0] == hashes[1]  # selection identity independent of emission


def test_pii_drop_policy(tmp_path):
    reg_path, _ = make_corpus(tmp_path)
    run_dir = measure(tmp_path, reg_path)
    out = tmp_path / "b"
    assert factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                         "--build-out", str(out), "--pii", "drop"]) == 0
    bm = json.loads((out / "BUILD-MANIFEST.json").read_text())
    assert bm["dropped_by_reason"]["pii"] == 1
    assert bm["kept_docs"] == 20


def test_contamination_drop(tmp_path):
    reg_path, shard = make_corpus(tmp_path)
    run_dir = measure(tmp_path, reg_path)
    eval_set = tmp_path / "eval.jsonl"
    eval_set.write_text(json.dumps({"id": "e1", "text": GOOD + "0"}) + "\n")
    out = tmp_path / "b"
    assert factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                         "--build-out", str(out), "--eval-set", str(eval_set)]) == 0
    bm = json.loads((out / "BUILD-MANIFEST.json").read_text())
    assert bm["dropped_by_reason"]["contamination"] >= 1


def test_changed_shard_fails_integrity(tmp_path):
    reg_path, shard = make_corpus(tmp_path)
    run_dir = measure(tmp_path, reg_path)
    with open(shard, "a", encoding="utf-8") as f:
        f.write("a brand new document sneaked in after measurement\n\n")
    out = tmp_path / "b"
    with pytest.raises(RuntimeError, match="changed after measurement"):
        factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                      "--build-out", str(out)])


def test_ppx_filter_via_lm(tmp_path):
    reg_path, shard = make_corpus(tmp_path)
    # add a gibberish doc that heuristics alone would keep
    with open(shard, "a", encoding="utf-8") as f:
        f.write(("zqxj wvkp qzzt xkcv bnml pqrs zxcv qwer jklh vbnm " * 8) + "\n\n")
    lm_dir = tmp_path / "lms"
    assert factory.main(["train-lm", "--registry", reg_path, "--shard", "eng",
                         "--lm-dir", str(lm_dir), "--sample-every", "1"]) == 0
    run_dir = tmp_path / "run"
    assert factory.main(["run", "--registry", reg_path, "--shard", "eng",
                         "--out", str(run_dir), "--sample-every", "1",
                         "--lm", str(lm_dir / "eng.lm.gz")]) == 0
    assert factory.main(["merge", "--registry", reg_path, "--out", str(run_dir)]) == 0
    out = tmp_path / "b"
    # --min-ppx-sample: this fixture is deliberately tiny, and the default
    # guard (200 scored documents) would switch the filter off.
    assert factory.main(["build", "--registry", reg_path, "--run-dir", str(run_dir),
                         "--build-out", str(out), "--lm-dir", str(lm_dir),
                         "--ppx-percentile", "99", "--min-ppx-sample", "2"]) == 0
    bm = json.loads((out / "BUILD-MANIFEST.json").read_text())
    assert bm["dropped_by_reason"]["perplexity"] >= 1
    assert "eng" in bm["filter_config"]["max_bits_per_char"]


def test_partition_union_hash_equals_sequential(tmp_path):
    """Two-partition parallel build must produce the identical
    filtered_build_hash as one sequential build — the hash is a SET of kept
    doc hashes, so cross-partition duplicates collapse in the union."""
    # two shards sharing one duplicated document (cross-shard dup)
    shared = GOOD + " shared across both shards"
    a = tmp_path / "a.txt"
    a.write_text("\n\n".join([GOOD + f"a{i}" for i in range(10)] + [shared]) + "\n\n",
                 encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("\n\n".join([GOOD + f"b{i}" for i in range(10)] + [shared]) + "\n\n",
                 encoding="utf-8")
    reg = {
        "registry_version": 1, "corpus_id": "part-fixture",
        "shards": [
            {"shard_id": "a", "path": str(a), "source": "fixture", "license": "CC-BY-4.0",
             "date_acquired": "2026-08-10", "data_class": "public", "language": "eng"},
            {"shard_id": "b", "path": str(b), "source": "fixture", "license": "CC-BY-4.0",
             "date_acquired": "2026-08-10", "data_class": "public", "language": "eng"},
        ],
    }
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg))
    run_dir = tmp_path / "run"
    for sid in ("a", "b"):
        assert factory.main(["run", "--registry", str(reg_path), "--shard", sid,
                             "--out", str(run_dir), "--sample-every", "1"]) == 0
    assert factory.main(["merge", "--registry", str(reg_path), "--out", str(run_dir)]) == 0

    seq = tmp_path / "seq"
    assert factory.main(["build", "--registry", str(reg_path), "--run-dir", str(run_dir),
                         "--build-out", str(seq)]) == 0
    seq_m = json.loads((seq / "BUILD-MANIFEST.json").read_text())
    assert seq_m["dropped_by_reason"]["exact_dup"] == 1  # sequential sees the cross dup

    pa, pb = tmp_path / "pa", tmp_path / "pb"
    for out, shard in ((pa, "a"), (pb, "b")):
        assert factory.main(["build", "--registry", str(reg_path), "--run-dir", str(run_dir),
                             "--build-out", str(out), "--shards", shard]) == 0
    un = tmp_path / "union"
    assert factory.main(["build-union", "--build-outs", f"{pa},{pb}",
                         "--out", str(un)]) == 0
    un_m = json.loads((un / "BUILD-MANIFEST.json").read_text())

    assert un_m["filtered_build_hash"] == seq_m["filtered_build_hash"]
    assert un_m["kept_docs"] == seq_m["kept_docs"]
    assert un_m["cross_partition_rekept_docs"] == 1


def test_union_refuses_overlapping_partitions(tmp_path):
    reg_path, _ = make_corpus(tmp_path)
    run_dir = measure(tmp_path, reg_path)
    o1, o2 = tmp_path / "o1", tmp_path / "o2"
    for out in (o1, o2):
        assert factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                             "--build-out", str(out), "--shards", "eng"]) == 0
    assert factory.main(["build-union", "--build-outs", f"{o1},{o2}",
                         "--out", str(tmp_path / "u")]) == 2


def test_partition_configs_are_invariant_with_lm_cutoffs(tmp_path):
    """Regression (caught in production 2026-08-11): each partition's filter
    config must carry the FULL per-language cutoff map, so partition
    manifests union cleanly and match a sequential build's config sha."""
    hindi = ("भारत एक विशाल देश है और यहाँ अनेक भाषाएँ बोली जाती हैं। "
             "यह वाक्य केवल परीक्षण के लिए बार-बार लिखा गया है। ") * 6
    a = tmp_path / "a.txt"
    a.write_text("\n\n".join([GOOD + f"a{i}" for i in range(8)]) + "\n\n", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("\n\n".join([hindi + f"ब{i}" for i in range(8)]) + "\n\n", encoding="utf-8")
    reg = {
        "registry_version": 1, "corpus_id": "cfg-fixture",
        "shards": [
            {"shard_id": "a", "path": str(a), "source": "fixture", "license": "CC-BY-4.0",
             "date_acquired": "2026-08-10", "data_class": "public", "language": "eng"},
            {"shard_id": "b", "path": str(b), "source": "fixture", "license": "CC-BY-4.0",
             "date_acquired": "2026-08-10", "data_class": "public", "language": "hin"},
        ],
    }
    reg_path = tmp_path / "reg.json"
    reg_path.write_text(json.dumps(reg))
    lm_dir = tmp_path / "lms"
    run_dir = tmp_path / "run"
    for sid in ("a", "b"):
        assert factory.main(["train-lm", "--registry", str(reg_path), "--shard", sid,
                             "--lm-dir", str(lm_dir), "--sample-every", "1"]) == 0
    for sid, lang in (("a", "eng"), ("b", "hin")):
        assert factory.main(["run", "--registry", str(reg_path), "--shard", sid,
                             "--out", str(run_dir), "--sample-every", "1",
                             "--lm", str(lm_dir / f"{lang}.lm.gz")]) == 0
    assert factory.main(["merge", "--registry", str(reg_path), "--out", str(run_dir)]) == 0

    seq, pa, pb, un = (tmp_path / n for n in ("seq", "pa", "pb", "un"))
    common = ["--registry", str(reg_path), "--run-dir", str(run_dir),
              "--lm-dir", str(lm_dir), "--ppx-percentile", "99",
              "--min-ppx-sample", "2"]
    assert factory.main(["build", *common, "--build-out", str(seq)]) == 0
    assert factory.main(["build", *common, "--build-out", str(pa), "--shards", "a"]) == 0
    assert factory.main(["build", *common, "--build-out", str(pb), "--shards", "b"]) == 0

    ms, ma, mb = (json.loads((d / "BUILD-MANIFEST.json").read_text()) for d in (seq, pa, pb))
    # the invariant: every build over the same measured run has the same config
    assert ma["filter_config_sha256"] == mb["filter_config_sha256"] == ms["filter_config_sha256"]
    assert sorted(ma["filter_config"]["max_bits_per_char"]) == ["eng", "hin"]

    assert factory.main(["build-union", "--build-outs", f"{pa},{pb}",
                         "--out", str(un)]) == 0
    mu = json.loads((un / "BUILD-MANIFEST.json").read_text())
    assert mu["filtered_build_hash"] == ms["filtered_build_hash"]
    assert mu["filter_config_sha256"] == ms["filter_config_sha256"]


def test_empty_build_is_flagged_in_the_manifest(tmp_path, capsys):
    """A receipt for an empty corpus is a valid receipt for nothing. The
    build must say so, in the manifest and on stderr, rather than exiting 0
    with a clean-looking hash. (Found by walking the quickstart as a new
    user: every document was dropped and nothing complained.)"""
    docs = [GOOD + str(i) for i in range(6)]
    shard = tmp_path / "s.txt"
    shard.write_text("\n\n".join(docs) + "\n\n", encoding="utf-8")
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "empty",
        "shards": [{"shard_id": "s", "path": str(shard), "source": "fixture",
                    "license": "CC0-1.0", "date_acquired": "2026-08-23",
                    "data_class": "synthetic-own", "language": "eng"}],
    }))
    run = tmp_path / "run"
    assert factory.main(["run", "--registry", str(reg), "--shard", "s",
                         "--out", str(run), "--sample-every", "1"]) == 0
    assert factory.main(["merge", "--registry", str(reg), "--out", str(run)]) == 0

    # a quality threshold nothing can satisfy
    out = tmp_path / "b"
    assert factory.main(["build", "--registry", str(reg), "--run-dir", str(run),
                         "--build-out", str(out), "--min-quality", "1.1"]) == 0
    bm = json.loads((out / "BUILD-MANIFEST.json").read_text())
    assert bm["kept_docs"] == 0
    assert bm["warnings"], "an empty build must carry a warning in its manifest"
    assert "EMPTY BUILD" in bm["warnings"][0]
    assert "EMPTY BUILD" in capsys.readouterr().err


def test_high_drop_rate_is_flagged(tmp_path):
    docs = [GOOD + str(i) for i in range(4)] + ["short one", "short two", "short three"]
    shard = tmp_path / "s.txt"
    shard.write_text("\n\n".join(docs) + "\n\n", encoding="utf-8")
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "drop",
        "shards": [{"shard_id": "s", "path": str(shard), "source": "fixture",
                    "license": "CC0-1.0", "date_acquired": "2026-08-23",
                    "data_class": "synthetic-own", "language": "eng"}],
    }))
    run = tmp_path / "run"
    factory.main(["run", "--registry", str(reg), "--shard", "s", "--out", str(run),
                  "--sample-every", "1"])
    factory.main(["merge", "--registry", str(reg), "--out", str(run)])
    out = tmp_path / "b"
    factory.main(["build", "--registry", str(reg), "--run-dir", str(run),
                  "--build-out", str(out), "--min-quality", "0.9"])
    bm = json.loads((out / "BUILD-MANIFEST.json").read_text())
    if bm["kept_docs"] and bm["kept_docs"] < 4:
        assert any("HIGH DROP RATE" in w for w in bm["warnings"])


def test_healthy_build_has_no_warnings(tmp_path):
    reg_path, _ = make_corpus(tmp_path)
    run_dir = measure(tmp_path, reg_path)
    out = tmp_path / "b"
    assert factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                         "--build-out", str(out)]) == 0
    bm = json.loads((out / "BUILD-MANIFEST.json").read_text())
    assert bm["kept_docs"] > 0
    assert bm["warnings"] == []


def test_a_thin_perplexity_sample_disables_the_filter(tmp_path, capsys):
    """Found by walking the quickstart: the default stride meant ONE
    document was scored, so p99 was that document and the filter dropped 33
    of 42. A percentile from a handful of samples is not a threshold."""
    docs = [GOOD + f"number {i}" for i in range(40)]
    shard = tmp_path / "s.txt"
    shard.write_text("\n\n".join(docs) + "\n\n", encoding="utf-8")
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "thin",
        "shards": [{"shard_id": "s", "path": str(shard), "source": "fixture",
                    "license": "CC0-1.0", "date_acquired": "2026-08-23",
                    "data_class": "synthetic-own", "language": "eng"}],
    }))
    lm_dir, run_dir = tmp_path / "lms", tmp_path / "run"
    factory.main(["train-lm", "--registry", str(reg), "--shard", "s",
                  "--lm-dir", str(lm_dir), "--sample-every", "1"])
    # stride 20 over 40 documents scores only 2 — far too few to threshold
    factory.main(["run", "--registry", str(reg), "--shard", "s", "--out", str(run_dir),
                  "--sample-every", "20", "--lm", str(lm_dir / "eng.lm.gz")])
    factory.main(["merge", "--registry", str(reg), "--out", str(run_dir)])

    out = tmp_path / "b"
    assert factory.main(["build", "--registry", str(reg), "--run-dir", str(run_dir),
                         "--build-out", str(out), "--lm-dir", str(lm_dir)]) == 0
    bm = json.loads((out / "BUILD-MANIFEST.json").read_text())
    assert bm["dropped_by_reason"]["perplexity"] == 0, \
        "a filter with no usable distribution must drop nothing"
    assert bm["filter_config"]["max_bits_per_char"] == {}
    assert "perplexity filter is OFF" in capsys.readouterr().err


def test_filtered_build_hash_covers_documents_not_configuration(tmp_path):
    """Pins the actual semantics, which the docs once described backwards.

    `filtered_build_hash` is a content hash of the SELECTED documents. It does
    not fold in `filter_config_sha256` -- deliberately, because a hash that
    included the config could not be recomputed by a third party holding only
    the source files, and independent verifiability is the whole point.

    So two builds that select the same documents by different means share a
    build hash and are told apart by their config sha. The docs claimed the
    opposite in six places, including inside the generated EU AI Act summary.
    """
    import json

    reg_path, _ = make_corpus(tmp_path)
    run_dir = measure(tmp_path, reg_path)
    a = tmp_path / "a"
    b = tmp_path / "b"
    # Same selection, different configuration: PII policy changes emitted text
    # but not which documents were chosen.
    assert factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                         "--build-out", str(a), "--emit", "text", "--pii", "keep"]) == 0
    assert factory.main(["build", "--registry", reg_path, "--run-dir", run_dir,
                         "--build-out", str(b), "--emit", "text", "--pii", "redact"]) == 0
    ma = json.loads((a / "BUILD-MANIFEST.json").read_text())
    mb = json.loads((b / "BUILD-MANIFEST.json").read_text())

    assert ma["kept_docs"] == mb["kept_docs"]
    assert ma["filtered_build_hash"] == mb["filtered_build_hash"], \
        "build hash must depend on the selected documents only"
    assert ma["filter_config_sha256"] != mb["filter_config_sha256"], \
        "the config sha is what distinguishes these two builds"
