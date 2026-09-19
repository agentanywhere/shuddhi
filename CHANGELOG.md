# Changelog

Notable changes to Shuddhi. Dates are release dates.

## Unreleased — will be 1.3.0

**Fixed — Indic and vocalised-Urdu words were split at every vowel sign.**
The contamination screen and the toxicity matcher split text on `\W+`, and
Python's `\w` does not match combining marks (Mn/Mc): मुझे became `म`, `झ`,
seven Hindi words became 13 fragments, six Tamil words 19. The contamination
screen's "8-word" grams were therefore about four real words with the vowels
thrown away — weaker than documented, and also noisier (five shared Hindi
words could raise a hit). In the toxicity screen every builtin Devanagari
term fell off the fast set-lookup path onto a regex fallback, the term गांड
matched inside गांडीव (Arjuna's bow), and hit density was computed over about
twice the true word count, under-flagging Indic documents.

Both screens now share one **matching normal form**, `shuddhi/words.py`,
stdlib-only and deterministic:

1. *Fold* — NFKC, casefold, and removal of characters that are invisible by
   design (Unicode's NFKC_Casefold recipe). One text compares equal however
   it was encoded: ज़ as U+095B or as ज + nukta; Bengali, Tamil and Malayalam
   two-part vowel signs; Arabic presentation forms from PDF extraction; the
   `ﬁ` ligature; full-width Latin; `Straße`/`STRASSE`. ZWJ/ZWNJ, zero-width
   space, soft hyphen, bidi marks and embeddings, BOM and variation selectors
   can no longer hide or break a match.
2. *Split* — a word is a run of `\w` and combining marks that contains at
   least one `\w` character.

Spelling choices are deliberately **not** folded (Arabic-script vocalisation
and tatweel, Arabic vs Farsi yeh/kaf, dropped nuktas, legacy Malayalam
chillus, transliteration); tests pin that boundary.

Pure-ASCII text yields the identical word list as before at the same cost.
Mark-heavy text costs more — about 0.5 ms for a 4,000-character Hindi
document — which is the price of Unicode normalization.

Toxicity: lexicon terms pass through the same normal form, and multi-word
terms are matched as word sequences instead of a boundary regex, so word
boundaries are right in every script by construction. Lexicon files and
`toxicity_lexicon_sha256` are unchanged.

Consequences for receipts:

- New `word_normalizer_version` (now `2`; the old behaviour is `1` and was
  never recorded). It appears in measurement stats under `contamination` and
  in the build's `filter_config.scorer_params`. A golden-digest test fails
  on any future change to the normal form until the version is bumped, and
  the digest is verified identical on Unicode 13.0 through 16.0.
- `filter_config_sha256` changes for **every** build, because the normal form
  is now part of the filter identity. `filtered_build_hash` changes only where
  a contamination or toxicity verdict actually changed the kept set.
- Contamination and toxicity results for corpora with Indic or Arabic-script
  text are **not comparable** across the two versions. Re-screen them; a
  receipt with no `word_normalizer_version` was screened with version 1.
  Eval-set files and `eval_set_sha256` are unchanged.
- Manifests record the interpreter's Unicode version as `env.unicode`.

**Changed — unreleased code says so in its receipts.** The version is
`1.3.0.dev0` until release and is stated once (`shuddhi/__init__.py`);
`factory_version` in manifests now derives from it instead of a second
constant, and tests keep `pyproject.toml` and the changelog in step.

Details: *The matching normal form* in `docs/ENGINE-INTERNALS.md`.

## 1.2.0 — 2026-08-24

First public release. The notes below cover everything through launch.

**Late fixes and additions**

- `--log-drops` on `build`/`pipeline` writes `dropped.jsonl`: one line per
  dropped document, with the reason recorded at the decision point.
- PII: added IBAN detection, validated by its ISO 13616 mod-97 check digits;
  the detector list now leads with region-neutral patterns (email, IBAN,
  Luhn cards, IP) with India-specific phone/Aadhaar/PAN alongside.
- Corrected a receipts claim: `filtered_build_hash` is a content hash of the
  selected documents and is **not** chained to `filter_config_sha256` (the
  config sha is recorded beside it). The docs said otherwise in six places,
  including the generated EU AI Act summary.
- The provenance gate's real limit is now stated plainly: it enforces the
  declared `data_class`, and is not a content classifier.

**Fixed — shards with Windows line endings were read as a single document.**
The record separator is a blank line, which CRLF writes as `\r\n\r\n`; that
contains no `\n\n`, so a whole shard collapsed into one document. It did not
error — it produced a clean receipt for a corpus that had been misread, which
is the worst failure mode a receipts tool can have. CRLF and lone-CR endings
are now folded to LF before splitting.

Two consequences worth knowing:

- The same documents now hash identically whether the file carries Unix or
  Windows endings, so a receipt can be recomputed across platforms.
- A corpus whose files contain carriage returns will produce a **different
  `corpus_build_hash` than it did before this fix** — the earlier hash
  described a misreading of it. Pure-LF corpora are unaffected, hash for
  hash. Shard provenance checksums are unchanged either way: they cover the
  raw file bytes.

Found by adding Windows to the CI matrix instead of assuming it worked.

**Receipts**
- `corpus_build_hash`: order-independent content hash of the accepted
  document set, reproducible on any machine.
- `filtered_build_hash`: content hash of the *selected* document set, by the
  same definition as `corpus_build_hash` so the two are comparable, and
  recorded alongside the parent hash.
- `filter_config_sha256`: pins every threshold plus the shas of the near-dup
  drop list, the toxicity lexicon, and any enabled plugin. Recorded beside
  the build hash rather than mixed into it, so the build hash stays
  recomputable by anyone holding only the source documents.
- Build integrity: a build fails if any document is absent from the
  measured run's hash set, so a shard that changed after measurement cannot
  silently produce an unmeasured corpus.

**Provenance**
- Registry gate refusing untagged, unknown-class, and customer-class shards
  before their files are opened, with no override path.
- Suspect-name rule requiring a named human reviewer.

**Filters** — exact dedup, full-corpus near-dup (MinHash/LSH with an
order-independent exemplar rule), quality heuristics, per-language
perplexity proxy, lexicon toxicity tier, contamination screening against
your eval sets, and pattern PII with keep/redact/drop policies.

**Other**
- Filter plugin API (`shuddhi.filters` entry points); plugin identities
  enter the config sha.
- Partition builds plus `build-union`; unioning disjoint partitions is
  provably identical to one sequential build.
- HTML extraction, tokenizer train/eval lab, `doctor` environment check.
- Docker image, venv and conda paths, 111 tests, full documentation set.

Measured on a 176 GB / 33-million-document corpus: build hash reproduced
across four independent full passes, 97.71% of documents kept, contamination
zero on every document. See [docs/MEASURED-REPORT.md](docs/MEASURED-REPORT.md).
