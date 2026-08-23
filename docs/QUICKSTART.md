# Quickstart

From nothing to a corpus you can prove the contents of. No GPU, no account,
no network calls.

---

## 1. See it work — 30 seconds

```bash
docker run --rm ghcr.io/agentanywhere/shuddhi:1.2.0 demo
```

That runs the whole pipeline over a bundled sample corpus which has defects
**deliberately planted in it**, so every filter visibly catches something:

```
kept 34 of 42 documents; 5 PII spans redacted
dropped by reason: {'exact_dup': 1, 'near_dup': 2, 'quality': 1,
                    'perplexity': 2, 'toxicity': 1, 'contamination': 1, 'pii': 0}
refused at the gate: ['customer_export']
```

Three hashes print at the end. **Run it again — they do not change**, and
they are identical on macOS, on Linux, and inside the container.

Two things in that output are worth understanding now, because they are the
whole product:

- **`customer_export` was refused before its file was opened.** It is tagged
  `data_class: "customer"` in the registry, and there is no flag, env var or
  config field that admits it. Try to find one.
- **`'pii': 0` does not mean no PII was found.** It means none was *dropped* —
  the policy is redact, so five spans were rewritten to `[PII:email]`,
  `[PII:phone_in]` and so on in the emitted text.

---

## 2. Install

Only needed to run Shuddhi on your own data. Pick one.

### Docker

```bash
docker pull ghcr.io/agentanywhere/shuddhi:1.2.0
docker run --rm ghcr.io/agentanywhere/shuddhi:1.2.0 doctor
```

Multi-architecture (x86-64 and arm64, so Apple Silicon runs native). **Pin
the version** in anything reproducible — a receipt produced by `:latest`
cannot say which engine made it.

### pip

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "shuddhi[lid,tokens,extract] @ git+https://github.com/agentanywhere/shuddhi"
shuddhi doctor
```

(Installing straight from the repository until the package is on PyPI. The
extras are optional: `lid` for fastText language ID, `tokens` for token
accounting, `extract` for HTML extraction. Without them the pipeline still
runs, with documented fallbacks.)

### From a clone

```bash
git clone https://github.com/agentanywhere/shuddhi.git && cd shuddhi
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[lid,tokens,extract,dev]"
shuddhi doctor
```

`python3 -m shuddhi` also works from a clone with nothing installed, if you
would rather not install anything at all.

`doctor` reports which interpreter you are on, what it can import, and the
exact command to fix anything missing. **If something later goes wrong, run
`doctor` first** — by far the most common failure is running Shuddhi with a
different Python than the one you installed into.

`make venv`, `make conda` and `make docker` wrap the same steps.

---

## 3. Point it at your own corpus

### Your data

Plain UTF-8 text, **one blank line between documents**:

```
First document. It can span
several lines.

