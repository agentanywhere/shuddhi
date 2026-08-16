import json
import os

import pytest

import tokenizer_lab
from tokenizer_lab import sample_shard

DOC = "this is document number {} with some ordinary words repeated for size padding. "


def write_shard(tmp_path, n_docs=400):
    p = tmp_path / "shard.txt"
    p.write_bytes(b"\n\n".join((DOC.format(i) * 3).encode() for i in range(n_docs)) + b"\n\n")
    return str(p)


def test_sampler_deterministic_and_boundary_clean(tmp_path):
    p = write_shard(tmp_path)
    a = sample_shard(p, budget_bytes=4000, chunks=4, phase=0)
    b = sample_shard(p, budget_bytes=4000, chunks=4, phase=0)
    assert a == b and len(a) > 0
    # every sampled doc is a complete document (starts with the known prefix)
    assert all(d.startswith(b"this is document number") for d in a)


def test_phases_are_disjoint(tmp_path):
    p = write_shard(tmp_path)
    train = set(sample_shard(p, budget_bytes=3000, chunks=4, phase=0))
    held = set(sample_shard(p, budget_bytes=3000, chunks=4, phase=1))
    assert train and held
    assert not (train & held)


def test_sample_cmd_writes_recipe(tmp_path):
    shard = write_shard(tmp_path)
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "t",
        "shards": [{"shard_id": "s", "path": shard, "source": "fixture",
                    "license": "CC-BY-4.0", "date_acquired": "2026-08-13",
                    "data_class": "public", "language": "eng"}],
    }))
    out = tmp_path / "samples"
    assert tokenizer_lab.main(["sample", "--registry", str(reg), "--out-dir", str(out),
                               "--mb-per-lang", "0.01", "--chunks", "4"]) == 0
    recipe = json.loads((out / "SAMPLE-RECIPE.json").read_text())
    assert recipe["languages"]["eng"]["docs"] > 0
    assert len(recipe["languages"]["eng"]["sha256"]) == 64
    assert (out / "eng.txt").exists()


@pytest.mark.skipif(
    not pytest.importorskip("tokenizers", reason="tokenizers not installed"),
    reason="tokenizers not installed",
)
def test_train_and_eval_end_to_end(tmp_path):
    shard = write_shard(tmp_path, n_docs=800)
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({
        "registry_version": 1, "corpus_id": "t",
        "shards": [{"shard_id": "s", "path": shard, "source": "fixture",
                    "license": "CC-BY-4.0", "date_acquired": "2026-08-13",
                    "data_class": "public", "language": "eng"}],
    }))
    train_dir, held_dir, tok_dir = tmp_path / "tr", tmp_path / "he", tmp_path / "tok"
    for phase, d in ((0, train_dir), (1, held_dir)):
        assert tokenizer_lab.main(["sample", "--registry", str(reg), "--out-dir", str(d),
                                   "--mb-per-lang", "0.02", "--chunks", "4",
                                   "--phase", str(phase)]) == 0
    assert tokenizer_lab.main(["train", "--sample-dir", str(train_dir),
                               "--out-dir", str(tok_dir), "--vocab-sizes", "400"]) == 0
    cand = tok_dir / "tatva-tok-v2-0k.json"
    assert cand.exists()
    assert tokenizer_lab.main(["eval", "--incumbent", str(cand),
                               "--candidates", str(cand),
                               "--heldout-dir", str(held_dir),
                               "--out-dir", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "TOKENIZER-EVAL.json").read_text())
    assert report["bytes_per_token"]["incumbent-32k"]["eng"] > 1.0
