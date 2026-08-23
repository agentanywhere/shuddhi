"""Streaming document iteration over blank-line-separated shard files.

The record separator is a blank line, so a "document" throughout the factory
means one separator-delimited block. Documents may contain internal single
newlines; a document that contained an internal blank line would count as two
records — that is the writer's contract, and counts are reported against it.

**Line endings are normalised before splitting.** A shard written on Windows
separates its documents with `\\r\\n\\r\\n`, which contains no `\\n\\n`, so a
naive split would swallow the whole file as a single document — silently, and
with a clean-looking receipt. Since that is the worst failure mode a receipts
tool can have, CRLF and lone-CR endings are folded to LF on the way in.

That also buys a stronger guarantee than tolerance: the same logical corpus
now hashes identically whether its files carry Unix or Windows endings, so a
receipt can be recomputed on a different platform from the same documents.
The shard's provenance checksum still covers the RAW bytes, unnormalised, so
the file itself is still identified exactly as it sits on disk.

Iteration is streaming (bounded memory) and deterministic: documents are
yielded in file order with a zero-based index, so index-stride sampling is
reproducible for a given file.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

SEPARATOR = b"\n\n"


def normalize_newlines(data: bytes) -> bytes:
    """Fold CRLF and lone CR to LF. No-op (and no copy) on Unix-ending data."""
    if b"\r" not in data:
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def iter_docs(path: str, chunk_size: int = 1 << 23, hasher=None) -> Iterator[tuple[int, bytes]]:
    """Yield (doc_index, doc_bytes) for every document in the shard.

    doc_bytes is stripped of surrounding whitespace; empty blocks are skipped
    (and do not consume an index). If `hasher` is given (e.g. hashlib.sha256()),
    it is updated with the raw file bytes during the same pass, so the shard
    checksum costs no second read of a multi-GB file.
    """
    idx = 0
    buf = b""
    pending_cr = False
    with open(path, "rb", buffering=1 << 20) as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            if hasher is not None:
                hasher.update(data)  # raw bytes: the provenance checksum
            # A CRLF pair can straddle a chunk boundary. Carrying the trailing
            # CR keeps normalisation identical to a single-chunk read -- without
            # this, a boundary CR would become its own LF and invent a blank
            # line, so chunk_size would change the document count.
            if pending_cr:
                data = b"\r" + data
                pending_cr = False
            if data.endswith(b"\r"):
                data = data[:-1]
                pending_cr = True
            buf += normalize_newlines(data)
            parts = buf.split(SEPARATOR)
            buf = parts.pop()  # tail may be an incomplete document
            for part in parts:
                doc = part.strip()
                if doc:
                    yield idx, doc
                    idx += 1
    if pending_cr:  # file ended on a bare CR
        buf += b"\n"
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
