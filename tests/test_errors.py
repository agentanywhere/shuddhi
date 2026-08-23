"""User-facing failure modes.

A stack trace is the right answer for a bug and the wrong answer for a
typo. These tests pin the difference: expected failures produce a sentence
and a next step with exit 2, and anything unrecognised still raises so the
bug report survives.

Every case here was hit by a real person following the guide.
"""

import json

import pytest

from shuddhi import cli as factory
from shuddhi.cli import UserError, _explain


def run(capsys, argv) -> tuple[int, str]:
    rc = factory.main(argv)
    return rc, capsys.readouterr().err


def test_missing_registry_explains_instead_of_tracebacking(tmp_path, capsys):
    rc, err = run(capsys, ["check", "--registry", str(tmp_path / "nope.json")])
    assert rc == 2
    assert "registry file not found" in err
    assert "cp examples/registry.json" in err          # the next step
    assert "Traceback" not in err


def test_malformed_json_points_at_the_line(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"registry_version": 1, "shards": [],}')
    rc, err = run(capsys, ["check", "--registry", str(bad)])
    assert rc == 2
    assert "is not valid JSON" in err
    assert "line" in err and "column" in err


def test_check_catches_a_path_typo(tmp_path, capsys):
    """The gate should fail on an unreadable shard, not leave it for `run`."""
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "x",
        "shards": [{"shard_id": "a", "path": str(tmp_path / "typo.txt"),
                    "source": "s", "license": "CC0-1.0",
                    "date_acquired": "2026-08-23", "data_class": "public",
                    "language": "eng"}],
    }))
    rc, err = run(capsys, ["check", "--registry", str(reg)])
    assert rc == 2
    assert "no such file" in err and "a:" in err


def test_check_catches_an_empty_shard(tmp_path, capsys):
    (tmp_path / "empty.txt").write_text("")
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "x",
        "shards": [{"shard_id": "a", "path": str(tmp_path / "empty.txt"),
                    "source": "s", "license": "CC0-1.0",
                    "date_acquired": "2026-08-23", "data_class": "public",
                    "language": "eng"}],
    }))
    rc, err = run(capsys, ["check", "--registry", str(reg)])
    assert rc == 2
    assert "file is empty" in err


def test_check_passes_cleanly_when_everything_is_fine(tmp_path, capsys):
    shard = tmp_path / "s.txt"
    shard.write_text("a document\n\n")
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "x",
        "shards": [{"shard_id": "a", "path": str(shard), "source": "s",
                    "license": "CC0-1.0", "date_acquired": "2026-08-23",
                    "data_class": "public", "language": "eng"}],
    }))
    rc = factory.main(["check", "--registry", str(reg)])
    assert rc == 0
    assert "admissible and readable" in capsys.readouterr().out


def test_build_before_measuring_names_the_missing_step(tmp_path, capsys):
    reg = tmp_path / "r.json"
    reg.write_text(json.dumps({"registry_version": 1, "corpus_id": "x", "shards": []}))
    rc, err = run(capsys, ["build", "--registry", str(reg),
                           "--run-dir", str(tmp_path / "run"),
                           "--build-out", str(tmp_path / "b")])
    assert rc == 2
    assert "MANIFEST.json not found" in err
    assert "shuddhi run" in err and "shuddhi merge" in err


def test_a_missing_language_model_suggests_the_fix():
    msg, hint = _explain(FileNotFoundError(2, "No such file", "lms/eng.lm.gz"))
    assert "language model not found" in msg
    assert "train-lm" in hint and "--no-perplexity" in hint


def test_user_error_carries_its_hint():
    msg, hint = _explain(UserError("something specific", "do this instead"))
    assert msg == "something specific" and hint == "do this instead"


def test_permission_error_mentions_the_docker_case():
    _msg, hint = _explain(PermissionError(13, "Permission denied", "/work/out"))
    assert "id -u" in hint


@pytest.mark.parametrize("exc", [ValueError("bug"), KeyError("bug"), TypeError("bug")])
def test_unexpected_exceptions_are_not_swallowed(exc):
    """An unrecognised exception is a BUG. Hiding it would waste the only
    report we get about it."""
    assert _explain(exc) is None
