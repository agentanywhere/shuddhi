# CLI Reference

```
shuddhi <command> [options]
docker run --rm shuddhi <command> [options]
```

Every command is safe to re-run. Nothing ever writes to your raw shards.

**Exit codes:** `0` success · `1` environment not ready (`doctor`) · `2`
refused or misconfigured (also every user-facing error: a missing file,
malformed JSON, a path typo — each prints a sentence and a next step rather
than a traceback; set `SHUDDHI_TRACEBACK=1` to see the stack) · `130`
interrupted — a refused shard, a missing shard output without
`--partial`, or incompatible partitions.

---

## `doctor`

Reports the interpreter, the active venv/conda environment, which packages
are importable, and which optional data files are present. Run this first
whenever something behaves oddly.

Exits `1` if a required package is missing, and prints the exact
install command for *that* interpreter.

---

## `init --corpus <dir> [--out registry.json]`

Scaffolds a registry from a directory of `.txt` shards: one entry per file,
`shard_id` from the filename, and a language guessed from a suffix like
`news_eng.txt`.

| flag | default | meaning |
|---|---|---|
| `--corpus` | required | directory holding your text shards |
| `--out` | `registry.json` | where to write |
| `--corpus-id` | folder name | the corpus's name |
| `--language` | guessed | ISO 639-3 code applied to every shard |
| `--force` | off | overwrite an existing file |

Provenance fields are written **empty on purpose**. An empty field is
refused by `check`, which names it — so the scaffold cannot become a corpus
until a human says where the data came from.

---

## `check --registry <file>`

Validates the registry, prints the provenance ledger plus every refusal
with its reason, and confirms each accepted shard's file exists and is not
empty — a `stat`, not a read, so a refused shard is still never opened.
Catching a path typo here rather than at `run` means it surfaces where you
are already looking. **Exits `2` if anything was refused** —
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
shuddhi neardup-sig   --registry R --shard S --sig-dir sigs/
shuddhi neardup-merge --registry R --run-dir run/ --sig-dir sigs/ --out neardup-drop.u64
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
| `--plugin` | — | enable an installed filter plugin (repeatable); its identity enters the config sha |
| `--shards` | all | comma list, for partition builds |
| `--emit` | `none` | `none` = manifest only; `text` = write filtered shards |

Writes `BUILD-MANIFEST.json`, `<shard>.kept.u64`, and with `--emit text`,
`<shard>.filtered.txt`. Fails if any document is absent from the measured
run's hash set (a shard changed after measurement).

---

## `ui --dir <dir> [--port 8765] [--no-open]`

Serves a local viewer over the builds in a directory: history, receipts,
per-shard measurements, drops by reason, warnings and errors, live progress,
and downloads. Binds to 127.0.0.1 and reads only the filesystem you point it
at. Zero dependencies.

---

## `pipeline --registry <file> --out <dir>`

Runs the whole pipeline in the correct order with one command: language
models, measurement, corpus manifest, near-duplicate clustering, filtering,
report and receipt. See the [Quickstart](QUICKSTART.md#build-it--one-command).

| flag | default | meaning |
|---|---|---|
| `--emit` | `text` | `text` writes the cleaned corpus; `none` is manifest-only |
| `--no-perplexity` | off | skip the language models and perplexity filter |
| `--no-neardup` | off | skip near-duplicate clustering |
| `--no-toxicity` | off | skip the toxicity screen |
| `--allow-refusals` | off | proceed with accepted shards when the registry has refusals |

Every `build` and `run` flag has an equivalent here.

---

## Progress output

Progress adapts to where it is going. On a terminal you get a live bar with a
rate and an ETA; piped to a file, to `docker logs`, or to CI you get
timestamped lines every 15 seconds with no cursor tricks or escape codes.
Override with `SHUDDHI_PROGRESS=tty|plain|none`; `NO_COLOR` and `TERM=dumb`
are honoured, and a non-UTF-8 terminal falls back to ASCII bar characters.

Every run also appends `events.jsonl` to its output directory — phases,
progress, warnings and errors, machine-readable. That file is what the
viewer reads, so the UI is a view over the log the run already wrote rather
than a second implementation of progress.

---

## `plugins`

Lists installed filter plugins with their versions and identities. See
[Extending](EXTENDING.md).

---

## `attest` — fingerprint a corpus you did not build here

Produces a receipt for a corpus produced by another tool (NeMo Curator,
DataTrove, Dolma, your own scripts), using the **same hash definition** a
native build uses, so the two are comparable and verifiable the same way.

| flag | default | meaning |
|---|---|---|
| `--corpus` | required | directory of documents to attest |
| `--corpus-id` | required | the name this corpus is known by |
| `--registry` | — | attest against declared provenance instead of `UNKNOWN` |
| `--scan` | off | also measure PII and toxicity across the corpus |
| `--out` | stdout | write `ATTESTATION.json` here |

An attestation proves **content, not acquisition**: it binds a corpus to a
hash and reports what is inside it. Without `--registry`, provenance fields
read `UNKNOWN` rather than blank — a blank reads as "nothing to declare",
which is the dangerous misreading. If the producing tool left a manifest it
is *cited, never verified* — we did not observe that run.

---

## `report` — regulatory summary from a build

| flag | default | meaning |
|---|---|---|
| `--registry` | required | the registry whose provenance is summarised |
| `--eu-ai-act` | off | use the EU AI Office template shape (Article 53(1)(d)) |
| `--manifest` | — | `BUILD-MANIFEST.json`, binding the summary to a reproducible build |
| `--out` | stdout | write here instead of stdout |

Pass the `BUILD-MANIFEST.json` that `build` writes, not the corpus
`MANIFEST.json` that `run` writes — only the former records a filter
configuration, and a training-content summary that cannot name the filters
is describing a corpus nobody built.

Nothing is computed specially for this: `source`, `license`, `data_class`,
`language` and `date_acquired` are already required registry fields, so the
summary is a projection of what admission recorded.

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
