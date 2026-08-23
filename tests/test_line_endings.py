"""A shard written on Windows must not silently become one document.

The record separator is a blank line. Written with CRLF that is b"\r\n\r\n",
which contains no b"\n\n" -- so splitting naively swallowed an entire shard
into a single document. It did not crash: it produced a clean receipt for a
corpus that had been misread. For a tool whose product IS the receipt, that
is the worst available failure mode, so it is pinned here from several angles.

Found by putting Windows in the CI matrix rather than assuming it worked.
"""

import hashlib

import pytest

from shuddhi.shards import doc_hash64, iter_docs, normalize_newlines

DOCS = ["First document.\nWith a second line.", "Second document.", "Third."]


def _write(path, sep, tail=""):
    body = sep.join(d.replace("\n", sep[: len(sep) // 2] or "\n") for d in DOCS)
    path.write_bytes((body + tail).encode("utf-8"))
    return str(path)


@pytest.mark.parametrize(
    "sep,name",
    [(b"\n\n", "unix"), (b"\r\n\r\n", "windows"), (b"\r\r", "classic-mac")],
)
def test_document_count_survives_every_line_ending(tmp_path, sep, name):
    p = tmp_path / f"{name}.txt"
    p.write_bytes(sep.join(d.encode("utf-8") for d in DOCS))
    docs = list(iter_docs(str(p)))
    assert len(docs) == 3, f"{name} endings collapsed the shard"


def test_crlf_and_lf_hash_identically(tmp_path):
    """The same documents must yield the same receipt on either platform."""
    lf = tmp_path / "lf.txt"
    lf.write_bytes(b"\n\n".join(d.encode("utf-8") for d in DOCS))
    crlf = tmp_path / "crlf.txt"
    crlf.write_bytes(
        b"\r\n\r\n".join(d.replace("\n", "\r\n").encode("utf-8") for d in DOCS)
    )
    assert [h for h, _ in ((doc_hash64(d), i) for i, d in iter_docs(str(lf)))] == [
        h for h, _ in ((doc_hash64(d), i) for i, d in iter_docs(str(crlf)))
    ]


def test_chunk_boundary_cannot_change_the_document_count(tmp_path):
    """A CRLF pair straddling a read boundary must not invent a blank line."""
    p = tmp_path / "crlf.txt"
    p.write_bytes(
        b"\r\n\r\n".join(d.replace("\n", "\r\n").encode("utf-8") for d in DOCS)
    )
    counts = {len(list(iter_docs(str(p), chunk_size=n))) for n in range(1, 64)}
    assert counts == {3}, f"chunk size changed the reading: {sorted(counts)}"


def test_trailing_bare_cr_is_not_lost(tmp_path):
    p = tmp_path / "tail.txt"
    p.write_bytes(b"Only document.\r")
    assert [d for _, d in iter_docs(str(p))] == [b"Only document."]


def test_provenance_checksum_still_covers_raw_bytes(tmp_path):
    """Normalisation is for splitting only -- the shard checksum is the file."""
    p = tmp_path / "crlf.txt"
    raw = b"A doc.\r\n\r\nB doc.\r\n"
    p.write_bytes(raw)
    h = hashlib.sha256()
    list(iter_docs(str(p), hasher=h))
    assert h.hexdigest() == hashlib.sha256(raw).hexdigest()


def test_normalize_is_identity_on_unix_data():
    """Pure-LF corpora must be untouched, so existing receipts still hold."""
    data = b"no carriage returns here\n\nat all\n"
    assert normalize_newlines(data) is data


def test_internal_lone_cr_does_not_split_a_document(tmp_path):
    """A lone CR inside text becomes a newline, not a record boundary."""
    p = tmp_path / "x.txt"
    p.write_bytes(b"line one\rline two\n\nsecond doc\n")
    docs = [d for _, d in iter_docs(str(p))]
    assert docs == [b"line one\nline two", b"second doc"]
