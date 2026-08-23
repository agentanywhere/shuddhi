# Changelog

Notable changes to Shuddhi. Dates are release dates.

## Unreleased

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

## 1.2.0 — 2026-08-13

First public release.

**Receipts**
- `corpus_build_hash`: order-independent content hash of the accepted
  document set, reproducible on any machine.
- `filtered_build_hash`: chained to the parent corpus hash and to
  `filter_config_sha256`, which pins every threshold plus the shas of the
  near-dup drop list, the toxicity lexicon, and any enabled plugin.
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
