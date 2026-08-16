#!/usr/bin/env python3
"""Build eval-set.jsonl — the benchmark material the contamination stage
protects (stage 6 input).

Sources, all inside this repo:
  1. String literals in the eval harnesses (ops/reliability-ab.mjs,
     ops/kriti-graders.mjs, ops/specialist-graders.mjs, ops/trap-honesty.mjs,
     ops/regrade-traps.mjs): every double-quoted string and every backtick
     template >= MIN_CHARS. This over-collects (grader messages as well as
     prompts) — over-collection is the safe direction for a contamination
     screen.
  2. Eval fixture files (ops/fixtures/**): the source trees agents are graded
     against, excluding node_modules and lockfiles.

Output: one JSON object per line: {id, source, text}. The file is committed
and its sha256 is recorded in every shard's contamination stats, so a report
always says exactly which eval set it was screened against.

Usage: python3 build_eval_set.py --repo-root ../.. --out eval-set.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re

MIN_CHARS = 80
HARNESS_FILES = (
    "ops/reliability-ab.mjs",
    "ops/kriti-graders.mjs",
    "ops/specialist-graders.mjs",
    "ops/trap-honesty.mjs",
    "ops/regrade-traps.mjs",
    "ops/honesty-doctrine.mjs",
    "ops/kriti-doctrine.mjs",
)
FIXTURE_DIRS = ("ops/fixtures",)
FIXTURE_SKIP = re.compile(r"node_modules|package-lock\.json|\.png$|\.ico$")

_DQ_STRING = re.compile(r'"((?:[^"\\\n]|\\.)+)"')
_TEMPLATE = re.compile(r"`((?:[^`\\]|\\.)+)`", re.DOTALL)


def _unescape(s: str) -> str:
    return (
        s.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\`", "`").replace("\\\\", "\\")
    )


def collect(repo_root: str) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    def add(source: str, kind: str, text: str) -> None:
        text = text.strip()
        if len(text) < MIN_CHARS:
            return
        key = hashlib.sha256(text.encode()).hexdigest()[:24]
        if key in seen:
            return
        seen.add(key)
        items.append({"id": f"{kind}:{os.path.basename(source)}:{key[:10]}", "source": source, "text": text})

    for rel in HARNESS_FILES:
        path = os.path.join(repo_root, rel)
        if not os.path.exists(path):
            continue
        src = open(path, encoding="utf-8").read()
        for m in _DQ_STRING.finditer(src):
            add(rel, "harness-string", _unescape(m.group(1)))
        for m in _TEMPLATE.finditer(src):
            add(rel, "harness-template", _unescape(m.group(1)))

    for d in FIXTURE_DIRS:
        base = os.path.join(repo_root, d)
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if not FIXTURE_SKIP.search(x)]
            for fn in files:
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, repo_root)
                if FIXTURE_SKIP.search(rel):
                    continue
                try:
                    text = open(p, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError):
                    continue
                add(rel, "fixture", text)

    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=os.path.join(os.path.dirname(__file__), "..", ".."))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "eval-set.jsonl"))
    args = ap.parse_args()

    items = collect(os.path.abspath(args.repo_root))
    with open(args.out, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    sha = hashlib.sha256(open(args.out, "rb").read()).hexdigest()
    print(f"{len(items)} eval items -> {args.out}  sha256={sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