Second document.
```

One file per language or source — each file is a *shard*. Have HTML instead?

```bash
shuddhi extract --in-dir ./my-html/ --out corpus/news_eng.txt
```

### A registry

The registry is the doorway: every shard declares where it came from, and
nothing enters without one. Scaffold it from the files you actually have:

```bash
shuddhi init --corpus <folder-with-your-txt-files> --out my-registry.json
```

Point `--corpus` at wherever your text actually lives — there is no
convention to follow. To try it on the corpus that ships with the
repository, use `examples/corpus`.

That writes one entry per text file, with the provenance fields left
**empty on purpose** — an empty field is refused, and `check` names exactly
which ones are missing. So a scaffold cannot become a corpus until someone
has said where the data came from.

Fill them in until it looks like this:

```json
{
  "registry_version": 1,
  "corpus_id": "my-corpus-v1",
  "shards": [
    {
      "shard_id": "news_eng",
      "path": "corpus/news_eng.txt",
      "source": "Example News Crawl 2026",
      "license": "CC-BY-4.0",
      "date_acquired": "2026-08-23",
      "data_class": "public",
      "language": "eng"
    }
  ]
}
```

**Paths are resolved from the directory you run Shuddhi in**, not from
wherever the registry file happens to sit. Keeping the registry at the root
of your project and using paths relative to it — `corpus/news_eng.txt` —
is the arrangement that behaves predictably.

`data_class` must be `public`, `licensed` or `synthetic-own`. Anything tagged
`customer`, `customer-derived` or `evaluation-only` is refused, as is
anything missing a field. Every rule is in the
[User Guide](USER-GUIDE.md#3-the-registry-and-the-provenance-gate).

```bash
shuddhi check --registry my-registry.json
```

Fix whatever it refuses before going further. It exits non-zero when
anything is refused, which is deliberate — that makes it a CI gate.

### Build it — one command

```bash
shuddhi pipeline --registry my-registry.json --out shuddhi-out/
```

Language models, measurement, the corpus manifest, near-duplicate
clustering, filtering, the cleaned corpus, an Article 53 draft and an HTML
receipt. It runs the stages in the right order, which matters more than it
sounds: the language models must exist *before* the measurement pass, or the
perplexity filter has no distribution to threshold against.

**If it keeps nothing, that is the tool telling you something.** It will say
so loudly and record the warning in the manifest. On a small or templated
corpus the usual culprit is near-duplicate clustering doing its job — if
your documents share most of their wording, they genuinely are near
duplicates and one exemplar survives per cluster. Check
`shuddhi-out/neardup-drop.u64.stats.json`: a `largest_cluster` close to your
document count is the tell. Re-run with `--no-neardup` to confirm.

Switches worth knowing:

```bash
--emit none        # manifest only: evaluate a configuration without writing a corpus
--no-perplexity    # skip the language models (sensible under a few thousand documents)
--no-neardup       # skip near-duplicate clustering
--pii drop         # drop documents containing PII instead of redacting them
--eval-set my-benchmarks.jsonl   # drop anything overlapping your eval sets
```

---

## 4. Look at what you got

```bash
shuddhi ui --dir shuddhi-out/
```

Build history, the receipts, what each filter dropped and why, the datasets
that went in, every warning, and the report to download — in a browser, on
localhost, reading only your own filesystem.

`shuddhi-out/report.html` is the same thing as a single self-contained file
you can email to an auditor or attach to a compliance pack.

```
shuddhi-out/run/MANIFEST.json         corpus_build_hash + what was measured
shuddhi-out/build/BUILD-MANIFEST.json filtered_build_hash + drops by reason
shuddhi-out/build/*.filtered.txt      the cleaned corpus
shuddhi-out/REPORT.md                 EU AI Act Article 53(1)(d) draft
```

**Record `filtered_build_hash` wherever you track training runs.** That one
string identifies exactly which documents your model saw, and anyone holding
the same source files can recompute it and check you.

---

## Already have a corpus, cleaned with something else?

You do not have to rebuild it to get a receipt:

```bash
shuddhi attest --corpus ./out-from-datatrove/ --corpus-id fineweb-slice \
    --registry my-registry.json --scan
```

Same hash definition a native build uses, so an attested corpus and a
Shuddhi-built one are comparable and verifiable the same way. The honest
limit: an attestation proves **content, not acquisition** — it says what is
inside the corpus, not where it came from. That is what `--registry` adds.

---

## When you outgrow one command

`pipeline` is the whole thing in one step. Run the stages yourself when you
want to parallelise across shards, resume after a failure, or inspect
between phases:

```bash
REG=my-registry.json

shuddhi train-lm --registry $REG --shard news_eng --lm-dir lms/
shuddhi run     --registry $REG --shard news_eng --out run/ --lm lms/eng.lm.gz --pii-scan
shuddhi merge   --registry $REG --out run/

shuddhi neardup-sig   --registry $REG --shard news_eng --sig-dir sigs/
shuddhi neardup-merge --registry $REG --run-dir run/ --sig-dir sigs/ --out neardup-drop.u64

shuddhi build --registry $REG --run-dir run/ --build-out build/ \
    --lm-dir lms/ --neardup-drop neardup-drop.u64 --toxicity --pii redact --emit text
```

Shards are independent, so `run` and `neardup-sig` parallelise cleanly.

---

## Next

- [User Guide](USER-GUIDE.md) — every stage, what it measures, how to tune it
- [CLI Reference](CLI-REFERENCE.md) — every command, flag and exit code
- [Docker](DOCKER.md) — mounts, compose, CI
- [Troubleshooting](TROUBLESHOOTING.md) — when something goes wrong
- [FAQ](FAQ.md) — how this differs from other pipelines, and what it does not do
