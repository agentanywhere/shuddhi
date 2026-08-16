# Tatva Data Factory v1 — engine + first honest composition report

*2026-08-10. Engine: `ops/data-factory/` (60 unit tests). Run artefacts:
`ops/data-factory/runs/tatva-sangraha-v1/` (manifest + per-shard stats,
committed) and Blob `agentanywhere/tatva/data-factory-v1/out-v2-20260810.tgz`
(264,038,056 bytes, byte-verified — includes the full doc-hash arrays).*

## What this is

The reusable dataset-cleansing engine the DeepSeek brief calls the highest-
return first investment (§5: "the cheapest useless token is the one you never
train"; §10 priority matrix: data quality + dedup = P0), applied to the full
Tatva corpus. Output is a **corpus build manifest**: one citable
`corpus_build_hash` over the accepted document set, plus the composition
numbers below. Every future training run cites its corpus build hash in its
run ledger — training-side provenance receipts, the same discipline our
serving side already has.

**The corpus build:**

```
corpus_id:          tatva-sangraha-v1
corpus_build_hash:  5e8fbb96cf1a4e7f6ab2468349657ce678759a97400f9e97952fa11919bb1efd
registry sha256:    7eac021c2137c075…   (15 shards, all public CC-BY-4.0)
eval-set sha256:    0a4d786dd10f6194…   (62 items screened against)
```

Reproducibility was demonstrated, not assumed: the corpus was processed
end-to-end **twice** (run-1, then run-2 after a scoring fix), and both
independent full passes produced the identical build hash.

## Coverage — read this first

Numbers here are measured, and each carries its coverage:

| label | meaning |
|---|---|
| **full pass** | computed over every byte / every document of the 176 GB corpus |
| **sampled 2%** | every 50th document (660,955 docs), deterministic stride |
| **derived** | raw bytes × a ratio measured on a stated sample; always labelled |

Provenance (sha256, doc counts) and **exact dedup are full-pass**. LID,
quality, domain, near-dup, contamination are **sampled**. Token totals are
**derived**. Nothing is extrapolated beyond that.

## Headline numbers

- **176.1 GB** document text, **33,047,370 documents**, 15 languages *(full pass)*
- **Exact duplicates: 0.38%** globally — 126,965 intra-shard + only 93
  cross-shard duplicate docs; unique-doc ratio **0.9962** *(full pass)*
- **Estimated tokens: 48.8B** with our 32k tokenizer *(derived from
  per-language bytes/token measured on ~30 MB/shard samples)*. Refines the
  earlier ~45B estimate, which extrapolated one global 3.9 bytes/token ratio.
- **Contamination: 0 of 660,955 sampled documents** hit our eval material
  (reliability-ab battery, honesty traps, eval fixtures; 8-word-gram screen,
  every candidate string-verified) *(sampled 2%)*
- **Quality: 99.9% high / 0.09% medium / 0.02% low** at v1 thresholds
  *(sampled 2%)* — see honesty notes: this says the corpus is clean of
  egregious junk, not that every document is valuable.
- **Language purity (fastText lid.176): ≥97% in 12 of 15 shards** *(sampled
  2%)*; exceptions quantified below.
- **Provenance gate: 0 of 15 shards refused** — all AI4Bharat Sangraha
  verified subset, CC-BY-4.0, acquisition dates recorded. The gate itself is
  exercised by unit tests (customer-class and untagged shards are refused
  before their file is opened; no override path exists in code).

## Per-shard (full pass; purity and b/tok sampled as labelled)

| shard | GB | docs | exact dup | LID purity | est tokens | bytes/token |
|---|---:|---:|---:|---:|---:|---:|
| hin | 31.8 | 5,715,642 | **2.11%** | 99.5% | 8.11B | 3.92 |
| nep | 22.5 | 4,372,224 | 0.00% | 97.0% | 6.02B | 3.74 |
| ben | 19.0 | 2,830,657 | 0.00% | 99.8% | 5.01B | 3.79 |
| tam | 14.9 | 2,219,346 | 0.00% | 99.7% | 4.07B | 3.66 |
| eng | 13.3 | 4,877,860 | 0.12% | 98.0% | 3.29B | 4.04 |
| tel | 12.9 | 2,394,751 | 0.00% | 99.7% | 3.60B | 3.59 |
| mal | 11.2 | 2,179,979 | 0.01% | 99.7% | 3.10B | 3.62 |
| mar | 10.9 | 1,920,210 | 0.00% | 99.6% | 2.93B | 3.73 |
| guj | 8.4 | 1,340,689 | 0.00% | 99.7% | 2.22B | 3.79 |
| urd | 6.5 | 1,360,769 | 0.00% | **90.3%** | 3.78B | **1.73** |
| san | 5.8 | 495,109 | 0.00% | **73.2%** | 1.59B | 3.62 |
| ori | 5.5 | 1,090,984 | 0.00% | 99.7% | 1.49B | 3.65 |
| pan | 5.4 | 885,347 | 0.00% | 99.9% | 1.37B | 3.93 |
| kan | 5.6 | 1,035,299 | 0.01% | 99.3% | 1.53B | 3.69 |
| asm | 2.4 | 328,504 | 0.00% | **93.2%** | 0.69B | 3.47 |

Domain mix *(sampled 2%; v1 keyword classifier — composition-level signal,
not per-doc ground truth)*: indic 84.1%, general-English 14.8%, BFSI 0.89%,
reasoning 0.17%, coding 0.01%. As expected for a web-text corpus: **BFSI,
reasoning and coding density must come from dedicated sources, not from
Sangraha.**

## Findings that change decisions

1. **Hindi is the dup hotspot.** 2.11% exact duplicates (120k docs) *and*
   1.83% near-dup rate in its sample, with one 424-member template cluster.
   All other shards are ≈0% on both. Action: hin gets near-dup filtering
   first in v1.1; everything else barely needs it.
2. **Urdu exposes a tokenizer gap.** 1.73 bytes/token vs 3.5–4.0 everywhere
   else means our 32k Indic-first tokenizer fragments Urdu (Arabic script)
   toward bytes. Urdu text will cost ~2.2× the tokens per byte of content,
   and its 3.78B token estimate is inflated in exactly that sense. Decision
   input for Rung-1: either extend tokenizer coverage or discount Urdu's
   token contribution.
3. **Sanskrit LID purity is 73.2%** — fastText labels 21.5% of the san
   sample as hin/mar. Sanskrit–Hindi confusion is a known weakness of
   lid.176 in both directions (the hin shard shows 0.25% san), so treat this
   as an upper bound on impurity, not a measured 27% contamination. Urdu's
   90.3% includes 8.9% labelled Persian — plausibly genuine fa content in
   the source crawl. Assamese 93.2% (Bengali-script confusion, 2% ben).
4. **The verified Sangraha subset is already clean and deduped upstream** —
   0.38% exact dup and ~0% junk at v1 thresholds. The factory's leverage on
   THIS corpus is receipts + composition + contamination; its filtering
   leverage arrives with the next, rawer source we ingest.

## Honesty notes (claims discipline)

- **Quality**: v1 heuristics (length, symbol/digit noise, repetition,
  boilerplate markers, documented thresholds in `quality.py`). They detect
  egregious junk; they do not rank good prose. 99.9% "high" means the
  corpus passes a junk screen, nothing more. A perplexity-proxy scorer is
  the v1.1 upgrade for real discrimination.
- **Near-dup rates are within-shard, within-sample** (MinHash on every 4th
  sampled doc ≈ 0.5% of docs). Isolated near-dup *pairs* are undersampled at
  that rate (P(both ends sampled) ≈ 0.0025%); what the measurement reliably
  catches is large template families, which is what it found in hin. The
  quoted rates are lower bounds dominated by big clusters.
- **Token totals are derived**, not counted: per-shard bytes/token measured
  on ~30 MB samples × full-pass bytes. Sampled-vs-derived is labelled in
  every table.
- **Contamination screening covers the 2% sample**, not every document, and
  screens against our current eval set (62 items, sha-pinned). Zero hits is
  the expected result for an Indic web corpus vs English coding prompts —
  the value is the standing mechanical screen, run on every future build.
- **Filters were measured, not applied**: v1 produced receipts and
  composition for the existing corpus; it did not delete anything. The
  accepted set = provenance-accepted shards' unique documents. Quality/
  near-dup/contamination exclusions become *applied* filters when a training
  run requests a filtered build (v1.1).
- The engine scored the corpus **twice** because run-1 exposed a real bug:
  Python `\w` excludes combining marks, so vowel matras counted as symbol
  noise and every abugida-script shard scored "medium". Fixed, regression-
  tested (clean Hindi + Tamil fixtures), full re-run. The bug never touched
  dedup/LID/tokens/contamination, and the build hash was identical across
  both runs.

## Compute + cost

Entire measurement ran on the existing 2-vCPU Azure LLM VM (where the corpus
lives), CPU-only: **~54 CPU-minutes per full pass** (~28 min wall with 2
workers, ~50–55 MB/s/core sustained), two passes total. **Zero GPU-hours,
zero Blob egress** for the corpus (the engine went to the data); ~264 MB of
artefacts uploaded to Blob as backup. Marginal cost: effectively the VM's
idle time.

## Reusing the engine (any future corpus)

```bash
python3 factory.py check --registry <registry.json>       # provenance gate
python3 factory.py run --registry <registry.json> --shard <id> --out out/ \
    --eval-set eval-set.jsonl --fasttext-model lid.176.ftz --tokenizer tokenizer.json
python3 factory.py merge --registry <registry.json> --out out/   # manifest
```

A registry entry needs source / license / date / data_class / language.
`customer`-class data is refused unconditionally — the hard legal rule
(customer data is evaluation-only, never training) is enforced in code with
no override, and unit-tested from five directions.

## v1.1 — applied builds, perplexity, PII (2026-08-11)

v1.1 turned the factory from measuring into producing. Public product name:
**Shuddhi (शुद्धि)**; "Tatva Data Factory" remains the internal engine name.

**The first filtered corpus build (full corpus, every document evaluated):**

```
parent corpus_build_hash: 5e8fbb96cf1a4e7f…  (now reproduced across FOUR
                                              independent full passes)
filter config (sha 32bcaec5…): quality ≥ 0.5 · per-language ppx cutoff at
                               measured p99 · PII redact · contamination drop
filtered_build_hash:      8ded58e56b049cc316cacbce735dc4e51ebf53448a895078ed68e43ae2908eef
```

| outcome | docs | share |
|---|---:|---:|
| **kept** | **32,565,779** | **98.54%** |
| dropped: exact duplicate | 127,024 | 0.38% |
| dropped: perplexity > p99 | 347,447 | 1.05% |
| dropped: quality < 0.5 | 7,109 | 0.02% |
| dropped: contamination | 0 | 0 — now verified on EVERY doc, not a sample |
| dropped: PII | 0 | policy = redact, not drop |
| PII redactions the emit applies | 185,117 spans | |

The perplexity filter dropping ≈1.05% against a p99 cutoff is the filter
working exactly as specified (≈1% per language by construction) — quote it
as design verification, not as a discovery. Contamination moving from
"0 in a 2% sample" to "0 across all 33.05M documents" is the real upgrade.

**New measured numbers (v4 measurement pass, sampled 2% = 660,955 docs):**

- **PII prevalence: 0.46% of docs** (3,063) contain pattern-detectable PII —
  email 2,133 · Indian phone 1,358 · IP 297 · Luhn-valid card 64 ·
  Aadhaar-format 17 · PAN 3. Pattern-level screening, not compliance-grade
  DLP; names/addresses (NER-class) remain v2.
- **Perplexity profile per language** (own char-trigram LM, bits/char):
  means 2.83 (tam) to 3.56 (san); p99 3.71–4.92. San's highest mean is
  consistent with its LID ambiguity finding.
- Corpus build hash reproduced a **4th** time on the v4 pass.

**Engineering receipts of the run itself (honesty notes):**

- Build integrity is mechanical: every document hash must exist in the
  measured run's set, so a shard changed after measurement fails the build.
- The full-corpus build ran as **two parallel partitions + union**; the
  filtered hash is a *set* of kept doc-hashes, so partitioning provably
  cannot change it (unit-tested: sequential ≡ partitioned). 11 cross-
  partition duplicates collapsed in the union, recorded in the manifest.
- Two production bugs were caught by the run and fixed with regression
  tests: (1) a 2000-char perplexity probe made builds ~2.65 ms/doc (~19 h
  projected) — probes bounded and recorded in the filter-config sha;
  (2) partition builds initially carried per-language cutoffs only for
  their own shards, so the config sha differed and the union refused —
  cutoff maps are now partition-invariant. The refusal was the integrity
  design doing its job.
- Compute: measurement ~54 CPU-min; the applied build ~18.8 CPU-hours
  (2 × 9.4 h partitions) on the same 2-vCPU VM. Zero GPU, zero Blob egress.
- Emission demo: the asm shard materialized end-to-end (`--emit text`) —
  324,558 of 328,504 docs kept (3,944 ppx, 2 quality), 1,057 PII spans
  redacted, 2.37 GB written, output receipt sha256 `5bcd95f6a5eaf6a4…`.

**Filters applied vs measured, v1.1 edition:** dedup/quality/perplexity/
contamination/PII are now *applied* (in the build; the raw corpus is
untouched). Near-dup filtering remains *measured only* — the hin template
clusters are still the top v1.2 item.

## v1.2 — every filter applied (2026-08-13)

v1.2 closed the checklist gaps: **applied near-dup at full corpus scale**,
a toxicity screen, an HTML extraction stage, and packaging. Nothing in the
filter chain is "measured but not applied" anymore.

**The v1.2 filtered build (all seven filters, every document evaluated):**

```
parent corpus_build_hash: 5e8fbb96cf1a4e7f…
filter config (sha 5668872b…): + near-dup droplist (sha ec4b398b…)
                               + toxicity lexicon (sha 5d0bac43…)
filtered_build_hash:      a532e4edb79a5c4f090ccb66167d19ccf11324a955fcb21610aa1dab598ef404
```

| outcome | docs | share |
|---|---:|---:|
| **kept** | **32,289,800** | **97.71%** |
| exact duplicate | 127,024 | 0.38% |
| **near duplicate** | **272,640** | **0.83%** |
| perplexity > p99 | 345,505 | 1.05% |
| quality < 0.5 | 7,086 | 0.02% |
| toxicity (lexicon tier) | 5,306 | 0.016% |
| contamination | 0 | verified on every doc |
| PII | 0 dropped; 182,781 spans redacted on emission | |

**Near-dup, finally applied and surprising:** 258,406 verified clusters
across the full corpus; the largest is **84,275 copies of one template — in
the ENGLISH shard**, not Hindi (eng near-dup rate 2.4% vs hin 0.83%). The
sampled v1 measurement had fingered hin; full-scale clustering corrected
that. Exemplar selection is order-independent (min doc-hash per cluster),
so the drop list — sha-pinned into the filter config — is reproducible
regardless of parallelism.

**Toxicity at 0.016%** is the lexicon tier working as specified: precision
over recall, dropping the unambiguous tail (distinct-terms + density
thresholds; one stray profanity in normal prose does not drop a document).
A classifier tier is the documented upgrade path.

**Compute honesty:** signature pass + clustering took ~27 h wall (far over
the ~2 h estimate — per-doc shingling cost; v1.3 optimization target listed
below), clustering itself 2.6 min; the build partitions took ~11.8 h each in
parallel. The toxicity matcher that made builds slower (~1–2 ms/doc as an
alternation regex) was rewritten to word-set lookups (measured 247 µs/doc,
speed-regression-tested) — the fix landed after this build started, so this
build paid the slow price and the numbers are identical either way.

## v1.3 backlog

1. Optimize the near-dup signature pass (the 27 h wall).
2. Tokenizer coverage decision for Urdu before Rung-1 data mixing.
3. Sanskrit LID second opinion before trusting 73% as impurity.
4. NER-class PII + toxicity classifier tier — commercial-edition candidates.
5. Checkpointed/resumable builds.
6. Distilled quality classifier (label with our own models on idle GPU
   windows; sovereignty-clean FineWeb-Edu equivalent).
