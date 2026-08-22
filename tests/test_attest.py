"""Attestation of a corpus Shuddhi did not build.

The feature's value rests entirely on it being honest about its own limits,
so most of these tests assert what an attestation must NOT claim. An
attestation that quietly implied provenance would be worse than no
attestation at all — it would launder unknown data through our receipt.
"""

import json
import os

import attest


def _corpus(tmp_path, files: dict[str, str]) -> str:
    root = tmp_path / "corpus"
    root.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return str(root)


DOCS = {"a.txt": "first document\n\nsecond document\n",
        "b.txt": "third document\n"}


# ----------------------------------------------------------- determinism --

def test_same_corpus_yields_the_same_hash(tmp_path):
    """The whole receipt is worthless if it is not reproducible."""
    root = _corpus(tmp_path, DOCS)
    a = attest.attest_corpus(root, "c")
    b = attest.attest_corpus(root, "c")
    assert a["corpus_build_hash"] == b["corpus_build_hash"]


def test_file_order_on_disk_does_not_change_the_hash(tmp_path):
    """Walk order varies by filesystem; the hash must not."""
    r1 = _corpus(tmp_path / "x", {"a.txt": "one\n", "b.txt": "two\n"})
    r2 = _corpus(tmp_path / "y", {"b.txt": "two\n", "a.txt": "one\n"})
    assert (attest.attest_corpus(r1, "c")["corpus_build_hash"]
            == attest.attest_corpus(r2, "c")["corpus_build_hash"])


def test_one_changed_byte_changes_the_hash(tmp_path):
    root = _corpus(tmp_path, DOCS)
    before = attest.attest_corpus(root, "c")["corpus_build_hash"]
    (tmp_path / "corpus" / "b.txt").write_text("third document!\n", encoding="utf-8")
    after = attest.attest_corpus(root, "c")["corpus_build_hash"]
    assert before != after


def test_hash_matches_the_native_build_definition(tmp_path):
    """Attested and Shuddhi-built corpora must be comparable, so the hash
    definition has to be the same one builder.filtered_build_hash uses."""
    import hashlib

    import numpy as np

    import shards as shards_mod

    root = _corpus(tmp_path, DOCS)
    att = attest.attest_corpus(root, "c")

    hashes = []
    for name in sorted(DOCS):
        for _, doc in shards_mod.iter_docs(os.path.join(root, name)):
            hashes.append(shards_mod.doc_hash64(doc))
    arr = np.array(sorted(hashes), dtype=np.uint64)
    expected = hashlib.blake2b(arr.tobytes(), digest_size=32).hexdigest()
    assert att["corpus_build_hash"] == expected


# ------------------------------------------------------------- honesty ----

def test_provenance_is_UNKNOWN_not_blank_without_a_registry(tmp_path):
    """A blank field reads as 'nothing to declare'. That misreading is the
    failure mode this feature must not enable."""
    att = attest.attest_corpus(_corpus(tmp_path, DOCS), "c")
    assert att["provenance"]["status"] == "UNKNOWN"
    assert att["provenance"]["sources"] is None
    assert "unknown" in att["provenance"]["detail"].lower()


def test_states_it_proves_content_not_acquisition(tmp_path):
    att = attest.attest_corpus(_corpus(tmp_path, DOCS), "c")
    joined = " ".join(att["limitations"]).lower()
    assert "content" in joined and "acquisition" in joined
    assert "cannot" in joined or "does not" in joined


def test_never_claims_the_corpus_is_clean_or_lawful(tmp_path):
    att = attest.attest_corpus(_corpus(tmp_path, DOCS), "c")
    blob = json.dumps(att).lower()
    for forbidden in ("is compliant", "lawfully obtained", "verified clean",
                      "guarantees", "certifies"):
        assert forbidden not in blob, f"attestation overclaims: {forbidden!r}"


def test_absence_of_finding_is_not_claimed_as_absence(tmp_path):
    att = attest.attest_corpus(_corpus(tmp_path, DOCS), "c")
    joined = " ".join(att["limitations"]).lower()
    assert "absence of a finding is not proof of absence" in joined


# ------------------------------------------------------------- upstream ---

def test_upstream_manifest_is_cited_never_verified(tmp_path):
    root = _corpus(tmp_path, DOCS)
    (tmp_path / "corpus" / "stats.json").write_text(
        json.dumps({"documents": 999999, "claim": "we removed everything bad"}),
        encoding="utf-8")
    att = attest.attest_corpus(root, "c")
    up = att["upstream"]
    assert up is not None
    assert up["tool"] == "datatrove"
    assert up["cited_not_verified"] is True
    # the upstream's own document count must NOT become ours
    assert att["documents"] != 999999


def test_no_upstream_manifest_is_reported_as_none(tmp_path):
    att = attest.attest_corpus(_corpus(tmp_path, DOCS), "c")
    assert att["upstream"] is None


# -------------------------------------------------------------- content ---

def test_counts_documents_and_duplicates(tmp_path):
    root = _corpus(tmp_path, {"a.txt": "dup\n\ndup\n\nunique\n"})
    att = attest.attest_corpus(root, "c")
    assert att["documents"] == 3
    assert att["unique_documents"] == 2
    assert att["exact_duplicate_rate"] > 0


def test_scan_hook_is_optional_and_aggregated(tmp_path):
    root = _corpus(tmp_path, DOCS)
    plain = attest.attest_corpus(root, "c")
    assert plain["content_scan"] is None
    scanned = attest.attest_corpus(root, "c", scan=lambda d: {"seen": 1})
    assert scanned["content_scan"] == {"seen": 3}


def test_empty_corpus_does_not_crash(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    att = attest.attest_corpus(str(root), "c")
    assert att["documents"] == 0
    assert att["provenance"]["status"] == "UNKNOWN"


def test_render_human_surfaces_the_limitation(tmp_path):
    att = attest.attest_corpus(_corpus(tmp_path, DOCS), "c")
    text = attest.render_human(att)
    assert "UNKNOWN" in text
    assert "CONTENT, not ACQUISITION" in text
