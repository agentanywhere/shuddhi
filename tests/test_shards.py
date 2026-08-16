import hashlib

import shards


def write(tmp_path, blob: bytes):
    p = tmp_path / "shard.txt"
    p.write_bytes(blob)
    return str(p)


def test_blank_line_separated_docs(tmp_path):
    p = write(tmp_path, b"doc one line a\ndoc one line b\n\ndoc two\n\n")
    docs = list(shards.iter_docs(p))
    assert docs == [(0, b"doc one line a\ndoc one line b"), (1, b"doc two")]


def test_empty_blocks_are_skipped(tmp_path):
    p = write(tmp_path, b"a\n\n\n\n\n\nb\n\n")
    docs = [d for _, d in shards.iter_docs(p)]
    assert docs == [b"a", b"b"]


def test_docs_across_chunk_boundary(tmp_path):
    # Force the separator to straddle the read boundary.
    doc_a = b"x" * 100
    doc_b = b"y" * 100
    p = write(tmp_path, doc_a + b"\n\n" + doc_b + b"\n\n")
    docs = [d for _, d in shards.iter_docs(p, chunk_size=101)]
    assert docs == [doc_a, doc_b]


def test_trailing_doc_without_separator(tmp_path):
    p = write(tmp_path, b"a\n\nlast doc no trailing sep")
    docs = [d for _, d in shards.iter_docs(p)]
    assert docs == [b"a", b"last doc no trailing sep"]


def test_inline_hasher_matches_file_sha256(tmp_path):
    blob = b"alpha\n\nbeta\n\ngamma\n\n" * 1000
    p = write(tmp_path, blob)
    h = hashlib.sha256()
    list(shards.iter_docs(p, chunk_size=97, hasher=h))
    assert h.hexdigest() == hashlib.sha256(blob).hexdigest()
    assert h.hexdigest() == shards.file_sha256(p)


def test_doc_hash64_deterministic_and_distinct():
    a = shards.doc_hash64(b"some document text")
    assert a == shards.doc_hash64(b"some document text")
    assert a != shards.doc_hash64(b"some document text!")
    assert 0 <= a < 2**64
