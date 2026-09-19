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
| 7 | Build manifest + composition report | `shuddhi merge` | — |
| 8 | PII scan/redact (email, phone, Aadhaar, PAN, Luhn-checked cards, IP) | `pii.py` | sampled; full-doc on build |
| 9 | Perplexity proxy (per-language char-trigram LM, bits/char) | `ngram_lm.py` | sampled; per-doc on build |
| 10| **Applied-filter builds** with chained hash | `builder.py` / `shuddhi build` | full corpus |
| 11| **Applied near-dup** (full-corpus MinHash/LSH, disk-backed, deterministic exemplar) | `neardup.py` | full corpus |
| 12| Toxicity screen (lexicon tier, external lists pluggable + sha-pinned) | `toxicity.py` | per-doc on build |
| 13| Extraction (HTML → shard text; trafilatura or fallback) | `extract.py` | — |

v1.2 near-dup + toxicity flow:

```bash
for s in <shards>; do shuddhi neardup-sig --registry R --shard $s --sig-dir sigs/; done
shuddhi neardup-merge --registry R --run-dir out/ --sig-dir sigs/ --out neardup-drop.u64
shuddhi build ... --neardup-drop neardup-drop.u64 --toxicity
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

**The matching normal form.** The contamination screen (8-word grams) and
the toxicity matcher (whole-word lexicon lookup) both ask "does this text
contain those words?", so they share one definition of *the same text* and of
*a word*: `words.py`, identified in receipts by `word_normalizer_version`.

| Version | Behaviour | Shuddhi |
|---|---|---|
| 1 | `lower()`, split on `\W+` — not recorded in receipts | through 1.2.0 |
| 2 | NFKC_Casefold-style fold; combining marks are word-internal | 1.3.0 |

Version 2, in order:

1. **Fold.** NFKC → casefold → remove ignorable code points (category `Cf`,
   variation selectors, combining grapheme joiner) → NFKC again if anything
   changed. This is Unicode's NFKC_Casefold recipe assembled from the
   standard library. It erases differences of *encoding*, not of spelling:

   | One text, two encodings | |
   |---|---|
   | ज़ as U+095B, or as ज + nukta U+093C | very common: IMEs disagree |
   | Bengali ো, Tamil ொ, Malayalam ൊ typed whole or as two halves | |
   | Arabic presentation forms (U+FB50–FEFF) vs plain letters | PDF extraction |
   | ZWJ / ZWNJ / zero-width space / soft hyphen present or absent | rendering hints, `<wbr>` |
   | bidi marks and embeddings around a word | everywhere in Urdu web text |
   | `ﬁ` ligature, full-width Latin, `Straße` vs `STRASSE` | |

2. **Split.** A word is a maximal run of `\w` and combining marks (`M*`)
   containing at least one `\w` character.

**Not folded, on purpose:** Arabic-script vocalisation marks and tatweel,
Arabic vs Farsi yeh/kaf, a dropped nukta (बाजार for बाज़ार), legacy Malayalam
chillu sequences, transliteration. Those are spelling choices, and folding
them is language-specific policy rather than a Unicode equivalence. If
measurement shows they matter, they are a version 3; `tests/test_words.py`
pins the current boundary so that change is a decision, not an accident.

Version 1 was wrong for every script that writes vowels as combining marks.
Python's `\w` does not match categories Mn/Mc, so each Indic word broke at
every matra, virama and nukta, and the marks were discarded: मुझे became
`म`, `झ`; seven Hindi words became 13 fragments, six Tamil words 19;
vocalised Urdu broke at every zabar/zer/pesh. Both sides of the screen were
fragmented identically, so it still ran, but an "8-word" gram spanned about
four real words reduced to consonant skeletons. That made the screen both
weaker than stated and noisier (मेरा and मारा were the same "words"; five
shared Hindi words could raise an 8-gram hit; the toxicity term गांड matched
inside गांडीव, Arjuna's bow). For pure-ASCII input versions 1 and 2 produce
the identical word list, at the same cost. Mark-heavy text costs more under
version 2 (≈0.5 ms per 4,000-character Hindi document, ≈6 ms at the 48,000-
character probe cap): combining marks defeat Unicode's normalization quick
check, so that text always pays for a full pass.

**Changing the normal form changes results, and therefore receipts:**

- *Contamination and toxicity verdicts* on non-ASCII text can differ between
  versions in both directions. A v1 contamination count for an Indic or
  Arabic-script corpus is not comparable with a v2 count, and a v1 "0 hits"
  does not carry the 8-word meaning the docs gave it. **Re-screen those
  corpora**; do not carry the old number forward. Eval-set files themselves
  are unchanged (they hold raw text, so `eval_set_sha256` is stable) — the
  gram index is rebuilt from them in memory on every run. Toxicity lexicon
  files and `toxicity_lexicon_sha256` are likewise unchanged.
- *Builds.* `filter_config_sha256` changes for **every** build, including
  English-only ones, because `scorer_params.word_normalizer_version` is now
  part of the filter identity. `filtered_build_hash` — a content hash of the
  kept documents — changes only if the kept set changes, i.e. only for
  corpora where a contamination or toxicity verdict actually moved.
- *Measurement stats* now carry `contamination.word_normalizer_version`. A
  stats file without that field was screened with version 1.
- `corpus_build_hash`, shard checksums, exact/near dedup, quality, LID and
  PII do not use the normal form and are unchanged. The corpus text itself is
  never rewritten: the normal form exists only inside the two screens.

**Keeping it stable.** Mark and ignorable ranges are derived from the
interpreter's `unicodedata` tables — the same tables `\w` and NFKC follow —
and the table version is recorded as `env.unicode` in each manifest. Unicode's
stability policies mean a newer table only adds behaviour for newly assigned
characters. Three tests hold the line: a golden digest over the sample texts
that fails until `WORD_NORMALIZER_VERSION` is bumped (verified identical on
Unicode 13.0 through 16.0); a check that `FilterConfig`'s hash moves with the
version; and an AST scan that fails if any module other than `words.py` hands
a `\W` pattern to `re` — which is exactly how version 1 went wrong, in two
places at once.

**The build hash.** `corpus_build_hash` = blake2b-256 over the sorted set of
unique 64-bit document hashes across accepted shards. Order-independent,
reproducible from the raw files, cheap to verify. Every training run that
consumes a corpus build cites this hash in its run ledger — that is the
contract.

## Running

```bash
# validate the ledger (exit 2 if anything is refused)
shuddhi check --registry configs/reference-sangraha.json

