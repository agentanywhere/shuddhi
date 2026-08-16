import json

import factory
from extract import strip_tags

HTML = """<html><head><title>Page</title>
<script>var tracking = "evil";</script>
<style>.x { color: red }</style></head>
<body><!-- comment -->
<h1>The monsoon arrived</h1>
<p>Farmers in the region &amp; officials welcomed the rains after a long dry
spell that had threatened the sowing season across several districts.</p>
</body></html>"""


def test_strip_tags_removes_script_style_comments():
    text = strip_tags(HTML)
    assert "tracking" not in text and "color" not in text and "comment" not in text
    assert "The monsoon arrived" in text
    assert "&" in text  # entity decoded
    assert "&amp;" not in text


def test_extract_dir_end_to_end(tmp_path):
    src = tmp_path / "html"
    src.mkdir()
    (src / "a.html").write_text(HTML, encoding="utf-8")
    (src / "b.html").write_text("<p>too short</p>", encoding="utf-8")
    out = tmp_path / "shard.txt"
    rc = factory.main(["extract", "--in-dir", str(src), "--out", str(out)])
    assert rc == 0
    stats = json.loads((tmp_path / "shard.txt.extract.json").read_text())
    assert stats["input_files"] == 2
    assert stats["documents_written"] == 1
    assert stats["skipped_short"] == 1
    content = out.read_text(encoding="utf-8")
    assert content.endswith("\n\n")
    # produced shard parses with the factory's own doc iterator
    import shards

    docs = list(shards.iter_docs(str(out)))
    assert len(docs) == 1
    assert b"monsoon" in docs[0][1]
