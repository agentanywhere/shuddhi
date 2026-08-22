# Quickstart

From nothing to a receipted, filtered corpus. Ten minutes, no GPU.

---

## 1. Install

Pick one. All three are equivalent; Docker is the least fiddly.

### Docker (recommended)

```bash
docker build -t shuddhi .
docker run --rm shuddhi doctor
```

### venv

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 factory.py doctor
```

### conda

```bash
conda env create -f environment.yml
conda activate shuddhi
python3 factory.py doctor
```

`doctor` prints which interpreter you are on, which packages it can see, and
exactly what to install if something is missing. **If anything later goes
wrong, run `doctor` first** — the most common failure by far is running
`factory.py` with a different Python than the one you installed into.

`make venv`, `make conda`, and `make docker` wrap the same commands.

---

## 2. See it work

```bash
./scripts/demo.sh              # or: docker run --rm shuddhi demo
```

This runs the whole pipeline over `examples/corpus/`, a small corpus with
**deliberately planted defects**, and takes a few seconds. You should see
every filter catch something:

```
kept 34 of 42 documents; 5 PII spans redacted
dropped by reason: {'exact_dup': 1, 'near_dup': 2, 'quality': 1,
                    'perplexity': 2, 'toxicity': 1, 'contamination': 1, 'pii': 0}
refused at the gate: ['customer_export']
```

Three hashes are printed at the end. **Run it twice — they do not change**,
and they are the same on macOS, Linux, and inside the container.

Two things worth understanding from that output:

- `customer_export` was **refused before its file was opened**. It is tagged
  `data_class: "customer"` in `examples/registry.json`, and no flag can
  admit it. That is the point of the provenance gate.
- `'pii': 0` does not mean no PII was found — it means none was *dropped*,
  because the policy is `--pii redact`. Five spans were rewritten to
  `[PII:email]`, `[PII:phone_in]`, and so on in the emitted text.

---

## 3. Run it on your own corpus

### Prepare your data

Shuddhi reads plain UTF-8 text files where **documents are separated by a
blank line**:

```
First document. It can span
several lines.

Second document.

Third document.
```

One file per language or source is the normal layout — each file is a
*shard*. If you have HTML instead, convert it first:

```bash
python3 factory.py extract --in-dir ./my-html/ --out corpus/mysource.txt
```

### Write a registry

The registry is the doorway. Every shard declares where it came from, and
nothing enters the pipeline without it. Copy `examples/registry.json` and
edit:

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
      "date_acquired": "2026-08-13",
      "data_class": "public",
      "language": "eng"
    }
  ]
}
```

`data_class` must be `public`, `licensed`, or `synthetic-own`. Anything
tagged `customer`, `customer-derived`, or `evaluation-only` is refused, as
is anything missing a field. See the [User Guide](USER-GUIDE.md#3-the-registry-and-the-provenance-gate)
for every field and rule.

```bash
python3 factory.py check --registry my-registry.json
```

Fix whatever it refuses before going further. (It exits non-zero when
anything is refused — that is intentional, so CI can gate on it.)

### Measure, then build

```bash
REG=my-registry.json

# optional but recommended: language models for the perplexity filter.
# Train these BEFORE measuring, so the measurement records a distribution.
python3 factory.py train-lm --registry $REG --shard news_eng --lm-dir lms/

# measure every shard (repeat per shard; these can run in parallel)
python3 factory.py run --registry $REG --shard news_eng --out run/ \
    --lm lms/eng.lm.gz --pii-scan

# mint the corpus build hash
python3 factory.py merge --registry $REG --out run/

# near-duplicate clustering across the whole corpus
python3 factory.py neardup-sig --registry $REG --shard news_eng --sig-dir sigs/
python3 factory.py neardup-merge --registry $REG --run-dir run/ \
    --sig-dir sigs/ --out neardup-drop.u64

# apply the filters and write the cleaned corpus
python3 factory.py build --registry $REG --run-dir run/ --build-out build/ \
    --lm-dir lms/ --neardup-drop neardup-drop.u64 \
    --toxicity --pii redact --emit text
```

Your cleaned shards are `build/*.filtered.txt`; your receipt is
`build/BUILD-MANIFEST.json`.

---

## 4. What you now have

```
run/MANIFEST.json         corpus_build_hash + composition of everything measured
run/COMPOSITION.md        the same, as readable tables
build/BUILD-MANIFEST.json filtered_build_hash + what was dropped and why
build/*.filtered.txt      the cleaned corpus (only with --emit text)
```

Record `filtered_build_hash` in whatever ledger tracks your training runs.
That single string identifies exactly which documents your model saw, and
anyone with the raw shards can recompute it and check.

---

## Next

- [User Guide](USER-GUIDE.md) — every stage, what it measures, how to tune it
- [CLI Reference](CLI-REFERENCE.md) — every command and flag
- [Docker](DOCKER.md) — mounts, compose, CI usage
- [Troubleshooting](TROUBLESHOOTING.md) — when something goes wrong
- [FAQ](FAQ.md)
