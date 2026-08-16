#!/usr/bin/env python3
"""Tokenizer lab — train and evaluate Tatva tokenizer candidates (v1.3).

Why this exists: Data Factory measurement showed the current 32k tokenizer
(paramanu/nano/tokenizer.json, trained on Indic Wikipedia) fragments Urdu —
1.73 bytes/token vs 3.5–4.0 for every other language, i.e. Urdu text costs
~2.2x the tokens per byte of content. Tokenizer choices are effectively
irreversible once a model trains, so candidates must be built and measured
BEFORE Rung-1 — and adoption into training configs is Sid's decision, not
this tool's.

Subcommands:
  sample  Deterministic, seek-based sampling from registry shards: K evenly
          spaced chunks per shard, resynced to document boundaries, equal
          byte budget per language ("Indic-first" = no language dominates
          the tokenizer by corpus mass). --phase 0 (train) and --phase 1
          (held-out) read disjoint file regions.
  train   Byte-level BPE with the SAME recipe as the incumbent (ByteLevel
          pre-tokenizer, min_frequency 2, specials <unk>/<s>/</s>/<pad>) at
          one or more vocab sizes.
  eval    bytes/token per language on the held-out phase for the incumbent
          + every candidate, plus corpus-level token projections using the
          measured run's per-shard byte totals. Emits JSON + a Markdown
          table; every artefact carries the sample recipe so the numbers
          are reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import registry as registry_mod

SEPARATOR = b"\n\n"
DEFAULT_CHUNKS = 64
# phase -> fractional offset inside each chunk window; budgets are far
# smaller than chunk windows, so phases read disjoint regions
_PHASE_OFFSET = {0: 0.10, 1: 0.55}


def sample_shard(path: str, budget_bytes: int, chunks: int = DEFAULT_CHUNKS,
                 phase: int = 0) -> list[bytes]:
    """Deterministic seek-based document sample spread across the file."""
    size = os.path.getsize(path)
    per_chunk = max(1, budget_bytes // chunks)
    window = size / chunks
    frac = _PHASE_OFFSET[phase]
    # The read must stay inside its slot: phases sit 0.45*window apart, so a
    # read capped at 0.35*window can never reach the other phase's region —
    # disjointness holds by construction on files of any size.
    read_len = min(per_chunk + (1 << 16), max(1, int(window * 0.35)))
    docs: list[bytes] = []
    with open(path, "rb") as f:
        for i in range(chunks):
            off = int(i * window + frac * window)
            if off >= size:
                break
            f.seek(off)
            blob = f.read(read_len)
            # resync: drop the partial doc before the first separator,
            # drop the partial doc after the last separator
            start = blob.find(SEPARATOR)
            end = blob.rfind(SEPARATOR)
            if start == -1 or end <= start:
                continue
            got = 0
            for part in blob[start + 2 : end].split(SEPARATOR):
                doc = part.strip()
                if doc:
                    docs.append(doc)
                    got += len(doc)
                    if got >= per_chunk:  # trim to budget
                        break
    return docs


def cmd_sample(args) -> int:
    _meta, accepted, refused = registry_mod.load_registry(args.registry)
    if refused:
        print(f"registry has refusals — fix before sampling", file=sys.stderr)
        return 2
    os.makedirs(args.out_dir, exist_ok=True)
    budget = int(args.mb_per_lang * 1e6)
    recipe = {"mb_per_lang": args.mb_per_lang, "chunks": args.chunks,
              "phase": args.phase, "languages": {}}
    for s in accepted:
        docs = sample_shard(s.path, budget, args.chunks, args.phase)
        out = os.path.join(args.out_dir, f"{s.language}.txt")
        data = b"\n\n".join(docs) + b"\n\n"
        with open(out, "wb") as f:
            f.write(data)
        recipe["languages"][s.language] = {
            "docs": len(docs), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        print(f"  {s.language}: {len(docs):,} docs, {len(data)/1e6:.1f} MB", flush=True)
    with open(os.path.join(args.out_dir, "SAMPLE-RECIPE.json"), "w") as f:
        json.dump(recipe, f, indent=1)
    return 0


def cmd_train(args) -> int:
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

    files = sorted(
        os.path.join(args.sample_dir, fn)
        for fn in os.listdir(args.sample_dir) if fn.endswith(".txt")
    )
    os.makedirs(args.out_dir, exist_ok=True)
    for vocab in args.vocab_sizes:
        tok = Tokenizer(models.BPE(unk_token="<unk>"))
        tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
        tok.decoder = decoders.ByteLevel()
        trainer = trainers.BpeTrainer(
            vocab_size=vocab, min_frequency=2,
            special_tokens=["<unk>", "<s>", "</s>", "<pad>"],
            initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        )
        tok.train(files, trainer)
        out = os.path.join(args.out_dir, f"tatva-tok-v2-{vocab // 1000}k.json")
        tok.save(out)
        print(f"trained vocab={tok.get_vocab_size()} -> {out}", flush=True)
    return 0


def cmd_eval(args) -> int:
    from tokenizers import Tokenizer

    candidates = {"incumbent-32k": args.incumbent}
    for p in args.candidates:
        candidates[os.path.splitext(os.path.basename(p))[0]] = p
    toks = {name: Tokenizer.from_file(path) for name, path in candidates.items()}

    shard_bytes = {}
    if args.run_dir:
        import glob

        for p in glob.glob(os.path.join(args.run_dir, "*.stats.json")):
            st = json.load(open(p))
            shard_bytes[st["shard"]["language"]] = st["full_pass"]["doc_bytes"]

    langs = sorted(
        fn[:-4] for fn in os.listdir(args.heldout_dir) if fn.endswith(".txt")
    )
    results: dict[str, dict[str, float]] = {n: {} for n in toks}
    for lang in langs:
        with open(os.path.join(args.heldout_dir, f"{lang}.txt"), "rb") as f:
            data = f.read()
        text = data.decode("utf-8", "replace")
        n_bytes = len(data)
        for name, tok in toks.items():
            n_tokens = len(tok.encode(text).ids)
            results[name][lang] = round(n_bytes / n_tokens, 4)

    projections = {}
    if shard_bytes:
        for name in toks:
            projections[name] = int(sum(
                shard_bytes[lang] / results[name][lang]
                for lang in langs if lang in shard_bytes
            ))

    report = {
        "heldout_dir": args.heldout_dir,
        "bytes_per_token": results,
        "corpus_token_projection": projections,
    }
    out = os.path.join(args.out_dir or ".", "TOKENIZER-EVAL.json")
    with open(out, "w") as f:
        json.dump(report, f, indent=1)

    names = list(toks)
    lines = ["| lang | " + " | ".join(names) + " |",
             "|---|" + "---:|" * len(names)]
    for lang in langs:
        lines.append(f"| {lang} | " + " | ".join(str(results[n][lang]) for n in names) + " |")
    if projections:
        lines.append("| **corpus tokens (proj.)** | " + " | ".join(
            f"{projections[n]/1e9:.1f}B" for n in names) + " |")
    table = "\n".join(lines)
    with open(os.path.join(args.out_dir or ".", "TOKENIZER-EVAL.md"), "w") as f:
        f.write(table + "\n")
    print(table)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tokenizer_lab", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("sample")
    p.add_argument("--registry", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--mb-per-lang", type=float, default=40.0)
    p.add_argument("--chunks", type=int, default=DEFAULT_CHUNKS)
    p.add_argument("--phase", type=int, default=0, choices=(0, 1))
    p.set_defaults(fn=cmd_sample)

    p = sub.add_parser("train")
    p.add_argument("--sample-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--vocab-sizes", type=int, nargs="+", default=[32000, 48000])
    p.set_defaults(fn=cmd_train)

    p = sub.add_parser("eval")
    p.add_argument("--incumbent", required=True)
    p.add_argument("--candidates", nargs="+", required=True)
    p.add_argument("--heldout-dir", required=True)
    p.add_argument("--run-dir", default="", help="measured run dir for corpus projections")
    p.add_argument("--out-dir", default=".")
    p.set_defaults(fn=cmd_eval)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
