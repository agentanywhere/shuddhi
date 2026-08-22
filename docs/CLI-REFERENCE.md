# CLI Reference

```
python3 factory.py <command> [options]
docker run --rm shuddhi <command> [options]
```

Every command is safe to re-run. Nothing ever writes to your raw shards.

**Exit codes:** `0` success · `1` environment not ready (`doctor`) · `2`
refused or misconfigured — a refused shard, a missing shard output without
`--partial`, or incompatible partitions.

---

## `doctor`

Reports the interpreter, the active venv/conda environment, which packages
are importable, and which optional data files are present. Run this first
whenever something behaves oddly.

Exits `1` if a required package is missing, and prints the exact
install command for *that* interpreter.

---

## `check --registry <file>`

Validates the registry and prints the provenance ledger plus every refusal
with its reason. Opens no shard files. **Exits `2` if anything was refused** —
suitable as a CI gate.

---

## `run` — measure one shard

| flag | default | meaning |
|---|---|---|
| `--registry` | required | registry file |
| `--shard` | required | `shard_id` to process |
| `--out` | required | output directory (shared across shards) |
| `--sample-every` | `50` | sampling stride; 50 = 2% of documents |
| `--minhash-every` | `4` | MinHash every Nth *sampled* document |
| `--token-every` | `20` | token-ratio measurement every Nth sampled document |
| `--token-byte-budget` | `30000000` | stop token measurement after this many bytes |
| `--max-docs` | `0` (all) | stop after N documents (smoke tests; marks the run truncated) |
| `--eval-set` | — | JSONL eval items for contamination screening |
| `--fasttext-model` | — | `lid.176.ftz`; without it, Unicode-script fallback |
| `--tokenizer` | — | HuggingFace `tokenizer.json` for bytes/token |
| `--lm` | — | `<lang>.lm.gz` to record a perplexity distribution |
| `--pii-scan` | off | count PII occurrences on sampled documents |

Writes `<out>/<shard>.stats.json` and `<out>/<shard>.hashes.u64`.
Shards are independent — run them in parallel.

---

## `merge --registry <file> --out <dir>`

Combines per-shard outputs, deduplicates globally, mints `corpus_build_hash`,
and writes `MANIFEST.json` + `COMPOSITION.md`.

`--partial` allows merging a subset; the missing shards are recorded in the
manifest. Without it, an incomplete corpus exits `2`.

---

## `train-lm` — perplexity model for one shard

| flag | default | meaning |
|---|---|---|
| `--registry` `--shard` `--lm-dir` | required | model is written to `<lm-dir>/<language>.lm.gz` |
| `--sample-every` | `200` | sampling stride for training text |
| `--max-mb` | `20` | training-text budget |

Run **before** `run`, and pass the model to `run --lm`, so the measurement
records a distribution for `build` to threshold on.

---

## `neardup-sig` / `neardup-merge`

```bash
factory.py neardup-sig   --registry R --shard S --sig-dir sigs/
factory.py neardup-merge --registry R --run-dir run/ --sig-dir sigs/ --out neardup-drop.u64
```

`neardup-sig` writes MinHash signatures for every document of one shard
(parallelisable). `neardup-merge` clusters across all shards and writes the
sorted drop list plus `<out>.stats.json`. Signature counts must match the
measured run, or it fails loudly.

---

## `build` — apply the filters

| flag | default | meaning |
|---|---|---|
| `--registry` | required | registry file |
| `--run-dir` | required | directory from `run` + `merge` |
| `--build-out` | required | output directory |
| `--min-quality` | `0.5` | drop documents scoring below this |
| `--lm-dir` | — | `<lang>.lm.gz` models; enables the perplexity filter |
| `--ppx-percentile` | `99` | cutoff percentile (`50`, `90`, `99`) |
| `--neardup-drop` | — | drop list from `neardup-merge` |
| `--toxicity` | off | drop lexicon-flagged documents |
| `--toxicity-lexicon-dir` | — | `<lang>.txt` lists merged with the built-ins |
| `--eval-set` | — | drop contaminated documents |
| `--pii` | `redact` | `keep` · `redact` · `drop` |
| `--shards` | all | comma list, for partition builds |
| `--emit` | `none` | `none` = manifest only; `text` = write filtered shards |

Writes `BUILD-MANIFEST.json`, `<shard>.kept.u64`, and with `--emit text`,
`<shard>.filtered.txt`. Fails if any document is absent from the measured
run's hash set (a shard changed after measurement).

---

## `build-union --build-outs <a,b,...> --out <dir>`

Unions disjoint partition builds into one manifest. The result is identical
to a single sequential build. Exits `2` if partitions disagree on parent
hash, filter config, or overlap in shards.

---

## `extract --in-dir <dir> --out <file>`

Converts a directory of `.html`/`.htm` files into a blank-line-separated
shard. `--min-chars` (default `80`) skips near-empty results. Uses
trafilatura when installed, otherwise a tag-stripping fallback; the
extractor used is recorded in `<out>.extract.json`.

---

## Container verbs

`demo` runs the sample pipeline, `test` runs the suite, `shell` opens bash.
Anything else is passed to the CLI unchanged.
