"""Attestation — a verifiable receipt for a corpus Shuddhi did not build.

WHY THIS EXISTS
---------------
Most people preparing pretraining data already use something: NVIDIA NeMo
Curator, HuggingFace DataTrove, AI2 Dolma, or a pipeline of their own. Those
tools are good at what they do and this is not an attempt to replace them.

But none of them emit a *receipt*. They produce a corpus; they do not produce
an artefact you can hand a regulator, an auditor, or an enterprise customer
that says "this, exactly this, is what the model saw."

So rather than compete for throughput — a fight against NVIDIA's GPU dedup
that we would lose and that helps nobody — Shuddhi attests what another tool
produced:

    shuddhi attest --corpus ./out-from-datatrove/ --corpus-id fineweb-slice

The output is a fingerprint computed with the SAME hash definition a native
Shuddhi build uses, so an attested corpus and a Shuddhi-built one are
verifiable the same way and comparable to each other.

WHAT AN ATTESTATION PROVES — AND WHAT IT CANNOT
-----------------------------------------------
This distinction is the whole ethical basis of the feature, so it is enforced
in the output and not left to documentation.

PROVES (measured, here, now):
  * Exact content identity — the corpus build hash over every document.
    Change one byte anywhere and the hash changes.
  * What the corpus contains — document and byte counts, exact-duplicate rate,
    personal-data detections by type, toxicity-screen flags, language mix.

CANNOT PROVE (and must never imply):
  * Where the data came from. Rights, licensing and collection method are
    properties of ACQUISITION, and a directory of text carries no memory of
    how it was obtained.
  * That anything was filtered upstream, or filtered well.

An attestation therefore answers "what is in this corpus, verifiably?" — not
"was this corpus lawfully obtained?". Only a registry-backed build answers the
second, because only there is provenance a required field that refuses on
absence.

Passing `--registry` upgrades the attestation: provenance then comes from
declared, refusal-checked records instead of being marked unknown. Without
it, every provenance field is explicitly UNKNOWN rather than blank — because
a blank reads as "nothing to declare", which is the dangerous misreading.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

import numpy as np

from . import shards as shards_mod

ATTESTATION_VERSION = 1

TEXT_SUFFIXES = (".txt", ".jsonl", ".json", ".md")

# Receipts and manifests that sit *inside* a corpus directory but are not part
# of the corpus. Excluding them is a correctness requirement, not tidiness:
#
#   * Our own default writes ATTESTATION.json into the attested directory. Left
#     in, a second attestation would count the first as a document and return a
#     different hash — destroying the reproducibility the receipt exists to
#     assert.
#   * The upstream manifests _upstream_manifest() looks for are metadata about
#     a corpus, not text the model would ever see. Counting DataTrove's
#     stats.json as a training document would silently overstate the corpus.
EXCLUDED_FILENAMES = frozenset({
    "attestation.json",
    "build-manifest.json",
    "manifest.json",
    "stats.json",
    "processing_stats.json",
    "metadata.json",
})


def _corpus_files(root: str, suffixes=TEXT_SUFFIXES) -> list[str]:
    """Every attestable file under root, in a deterministic order.

    Sorted so the attestation is reproducible: the same directory attested on
    two machines must yield the same hash, which is the entire point.
    """
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.lower() in EXCLUDED_FILENAMES:
                continue
            if fn.lower().endswith(suffixes):
                found.append(os.path.join(dirpath, fn))
    return sorted(found)


def _upstream_manifest(root: str) -> dict | None:
    """Detect and record the producing tool's own manifest, if it left one.

    We read it purely to CITE it — never to trust its claims. Naming the
    upstream tool in the receipt is useful provenance context; treating its
    self-reported stats as verified would be exactly the overclaim this
    module exists to avoid.
    """
    candidates = {
        "shuddhi": ("BUILD-MANIFEST.json",),
        "datatrove": ("stats.json", "processing_stats.json"),
        "nemo-curator": ("metadata.json",),
        "dolma": ("manifest.json",),
    }
    for tool, names in candidates.items():
        for name in names:
            p = os.path.join(root, name)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        return {"tool": tool, "file": name,
                                "content_sha256": hashlib.sha256(
                                    open(p, "rb").read()).hexdigest(),
                                "cited_not_verified": True,
                                "raw": json.load(f)}
                except Exception:
                    return {"tool": tool, "file": name,
                            "cited_not_verified": True,
                            "note": "present but unparseable"}
    return None


def attest_corpus(root: str, corpus_id: str, registry_meta: dict | None = None,
                  accepted: list | None = None, scan=None) -> dict:
    """Compute an attestation over a directory of documents.

    scan: optional callable(doc_bytes) -> dict of counters, so the caller
    decides whether to pay for PII/toxicity measurement. Kept injectable so
    this module stays cheap to test and does not import the whole pipeline.
    """
    files = _corpus_files(root)
    hashes: list[int] = []
    n_docs = 0
    n_bytes = 0
    per_file = []
    counters: dict[str, int] = {}

    for path in files:
        f_docs = 0
        f_bytes = 0
        for _, doc in shards_mod.iter_docs(path):
            h = shards_mod.doc_hash64(doc)
            hashes.append(h)
            f_docs += 1
            f_bytes += len(doc)
            if scan is not None:
                for k, v in scan(doc).items():
                    counters[k] = counters.get(k, 0) + v
        n_docs += f_docs
        n_bytes += f_bytes
        per_file.append({
            "path": os.path.relpath(path, root),
            "docs": f_docs,
            "bytes": f_bytes,
        })

    arr = np.array(sorted(hashes), dtype=np.uint64) if hashes else np.empty(0, dtype=np.uint64)
    corpus_build_hash = hashlib.blake2b(arr.tobytes(), digest_size=32).hexdigest()
    unique = int(len(np.unique(arr))) if hashes else 0

    att = {
        "attestation_version": ATTESTATION_VERSION,
        "corpus_id": corpus_id,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),

        # --- what this attestation PROVES -------------------------------
        "corpus_build_hash": corpus_build_hash,
        "hash_definition": (
            "blake2b-256 over the ascending-sorted set of blake2b-8 document "
            "hashes — the identical definition a native Shuddhi build uses, so "
            "an attested corpus and a built corpus are directly comparable."
        ),
        "documents": n_docs,
        "unique_documents": unique,
        "exact_duplicate_rate": (round(1 - unique / n_docs, 6) if n_docs else 0.0),
        "bytes": n_bytes,
        "files": per_file,
        "content_scan": counters or None,

        # --- what it explicitly does NOT prove ---------------------------
        "provenance": _provenance_block(registry_meta, accepted),
        "limitations": [
            "Attestation proves CONTENT, not ACQUISITION. This receipt binds a "
            "corpus to a hash and reports what is inside it; it does not and "
            "cannot establish where the data came from, under what licence, or "
            "whether any rights-holder opted out.",
            "Upstream tool statistics, where present, are CITED and never "
            "verified. Shuddhi did not observe the upstream run.",
            "Absence of a finding is not proof of absence. Personal-data "
            "detection is pattern-based; toxicity screening is lexicon-tier.",
        ],
        "upstream": _upstream_manifest(root),
    }
    return att


def _provenance_block(registry_meta: dict | None, accepted: list | None) -> dict:
    """Provenance is declared, or it is UNKNOWN. It is never blank.

    A blank field in a compliance artefact reads as "nothing to declare".
    That misreading is the failure mode worth engineering against.
    """
    if not registry_meta or not accepted:
        return {
            "status": "UNKNOWN",
            "detail": (
                "No registry supplied. Source, licence, data class and "
                "acquisition date are unknown to this attestation. Re-run with "
                "--registry to attest against declared, refusal-checked "
                "provenance records."
            ),
            "sources": None,
        }
    return {
        "status": "DECLARED",
        "detail": (
            "Provenance taken from a Shuddhi registry, in which source, "
            "licence, data_class, language and date_acquired are required "
            "fields — a shard missing any of them is refused, not defaulted."
        ),
        "registry_sha256": registry_meta.get("registry_sha256"),
        "sources": [
            {"shard_id": s.shard_id, "source": s.source, "license": s.license,
             "data_class": s.data_class, "language": s.language,
             "date_acquired": s.date_acquired}
            for s in accepted
        ],
    }


def render_human(att: dict) -> str:
    """A short, honest summary for the terminal."""
    L = []
    L.append(f"corpus        {att['corpus_id']}")
    L.append(f"build hash    {att['corpus_build_hash']}")
    L.append(f"documents     {att['documents']:,}  ({att['unique_documents']:,} unique, "
             f"{att['exact_duplicate_rate']:.2%} exact duplicates)")
    L.append(f"size          {att['bytes']:,} bytes across {len(att['files'])} file(s)")
    if att.get("content_scan"):
        items = ", ".join(f"{k}={v:,}" for k, v in sorted(att["content_scan"].items()))
        L.append(f"content scan  {items}")
    up = att.get("upstream")
    if up:
        L.append(f"upstream      {up['tool']} ({up['file']}) — cited, not verified")
    prov = att["provenance"]
    L.append(f"provenance    {prov['status']}")
    if prov["status"] == "UNKNOWN":
        L.append("              ^ this attestation proves CONTENT, not ACQUISITION.")
        L.append("                Re-run with --registry to attest declared provenance.")
    return "\n".join(L)
