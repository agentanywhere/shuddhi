# Shuddhi (शुद्धि) — Data Factory

**A receipts-first data factory for sovereign AI.** Shuddhi turns raw text
into a filtered corpus *with a verifiable identity*: every document is
content-hashed, every shard carries provenance, every filter threshold is
pinned, and the whole build collapses into one hash that a training run
cites in its ledger.

Six months after a training run, "which documents did this model see, and
can you prove the customer data was excluded?" should have an answer that
does not depend on anyone's memory. That is what this produces.

Internally the engine is the **Tatva Data Factory**; Shuddhi is the product.

[![CI](https://github.com/agentanywhere/shuddhi/actions/workflows/ci.yml/badge.svg)](https://github.com/agentanywhere/shuddhi/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

Apache-2.0. CPU-only. No network calls, no telemetry, no account.

---

## Try it in one minute

```bash
docker build -t shuddhi .
docker run --rm shuddhi demo
```

That runs the complete pipeline over a bundled sample corpus with
deliberately planted defects, so every filter visibly catches something:

```
kept 34 of 42 documents; 5 PII spans redacted
dropped by reason: {'exact_dup': 1, 'near_dup': 2, 'quality': 1,
                    'perplexity': 2, 'toxicity': 1, 'contamination': 1, 'pii': 0}
refused at the gate: ['customer_export']
```

Run it twice: the hashes do not change. Run it on macOS, in a venv, and in
the container: the hashes still do not change.

No Docker? `make venv` or `make conda`, then `./scripts/demo.sh`.

---

## Documentation

| | |
|---|---|
| **[Quickstart](docs/QUICKSTART.md)** | install, see it work, run it on your own corpus |
| **[User Guide](docs/USER-GUIDE.md)** | every stage, what it measures, how to tune it |
| **[CLI Reference](docs/CLI-REFERENCE.md)** | every command, flag, and exit code |
| **[Docker](docs/DOCKER.md)** | mounts, compose, CI usage |
| **[Troubleshooting](docs/TROUBLESHOOTING.md)** | when something goes wrong |
| **[FAQ](docs/FAQ.md)** | how it differs from other curation pipelines, and what it does not do |
| **[Extending](docs/EXTENDING.md)** | write a filter plugin; how custom filters stay inside the receipt |
| [Engine internals](docs/ENGINE-INTERNALS.md) | stage-by-stage implementation notes |
| [Measured report](docs/MEASURED-REPORT.md) | the full 176 GB run, with coverage on every number |

---

## The receipts chain

```
registry              source · licence · date · data_class, per shard
   │                  (customer-class data refused here, in code, no override)
   ├─► corpus_build_hash     content hash of the accepted document set
   ├─► filter_config_sha     every threshold + droplist + lexicon shas
   └─► filtered_build_hash   chained to both — the string training cites
```

Order-independent, recomputable by anyone holding the shards, and unchanged
by parallelism. No signature to trust, no server to ask.

---

## For the EU AI Act

Article 53(1)(d) of Regulation (EU) 2024/1689 requires every provider placing a
general-purpose AI model on the Union market to publish a "sufficiently detailed
summary of the content used for training", on the template the AI Office
published on 2025-07-24. Enforcement powers activated 2026-08-02; models placed
on the market before 2025-08-02 must publish by 2027-08-02.

```bash
python factory.py report --eu-ai-act --registry examples/registry.json \
                         --manifest BUILD-MANIFEST.json > article-53.md
```

Shuddhi does not compute anything new for this. `source`, `licence`,
`data_class`, `language` and `date_acquired` are already **required** registry
fields — a shard missing any of them is refused, not defaulted — so the summary
is a projection of what admission already recorded.

Pass the `BUILD-MANIFEST.json` that `factory.py build` writes, not the corpus
`MANIFEST.json` that `factory.py run` writes: only the first records a filter
pass. Hand it the wrong one and it says so and marks the fields a **GAP**,
rather than reporting a retention count nothing measured.

**It does not make you compliant, and it never claims to.** Compliance is a legal
position held by a provider, not a property of a tool. What you get is a draft
grounded in what was actually recorded, for your counsel to complete. Every field
a corpus cannot know — provider identity, crawler identity, your TDM opt-out
policy under Directive (EU) 2019/790 Art. 4(3) — is printed as an explicit
**GAP** rather than guessed or quietly omitted. An incomplete summary you can see
beats a confident one that is wrong.

One answer in it is stronger than most providers can give. Where the template
asks how user data was handled, the honest answer here is that a build containing
it **cannot be produced** — the refusal is structural, not procedural.

---

## Already using NeMo Curator, DataTrove, or Dolma?

Keep using them. They are good at throughput, and out-curating NVIDIA's GPU dedup
is a fight that helps nobody. What none of them emits is a *receipt* — an artefact
you can hand a regulator, an auditor or a customer that says "this, exactly this,
is what the model saw."

```bash
python factory.py attest --corpus ./out-from-datatrove/ --corpus-id fineweb-slice
```

The fingerprint uses the **same hash definition** a native build uses, so an
attested corpus and a Shuddhi-built one are verifiable the same way and
comparable to each other. If the producing tool left a manifest, it is *cited,
never verified* — we did not observe that run.

An attestation proves **content, not acquisition**. It binds a corpus to a hash
and reports what is inside it; it cannot establish where the data came from or
under what licence. Without `--registry`, every provenance field reads `UNKNOWN`
rather than blank — because a blank reads as "nothing to declare", which is the
dangerous misreading.

---

## What it does

| stage | module |
|---|---|
| Provenance gate — customer-class data refused before the file is opened | `registry.py` |
| Streaming ingest, document hashing, shard SHA-256 | `shards.py` |
| Exact dedup (full corpus) | `dedup.py` |
| Near-dup — MinHash/LSH, disk-backed, order-independent exemplar | `neardup.py` |
| Language ID — fastText lid.176, Unicode-script fallback | `lid.py` |
| Quality heuristics | `quality.py` |
| Perplexity proxy — per-language char-trigram LM | `ngram_lm.py` |
| Toxicity — lexicon tier, pluggable and sha-pinned | `toxicity.py` |
| PII — scan and redact (email/phone/Aadhaar/PAN/Luhn cards/IP) | `pii.py` |
| Domain classification | `domain.py` |
| Contamination screen against your eval sets | `contamination.py` |
| Applied-filter builds with chained hashes | `builder.py` |
| HTML → shard extraction | `extract.py` |
| Tokenizer train/eval lab | `tokenizer_lab.py` |
| Attest a corpus **another tool** built — same hash definition, honest about limits | `attest.py` |
| EU AI Act Article 53(1)(d) training-content summary, as a reviewable draft | `eu_ai_act.py` |
| **Filter plugin API** — third-party/commercial filters, no fork, identity in the receipt | `plugins.py` |

CPU-only throughout. No GPU, no cluster, no network calls.

---

## Proven at scale

From the reference run — 176.1 GB, 33,047,370 documents, 15 languages, on a
single 2-vCPU box:

| | |
|---|---|
| corpus build hash | `5e8fbb96…`, reproduced across **four** independent full passes |
| filtered build hash | `a532e4ed…` — 32,289,800 documents kept (97.71%) |
| dropped | 0.38% exact-dup · 0.83% near-dup · 1.05% perplexity · 0.02% quality · 0.016% toxicity |
| contamination | 0, verified on **every** document |
| PII | 182,781 spans redacted |
| largest near-dup cluster | one template repeated 84,275 times |

Full detail, with coverage labelled on every number, in the
[measured report](docs/MEASURED-REPORT.md). Claims discipline is part of the
product: full-pass, sampled, and derived figures are never mixed silently,
and the report states what was *not* measured.

---

## Development

```bash
make help          # every task
make doctor        # can this interpreter run the pipeline?
make test          # 140 tests, no network, seconds
make demo          # end-to-end on the sample corpus
make docker-demo   # the same, inside the container
```

Repo layout:

```
factory.py            CLI: doctor · check · run · merge · build · build-union
                           attest · report · plugins · neardup-sig
                           neardup-merge · train-lm · extract
*.py                  the stages (table above)
tests/                140 tests, tiny fixtures
examples/             sample corpus with planted defects, registry, lexicon
scripts/demo.sh       the end-to-end demo
configs/              shard registries
runs/                 measured manifests from the reference corpus
docs/                 the documentation set
```

---

## Contributing

Issues and pull requests are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md)
for the ground rules (the important one: anything that changes what a build
keeps must also change the build's identity). Security-sensitive reports go
to security@shephertz.com per [SECURITY.md](SECURITY.md).

Most new filters belong in a [plugin](docs/EXTENDING.md) rather than in core.

## Permanently open

The engine, **every** built-in filter, local receipt generation and the
customer-data refusal are Apache-2.0 and will not move behind a proprietary
licence later. Commercial offerings extend Shuddhi through the public plugin API
and through hosted services — they do not remove capability from the open engine,
and an existing open feature will not be repackaged as a paid one.

We are stating this because the alternative is well documented: several
open-core projects relicensed after adoption, and what they lost was not revenue
but the willingness of anyone to build on them again.

What is commercial: a hosted registry with signed attestation, team review
workflow, cross-build analytics, air-gapped deployment and support. The engine
demands a named human reviewer for a suspect shard and gives you no way to manage
that queue — managing it is the product. **The engine and the proof are free;
running it as an organisation is paid.**

The discipline that keeps this honest: if a commercial feature needs an engine
change, that engine change is made here, in the open repository.

## Licence

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). "Shuddhi" is a
trademark of ShepHertz Technologies; the licence covers the software, not
the name.
