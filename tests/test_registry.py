"""Stage 1: the provenance gate. The customer-data exclusion is the hard
legal rule — these tests are the executable statement of it."""

import json

import pytest

from shuddhi import registry


def write_registry(tmp_path, shards):
    p = tmp_path / "reg.json"
    p.write_text(json.dumps({"registry_version": 1, "corpus_id": "t", "shards": shards}))
    return str(p)


def entry(**over):
    base = {
        "shard_id": "s1",
        "path": "/data/s1.txt",
        "source": "AI4Bharat Sangraha, verified subset",
        "license": "CC-BY-4.0",
        "date_acquired": "2026-07-24",
        "data_class": "public",
        "language": "hin",
    }
    base.update(over)
    return base


def test_accepts_fully_tagged_public_shard(tmp_path):
    _, accepted, refused = registry.load_registry(write_registry(tmp_path, [entry()]))
    assert [s.shard_id for s in accepted] == ["s1"]
    assert refused == []


@pytest.mark.parametrize("cls", ["customer", "customer-derived", "evaluation-only", "CUSTOMER"])
def test_customer_class_is_always_refused(tmp_path, cls):
    _, accepted, refused = registry.load_registry(write_registry(tmp_path, [entry(data_class=cls)]))
    assert accepted == []
    assert len(refused) == 1
    assert "never training" in refused[0].reason


def test_customer_class_refusal_has_no_override(tmp_path):
    """reviewed_by lifts the suspect-name check, but must NOT admit customer data."""
    e = entry(data_class="customer", reviewed_by="a-human")
    _, accepted, refused = registry.load_registry(write_registry(tmp_path, [e]))
    assert accepted == []
    assert "never training" in refused[0].reason


@pytest.mark.parametrize("missing", ["source", "license", "date_acquired", "data_class", "language"])
def test_untagged_shard_is_refused(tmp_path, missing):
    e = entry()
    del e[missing]
    _, accepted, refused = registry.load_registry(write_registry(tmp_path, [e]))
    assert accepted == []
    assert "untagged" in refused[0].reason


def test_unknown_data_class_is_refused(tmp_path):
    _, accepted, refused = registry.load_registry(
        write_registry(tmp_path, [entry(data_class="probably-fine")])
    )
    assert accepted == []
    assert "unknown data_class" in refused[0].reason


def test_suspect_name_needs_named_reviewer(tmp_path):
    e = entry(shard_id="pilot_customer_dump", path="/data/pilot_customer_dump.txt")
    _, accepted, refused = registry.load_registry(write_registry(tmp_path, [e]))
    assert accepted == []
    assert "suspect provenance" in refused[0].reason

    e["reviewed_by"] = "sid"
    _, accepted, refused = registry.load_registry(write_registry(tmp_path, [e]))
    assert [s.shard_id for s in accepted] == ["pilot_customer_dump"]


def test_refusal_never_opens_the_file(tmp_path):
    """Admission is decided on the ledger alone — the path need not exist."""
    e = entry(data_class="customer", path="/does/not/exist/anywhere.txt")
    _, accepted, refused = registry.load_registry(write_registry(tmp_path, [e]))
    assert accepted == [] and len(refused) == 1


def test_duplicate_shard_id_refused(tmp_path):
    _, accepted, refused = registry.load_registry(
        write_registry(tmp_path, [entry(), entry()])
    )
    assert len(accepted) == 1 and len(refused) == 1
    assert "duplicate" in refused[0].reason


def test_registry_sha_is_recorded(tmp_path):
    meta, _, _ = registry.load_registry(write_registry(tmp_path, [entry()]))
    assert len(meta["registry_sha256"]) == 64
