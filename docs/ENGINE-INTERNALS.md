# Tatva Data Factory v1

The reusable dataset-cleansing engine for the Tatva from-scratch lane — and
for every future corpus we train on. It turns raw text shards into a
**provenance-receipted corpus build**: every accepted document is tracked by
content hash, every shard by SHA-256 + source/license/date, and the whole
build collapses into one citable `corpus_build_hash`. Training-side receipts,
the same discipline our serving side already has.

Design follows §5 ("the cheapest useless token is the one you never train")
and §14 (data metrics) of the DeepSeek learnings brief: dedup, quality
scoring, language ID, domain classification, provenance and contamination
checks — as infrastructure, not one-off scripts.

## Stages

| # | Stage | Module | Coverage |
|---|---|---|---|
| 1 | Ingest + provenance ledger | `registry.py` | every shard, before its file is opened |
| 2 | Language ID (fastText lid.176, script fallback) | `lid.py` | sampled |
| 3 | Dedup — exact (64-bit content hash) | `shards.py` + `dedup.py` | **full corpus** |
| 3b| Dedup — near (MinHash 32-perm, LSH 8×4, verified) | `dedup.py` | sampled |
| 4 | Quality scoring v1 (heuristics, documented thresholds) | `quality.py` | sampled |
| 5 | Domain classifier v1 (coding/bfsi/reasoning/indic/general) | `domain.py` | sampled |
| 6 | Contamination vs our eval sets (8-gram, string-verified) | `contamination.py` + `build_eval_set.py` | sampled |
| 7 | Build manifest + composition report | `factory.py merge` | — |
| 8 | PII scan/redact (email, phone, Aadhaar, PAN, Luhn-checked cards, IP) | `pii.py` | sampled; full-doc on build |
| 9 | Perplexity proxy (per-language char-trigram LM, bits/char) | `ngram_lm.py` | sampled; per-doc on build |
| 10| **Applied-filter builds** with chained hash | `builder.py` / `factory.py build` | full corpus |
| 11| **Applied near-dup** (full-corpus MinHash/LSH, disk-backed, deterministic exemplar) | `neardup.py` | full corpus |
| 12| Toxicity screen (lexicon tier, external lists pluggable + sha-pinned) | `toxicity.py` | per-doc on build |
| 13| Extraction (HTML → shard text; trafilatura or fallback) | `extract.py` | — |

v1.2 near-dup + toxicity flow:

```bash
for s in <shards>; do python3 factory.py neardup-sig --registry R --shard $s --sig-dir sigs/; done
python3 factory.py neardup-merge --registry R --run-dir out/ --sig-dir sigs/ --out neardup-drop.u64
python3 factory.py build ... --neardup-drop neardup-drop.u64 --toxicity
```

**The provenance gate is mechanical.** A shard is refused — before its file
is ever opened — if it is untagged, carries an unknown `data_class`, or is
tagged `customer` / `customer-derived` / `evaluation-only`. Customer data is
evaluation-only, never training: that rule is code with **no override path**
(`registry.py::_refusal_reason`, forbidden-class check first, unconditional
return). Suspiciously-named shards claiming a trainable class additionally
require a named human reviewer.

**Full-pass vs sampled, never mixed silently.** Shard SHA-256, document
counts, and exact-dedup run over every byte. LID, quality, domain, near-dup,
contamination and token ratios run on a deterministic index-stride sample and
always report their exact coverage.

**The build hash.** `corpus_build_hash` = blake2b-256 over the sorted set of
unique 64-bit document hashes across accepted shards. Order-independent,
reproducible from the raw files, cheap to verify. Every training run that
consumes a corpus build cites this hash in its run ledger — that is the
contract.

## Running

```bash
# validate the ledger (exit 2 if anything is refused)
python3 factory.py check --registry configs/reference-sangraha.json

# process one shard (all stages, one streaming pass)
python3 factory.py run --registry configs/reference-sangraha.json \
  --shard sangraha_hin --out out/ \
  --eval-set eval-set.jsonl --fasttext-model lid.176.ftz \
  --tokenizer tokenizer.json

# merge all shard outputs into MANIFEST.json + COMPOSITION.md
python3 factory.py merge --registry configs/reference-sangraha.json --out out/

# train per-language perplexity-proxy LMs (once per corpus)
python3 factory.py train-lm --registry configs/reference-sangraha.json \
  --shard sangraha_hin --lm-dir lms/

# applied-filter build over the MEASURED run (run -> merge -> build):
# exact-dedup keep-first, quality >= 0.5, per-language ppx cutoff at the
# measured p99, PII redaction, contamination drop. --emit none produces the
# hash-only manifest; --emit text also writes the filtered shards.
python3 factory.py build --registry configs/reference-sangraha.json \
  --run-dir out/ --build-out build/ --lm-dir lms/ --ppx-percentile 99 \
  --pii redact --eval-set eval-set.jsonl --emit none
```

**The chained hash.** A build's `filtered_build_hash` is computed with the
same definition as the parent `corpus_build_hash` and recorded alongside the
parent hash + the sha256 of the exact filter config. Same raw files + same
config ⇒ same filtered hash, emission or not. Build also verifies integrity:
every document hash must exist in the measured run's set, so a shard that
changed after measurement fails the build loudly.

`run_all.sh` drives all 15 Sangraha shards with 2 workers on the LLM VM
(CPU-only; the corpus lives there, so no Blob egress is spent).

Dependencies: numpy (required for dedup/merge); `fasttext-predict` (LID,
optional — falls back to Unicode-script ID and says so in the stats);
`tokenizers` (token ratios, optional). All pip wheels, no compilers.

Defaults: sample stride 50 (2% of documents), MinHash on every 4th sampled
doc, token ratio on every 20th sampled doc up to 30 MB/shard. Tune per run;
every stats file records the strides it ran with.

## Tests

```bash
python3 -m pytest tests/ -q     # 80 tests, tiny fixtures, no network
```

## Outputs

- `out/<shard>.stats.json` — per-shard receipts: provenance echo, sha256,
  full-pass counts, sampled metrics, timing.
- `out/<shard>.hashes.u64` — the shard's document content hashes (raw uint64),
  input to global dedup and to any future incremental build.
- `out/MANIFEST.json` — the corpus build manifest (the thing training runs cite).
- `out/COMPOSITION.md` — human-readable composition tables.

First production report: `portfolio/DATA-FACTORY-V1.md`.
