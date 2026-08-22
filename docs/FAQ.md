# FAQ

### What problem does Shuddhi actually solve?

Six months after a training run, "which documents did this model see, and
can you prove the customer data was excluded?" is usually unanswerable.
Shuddhi makes it answerable with a hash anyone can recompute from the raw
shards.

### How is this different from datatrove, NeMo Curator, or the Dolma toolkit?

Those are strong, mature curation pipelines, and at web scale on GPU
clusters they will out-throughput this by a wide margin. The difference is
what Shuddhi treats as the product: **the receipt**. Reproducible content-
addressed build hashes, a filter config pinned into the chain, a provenance
gate enforced in code, and a build that fails if a shard changed since it was
measured. If you want maximum throughput, use those. If you need to *prove*
what went into a model, that is this.

### Is the corpus build hash a signature?

No, and deliberately so. It is a content hash you recompute yourself — no
key, no server, no trust. Two people with the same shards and config get the
same string or discover they do not.

### Does it phone home?

No. The pipeline makes no network calls. The only downloads are ones you
run yourself (`make fetch-lid`).

### Can it really refuse customer data, or is that just a convention?

It is a code path with no override. The check runs before any other
validation, returns unconditionally, and happens before the shard file is
opened. There is no flag, environment variable, or registry field that
admits a `customer` class, and the test suite asserts this from five
directions — including that a named human reviewer cannot override it.

### Do I need a GPU?

No. Everything is CPU-only by design. The reference corpus — 176 GB, 33
million documents — was measured and built on a 2-vCPU virtual machine.

### How big a corpus can it handle?

Memory scales with document *count*, not size. Roughly 40 bytes per document
for merge, ~256 bytes per document for near-dup signatures (memory-mapped).
33 million documents merges inside 2 GB. Individual documents and files can
be any size — everything streams.

### Why blank-line-separated text instead of JSONL/parquet?

Because it is the lowest common denominator: greppable, streamable, trivially
produced by any scraper, and readable in fifty years. `extract` converts
HTML; converting other formats is a few lines of whatever you already use.

### Can I add my own filter?

Yes. Each filter is a small module with one function, and `builder.py`
applies them in a documented order. Add a module, call it in `build_shard`,
add its identity to `FilterConfig.canonical()` so it enters the config sha —
that last step is what keeps the receipt honest.

### Why did my filtered corpus keep 97% of documents? I expected more removal.

Because the reference corpus was already curated upstream. Shuddhi reports
what it finds rather than manufacturing a scary number. On a raw crawl,
near-dup and quality drops are far larger — that is where the filtering
leverage lives.

### The perplexity filter dropped exactly ~1%. Is that a finding?

No, and the docs are careful about this: `--ppx-percentile 99` drops the
worst 1% per language *by construction*. It is design verification, not a
discovery about your data.

### Is the toxicity screen safe to rely on for content moderation?

No. It is a lexicon tier with conservative thresholds, meant to remove the
unambiguous tail from a training corpus. It has no understanding of context.
Content moderation needs a classifier and human review.

### Is the PII redaction compliance-grade?

No. It is pattern-based — email, phone, Aadhaar, PAN, Luhn-valid cards, IP —
and does not detect names or addresses, which need NER. Treat it as corpus
hygiene, not as a DLP control.

### What happens if two people build the same corpus with different settings?

Different `filter_config_sha256`, therefore different `filtered_build_hash`,
both chained to the same `corpus_build_hash`. That is the intended behaviour:
the config is part of the identity.

### Can I trust the hash if I parallelise the build?

Yes, and it is unit-tested. The hash is defined over a set of document
hashes, so partitioning cannot change it; `build-union` merges partitions and
refuses to combine incompatible ones.

### Why is `--emit none` the default?

So you can evaluate a filter configuration — how much would this drop, and
why — without writing a copy of your corpus. The selection and the hash are
identical whether or not text is emitted.

### Does it modify my original data?

Never. Raw shards are opened read-only. All output goes to the directories
you name.

### What are the token counts based on?

Bytes-per-token measured with your tokenizer on a sample per shard, then
multiplied by full-pass byte totals. They are labelled as derived estimates
everywhere they appear, because that is what they are.

### Is it open source?

Not yet. The engine is built to be, and the repository carries a
`PUBLIC-RELEASE-CHECKLIST.md` for the extraction, but the decision has not
been made.
