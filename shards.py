"""Streaming document iteration over blank-line-separated shard files.

The Sangraha extraction (`build_big_corpus.py` on the LLM VM) writes each
document as `doc.strip() + "\\n\\n"`, so the record separator is a blank line.
A "document" throughout the factory means one such separator-delimited block.
Documents may contain internal single newlines; a document that contained an
internal blank line would count as two records — that is the writer's contract,
and counts are reported against it.

Iteration is streaming (bounded memory) and deterministic: documents are
yielded in file order with a zero-based index, so index-stride sampling is
reproducible for a given file.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

SEPARATOR = b"\n\n"


def iter_docs(path: str, chunk_size: int = 1 << 23, hasher=None) -> Iterator[tuple[int, bytes]]:
    """Yield (doc_index, doc_bytes) for every document in the shard.

    doc_bytes is stripped of surrounding whitespace; empty blocks are skipped
    (and do not consume an index). If `hasher` is given (e.g. hashlib.sha256()),
    it is updated with the raw file bytes during the same pass, so the shard
    checksum costs no second read of a multi-GB file.
    """
    idx = 0
    buf = b""
    with open(path, "rb", buffering=1 << 20) as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            if hasher is not None:
                hasher.update(data)
            buf += data
            parts = buf.split(SEPARATOR)
            buf = parts.pop()  # tail may be an incomplete document
            for part in parts:
                doc = part.strip()
                if doc:
                    yield idx, doc
                    idx += 1
    doc = buf.strip()
    if doc:
        yield idx, doc


def doc_hash64(doc: bytes) -> int:
    """64-bit content hash of a document (blake2b-8), used for exact dedup.

    With ~10^8 documents the expected number of 64-bit birthday collisions is
    ~10^-3 — negligible for dedup-rate measurement. blake2b is deterministic
    across runs, machines, and Python versions (unlike built-in hash()).
    """
    return int.from_bytes(hashlib.blake2b(doc, digest_size=8).digest(), "big")


def file_sha256(path: str) -> str:
    """SHA-256 of the raw shard file (provenance receipt). Streaming."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1 << 22)
            if not block:
                break
            h.update(block)
    return h.hexdigest()
