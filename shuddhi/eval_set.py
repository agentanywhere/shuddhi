#!/usr/bin/env python3
"""Build an eval-set JSONL for contamination screening.

The contamination stage screens your corpus against material you do NOT
want a model trained on: benchmark questions, held-out evaluation sets,
grading prompts, canary strings. That material is yours, so this tool just
converts what you have into the format Shuddhi reads.

Output format — one JSON object per line:

    {"id": "...", "source": "...", "text": "..."}

Usage:

    # each file in a directory becomes one eval item
    python3 build_eval_set.py --from-dir ./benchmarks --out eval-set.jsonl

    # each non-empty line of a file becomes one eval item
    python3 build_eval_set.py --from-lines ./prompts.txt --out eval-set.jsonl

    # pull a field out of an existing JSONL (e.g. a benchmark dump)
    python3 build_eval_set.py --from-jsonl ./bench.jsonl --field question \
        --out eval-set.jsonl

Sources combine; pass several. Items shorter than --min-chars (default 40)
are skipped: very short strings match ordinary prose and would flood your
build with false contamination hits.

Keep the result private. An eval set that has been published is one a model
can be trained on, which is exactly what the screen exists to detect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os


def _add(items, seen, source, text, min_chars):
    text = " ".join(text.split())
    if len(text) < min_chars:
        return
    key = hashlib.sha256(text.encode()).hexdigest()
    if key in seen:
        return
    seen.add(key)
    items.append({"id": f"{os.path.basename(source)}:{key[:10]}",
                  "source": source, "text": text})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-dir", action="append", default=[],
                    help="directory of text files; each file is one eval item")
    ap.add_argument("--from-lines", action="append", default=[],
                    help="text file; each non-empty line is one eval item")
    ap.add_argument("--from-jsonl", action="append", default=[],
                    help="JSONL file; use with --field")
    ap.add_argument("--field", default="text", help="field to read from --from-jsonl")
    ap.add_argument("--min-chars", type=int, default=40)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    items: list[dict] = []
    seen: set[str] = set()

    for d in args.from_dir:
        for root, _dirs, files in os.walk(d):
            for fn in sorted(files):
                path = os.path.join(root, fn)
                try:
                    _add(items, seen, path, open(path, encoding="utf-8").read(), args.min_chars)
                except (UnicodeDecodeError, OSError):
                    continue

    for f in args.from_lines:
        for line in open(f, encoding="utf-8"):
            if line.strip():
                _add(items, seen, f, line, args.min_chars)

    for f in args.from_jsonl:
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            val = obj.get(args.field)
            if isinstance(val, str):
                _add(items, seen, f, val, args.min_chars)

    if not items:
        print("no eval items found — check your sources and --min-chars")
        return 1

    with open(args.out, "w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    sha = hashlib.sha256(open(args.out, "rb").read()).hexdigest()
    print(f"{len(items)} eval items -> {args.out}")
    print(f"sha256 {sha}  (recorded in every build that screens against it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
