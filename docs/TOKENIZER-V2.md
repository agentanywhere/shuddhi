# Tatva tokenizer v2 — candidates, measurements, recommendation

*2026-08-13. Lab: `ops/data-factory/tokenizer_lab.py`; artefacts:
`ops/data-factory/runs/tokenizer-v2/` + Blob
`tatva/data-factory-v1/tokenizer-v2-20260813.tgz`. Decision on adoption is
Sid's — it changes training configs (Rung-1 bins must be re-tokenized).*

## Why

Data Factory measurement caught the incumbent 32k tokenizer (trained on
Indic Wikipedia) fragmenting Urdu: **1.73 bytes/token** vs 3.5–4.0 for every
other language — Urdu text costs ~2.2× the tokens per byte of content.
Tokenizer choices are effectively irreversible after pretraining, so
candidates had to be built and measured before Rung-1 spends its budget.

## Candidates

All use the incumbent's exact recipe (byte-level BPE, min_frequency 2,
`<unk>/<s>/</s>/<pad>`), trained on deterministic seek-samples of the Tatva
corpus itself — **equal 40 MB per language** (Indic-first: no language
dominates by corpus mass), the `v2c` variants adding 40 MB of **our own
source code** (24k files across shephertz repos, `synthetic-own`
provenance) as a 16th slice. Held-out eval reads disjoint file regions by
construction.

## Measured (bytes/token, held-out; higher = fewer tokens = cheaper)

| lang | incumbent | v2-lang-32k | v2c-code-32k | v2c-code-48k |
|---|---:|---:|---:|---:|
| **urd** | **1.73** | **6.08** | **5.92** | **6.28** |
| **code** | 2.37 | 2.03 | **2.91** | **3.01** |
| eng | 4.00 | 3.95 | 3.92 | 4.15 |
| hin | 3.92 | 3.93 | 3.93 | 3.94 |
| ben | 3.79 | 3.79 | 3.79 | 3.81 |
| asm | 3.43 | 3.77 | 3.75 | 3.79 |
| nep | 3.74 | 3.86 | 3.86 | 3.87 |
| ori | 3.64 | 3.77 | 3.76 | 3.79 |
| san | 3.62 | 3.72 | 3.71 | 3.74 |
| others (tam/tel/mal/kan/guj/mar/pan) | 3.58–3.92 | within ±1% | within ±1% | +0.5–1% |

Full table: `runs/tokenizer-v2/TOKENIZER-EVAL.md`.

## What the numbers say

1. **Urdu is fixed: 1.73 → 5.9–6.3 bytes/token (~3.4×).** Urdu becomes the
   *cheapest* language to train on per byte instead of the most expensive.
2. **Nothing else pays for it.** hin/ben/tam/tel/mal/kan/guj/mar/pan are
   within ±1%; the smaller languages the old Wikipedia-trained tokenizer
   under-served actually improve (asm +9%, nep +3%, ori +4%, san +3%).
3. **The code slice is nearly free and clearly earns its seat**: +23% code
   efficiency over the incumbent (2.37 → 2.91) at ≤0.5% cost to any
   language. Decision input for the Taksha-adjacent future of the lane.
4. **48k buys ~1% on Indic, +6% on eng, +3% on code**, at the cost of 16k
   extra embedding rows (~33M params per untied embedding on a 2048-d
   model — material on a 1B, noise on ≥3B).
5. **Corpus accounting deflates honestly: ~48.9B → ~45.9B projected
   tokens.** The corpus did not shrink — Urdu's token count was inflated by
   fragmentation, and the truthful number under v2c-32k is ~45.9B. Update
   Rung-planning against this, not 48.8B.

Caveat, stated plainly: candidates are trained on samples of the corpus
they are measured on, the incumbent was not — this comparison is exactly
the argument for retraining (tokenize what you will actually consume), not
a neutral bake-off of tokenizer algorithms.

## Decision: ADOPTED (2026-08-13)

Sid delegated the call ("do what you think is right"); **`v2c-code-32k` is
adopted** for the Tatva lane. Canonical file:
`paramanu/nano/tokenizer_v2c_32k.json`
(sha256 `37f32ba1f49b81a1f659fdf42edefe4903432a46cced278af9f82c76d9066d3c`),
also at Blob `agentanywhere/canonical/tokenizer_v2c_32k.json`.
`tokenize2.py` now defaults to it; the v1 `tokenizer.json` remains only to
reproduce pre-adoption bins. Remaining operational step (belongs to the
training session, needs the fs-2977 box): re-tokenize the staged Rung-1
bins with the adopted tokenizer before any training, and cite tokenizer
sha + corpus build hash `a532e4ed…` in the run ledger. The 295M-token
smoke bins on fs-2977 are v1-tokenized — stale for Rung-1.

## Original recommendation (for the record)

**Adopt `v2c-code-32k`** for Rung-1: fixes Urdu 3.4×, +23% on code,
≤0.5% cost anywhere, keeps the 32k embedding footprint the 1B configs
already assume. Choose 48k only if Rung-1 grows to ≥3B. On extra languages
(French, East Asian): recommend **no** — vocab is zero-sum against Indic
efficiency, those markets aren't ours, and byte-level BPE degrades
gracefully on anything unseen; remaining scheduled Indian languages join
in v3 when their data joins the corpus.

If adopted, the swap is: re-tokenize the staged Rung-1 bins with
`v2c-code-32k.json`, update the training config's tokenizer path + vocab
size, and record the tokenizer sha + this doc in the run ledger alongside
the corpus build hash `a532e4ed…`.
