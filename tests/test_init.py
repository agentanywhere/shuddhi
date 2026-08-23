"""`shuddhi init` — scaffolding a registry from files you already have.

The scaffold deliberately does NOT produce a usable registry: provenance
fields are empty, so `check` refuses every shard and names the missing
fields. A scaffold that quietly passed the gate would defeat the gate.
"""

import json

from shuddhi import cli as factory


def corpus_at(tmp_path, names=("news_eng.txt", "news_hin.txt")):
    d = tmp_path / "corpus"
    d.mkdir()
    for n in names:
        (d / n).write_text("a document\n\nanother document\n\n", encoding="utf-8")
    return d


def test_writes_one_entry_per_file(tmp_path):
    d = corpus_at(tmp_path)
    out = tmp_path / "r.json"
    assert factory.main(["init", "--corpus", str(d), "--out", str(out)]) == 0
    doc = json.loads(out.read_text())
    assert [s["shard_id"] for s in doc["shards"]] == ["news_eng", "news_hin"]
    assert doc["registry_version"] == 1


def test_provenance_is_left_empty_on_purpose(tmp_path):
    d = corpus_at(tmp_path)
    out = tmp_path / "r.json"
    factory.main(["init", "--corpus", str(d), "--out", str(out)])
    doc = json.loads(out.read_text())
    for s in doc["shards"]:
        for field in ("source", "license", "date_acquired", "data_class"):
            assert s[field] == "", f"{field} must be empty so the gate refuses it"


def test_the_scaffold_is_refused_until_filled(tmp_path, capsys):
    """The whole point: init's output cannot become a corpus on its own."""
    d = corpus_at(tmp_path)
    out = tmp_path / "r.json"
    factory.main(["init", "--corpus", str(d), "--out", str(out)])
    rc = factory.main(["check", "--registry", str(out)])
    assert rc == 2
    printed = capsys.readouterr().out
    assert "missing provenance field(s)" in printed
    assert "accepted: 0" in printed


def test_filling_it_in_makes_it_pass(tmp_path, capsys):
    d = corpus_at(tmp_path)
    out = tmp_path / "r.json"
    factory.main(["init", "--corpus", str(d), "--out", str(out)])
    doc = json.loads(out.read_text())
    for s in doc["shards"]:
        s.update(source="Example crawl", license="CC-BY-4.0",
                 date_acquired="2026-08-23", data_class="public")
    out.write_text(json.dumps(doc))
    assert factory.main(["check", "--registry", str(out)]) == 0
    assert "admissible and readable" in capsys.readouterr().out


def test_language_guessed_from_a_filename_suffix(tmp_path):
    d = corpus_at(tmp_path, names=("news_eng.txt", "reports_tam.txt", "misc.txt"))
    out = tmp_path / "r.json"
    factory.main(["init", "--corpus", str(d), "--out", str(out)])
    langs = {s["shard_id"]: s["language"] for s in json.loads(out.read_text())["shards"]}
    assert langs["news_eng"] == "eng"
    assert langs["reports_tam"] == "tam"
    assert langs["misc"] == "", "no suffix means no guess — do not invent one"


def test_explicit_language_overrides_the_guess(tmp_path):
    d = corpus_at(tmp_path, names=("news_eng.txt",))
    out = tmp_path / "r.json"
    factory.main(["init", "--corpus", str(d), "--out", str(out), "--language", "hin"])
    assert json.loads(out.read_text())["shards"][0]["language"] == "hin"


def test_will_not_clobber_an_existing_registry(tmp_path, capsys):
    d = corpus_at(tmp_path)
    out = tmp_path / "r.json"
    out.write_text('{"precious": true}')
    rc = factory.main(["init", "--corpus", str(d), "--out", str(out)])
    assert rc == 2
    assert "already exists" in capsys.readouterr().err
    assert json.loads(out.read_text()) == {"precious": True}, "must not overwrite"
    assert factory.main(["init", "--corpus", str(d), "--out", str(out), "--force"]) == 0


def test_a_missing_directory_suggests_one_that_exists(tmp_path, monkeypatch, capsys):
    """Sid pointed --corpus at ./corpus because the docs said so, and had no
    such folder. Being merely correct is not enough — name a real option."""
    monkeypatch.chdir(tmp_path)
    corpus_at(tmp_path, names=("a.txt",))
    rc = factory.main(["init", "--corpus", "./nope", "--out", "r.json"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no such directory" in err
    assert "--corpus corpus" in err, "should name a folder that actually exists"


def test_empty_directory_points_at_the_bundled_sample(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(tmp_path)
    rc = factory.main(["init", "--corpus", str(empty), "--out", "r.json"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no .txt files" in err and "extract" in err