# process one shard (all stages, one streaming pass)
shuddhi run --registry configs/reference-sangraha.json \
  --shard sangraha_hin --out out/ \
  --eval-set eval-set.jsonl --fasttext-model lid.176.ftz \
  --tokenizer tokenizer.json

# merge all shard outputs into MANIFEST.json + COMPOSITION.md
shuddhi merge --registry configs/reference-sangraha.json --out out/

# train per-language perplexity-proxy LMs (once per corpus)
shuddhi train-lm --registry configs/reference-sangraha.json \
  --shard sangraha_hin --lm-dir lms/

# applied-filter build over the MEASURED run (run -> merge -> build):
# exact-dedup keep-first, quality >= 0.5, per-language ppx cutoff at the
# measured p99, PII redaction, contamination drop. --emit none produces the
# hash-only manifest; --emit text also writes the filtered shards.
shuddhi build --registry configs/reference-sangraha.json \
  --run-dir out/ --build-out build/ --lm-dir lms/ --ppx-percentile 99 \
  --pii redact --eval-set eval-set.jsonl --emit none
```

**The build hash.** A build's `filtered_build_hash` is computed with the
same definition as the parent `corpus_build_hash` and recorded alongside the
parent hash + the sha256 of the exact filter config. Same raw files + same
config ⇒ same filtered hash, emission or not. Build also verifies integrity:
every document hash must exist in the measured run's set, so a shard that
changed after measurement fails the build loudly.

`scripts/run-reference-corpus.sh` drives all 15 Sangraha shards with 2 workers on the LLM VM
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
