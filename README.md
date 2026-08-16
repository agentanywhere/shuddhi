# Shuddhi (शुद्धि) — Data Factory

**A receipts-first data factory for sovereign AI.** Shuddhi turns raw text
shards into a *filtered corpus build with a verifiable identity*: every
accepted document is content-hashed, every shard carries source/license/date
provenance, every filter threshold is pinned, and the whole build collapses
into one citable hash that a training run quotes in its ledger.

Internally the engine is the **Tatva Data Factory**; Shuddhi is the product.

> **Status: private.** This repository is internal (Bitbucket). The plan is to
> extract an open core to GitHub when the launch is right — see
> `PUBLIC-RELEASE-CHECKLIST.md`, which lists exactly what must change first
> (the eval set and VM-path configs must NOT ship publicly).

## The receipts chain

```
registry (source · license · date · data_class, per shard)
  → corpus_build_hash      content hash of the accepted document set
  → filter_config_sha      every threshold + the droplist/lexicon shas
  → filtered_build_hash    chained to both; the thing training cites
  → tokenizer sha          recorded alongside in the run ledger
```

Reproducible by construction: the same raw files and the same config yield
the same hashes on any machine. Ours were reproduced across four independent
full passes of a 176 GB corpus.

## What it does

| stage | module |
|---|---|
| Provenance gate — **customer-class data refused in code, no override** | `registry.py` |
| Streaming shard ingest, document hashing, shard SHA-256 | `shards.py` |
| Exact dedup (full corpus) | `dedup.py` |
| Near-dup — MinHash/LSH, disk-backed, deterministic exemplar | `neardup.py` |
| Language ID (fastText lid.176, script fallback) | `lid.py` |
| Quality heuristics | `quality.py` |
| Perplexity proxy (per-language char-trigram LM) | `ngram_lm.py` |
| Toxicity screen (lexicon tier, pluggable lists) | `toxicity.py` |
| PII scan + redact (email/phone/Aadhaar/PAN/Luhn cards/IP) | `pii.py` |
| Domain classifier (coding/bfsi/reasoning/indic/general) | `domain.py` |
| Contamination screen vs eval sets | `contamination.py` |
| Applied-filter builds + chained hash | `builder.py` |
| HTML → shard extraction | `extract.py` |
| Tokenizer train/eval lab | `tokenizer_lab.py` |

The provenance gate is the load-bearing guarantee: a shard that is untagged,
carries an unknown `data_class`, or is tagged `customer` / `customer-derived`
/ `evaluation-only` is refused **before its file is opened**, with no flag,
env var, or config field that can admit it. Unit-tested from five directions.

## Quickstart

```bash
pip install -e ".[lid,tokens,extract,dev]"
python3 -m pytest tests/ -q                      # 102 tests, no network

python3 factory.py check --registry configs/<registry>.json      # provenance gate
python3 factory.py run   --registry configs/<registry>.json \
    --shard <id> --out out/ --eval-set eval-set.jsonl \
    --fasttext-model lid.176.ftz --tokenizer tokenizer.json
python3 factory.py merge --registry configs/<registry>.json --out out/
python3 factory.py build --registry configs/<registry>.json \
    --run-dir out/ --build-out build/ --pii redact --toxicity
```

`docs/ENGINE-INTERNALS.md` documents every stage, flag, and the full-pass vs
sampled distinction. Builds parallelize by partition and the build hash is
provably unchanged by partitioning (`factory.py build-union`).

## Measured on a real corpus

Full results: `docs/MEASURED-REPORT.md`. Headline, from the 176 GB / 33.05M
document Tatva corpus on **one 2-vCPU box, zero GPU**:

| | |
|---|---|
| corpus build hash | `5e8fbb96…` (reproduced ×4) |
| filtered build hash | `a532e4ed…` — 32,289,800 docs kept (97.71%) |
| dropped | 0.38% exact-dup · 0.83% near-dup · 1.05% perplexity · 0.02% quality · 0.016% toxicity |
| contamination | 0, verified on every document |
| PII | 182,781 spans redacted |

Claims discipline is part of the product: every number carries its coverage
(full-pass vs sampled vs derived), and the report states what was *not*
measured. `docs/TOKENIZER-V2.md` is the companion tokenizer study.

## Repo map

```
factory.py            CLI: check · run · merge · build · build-union
                           neardup-sig · neardup-merge · train-lm · extract
*.py                  the stages (table above)
tests/                102 tests, tiny fixtures, no network
configs/              shard registries (INTERNAL paths — see checklist)
runs/                 measured manifests + composition reports
runs/tokenizer-v2/    tokenizer candidates + eval
docs/                 internals, measured report, tokenizer study
eval-set.jsonl        INTERNAL benchmark material — never publish
```
