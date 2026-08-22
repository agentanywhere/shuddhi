#!/usr/bin/env bash
# Shuddhi end-to-end demo on the bundled example corpus (~10 seconds).
#
#   ./scripts/demo.sh [workdir]        default workdir: ./demo-out
#
# Runs the complete pipeline — provenance gate, measurement, near-dup
# clustering, perplexity models, and a filtered build with every filter
# switched on — over examples/corpus/, which contains deliberately planted
# defects so you can watch each filter catch something.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
W="${1:-demo-out}"
REG=examples/registry.json

rule() { printf '\n\033[1m── %s\033[0m\n' "$1"; }

rule "0. environment"
"$PY" factory.py doctor

rm -rf "$W"; mkdir -p "$W"

rule "1. provenance gate — check the registry before reading any data"
echo "   (customer_export is tagged data_class 'customer': it must be refused)"
"$PY" factory.py check --registry "$REG" || true

rule "2. per-language perplexity models (train BEFORE measuring, so the"
echo "   measurement records a bits/char distribution the build can threshold on)"
for s in sample_eng sample_hin; do
  "$PY" factory.py train-lm --registry "$REG" --shard "$s" --lm-dir "$W/lms" --sample-every 1
done

rule "3. measure each accepted shard"
for s in sample_eng sample_hin; do
  lang=eng; [ "$s" = "sample_hin" ] && lang=hin
  "$PY" factory.py run --registry "$REG" --shard "$s" --out "$W/run" \
      --sample-every 1 --eval-set examples/eval-set.jsonl --pii-scan \
      --lm "$W/lms/$lang.lm.gz"
done

rule "4. merge into a corpus manifest (this mints the corpus build hash)"
"$PY" factory.py merge --registry "$REG" --out "$W/run"

rule "5. near-duplicate clustering across the whole corpus"
for s in sample_eng sample_hin; do
  "$PY" factory.py neardup-sig --registry "$REG" --shard "$s" --sig-dir "$W/sigs"
done
"$PY" factory.py neardup-merge --registry "$REG" --run-dir "$W/run" \
    --sig-dir "$W/sigs" --out "$W/neardup-drop.u64"

rule "6. filtered build — every filter on, PII redacted, text emitted"
"$PY" factory.py build --registry "$REG" --run-dir "$W/run" --build-out "$W/build" \
    --lm-dir "$W/lms" --ppx-percentile 99 \
    --neardup-drop "$W/neardup-drop.u64" \
    --toxicity --toxicity-lexicon-dir examples/lexicon \
    --pii redact --eval-set examples/eval-set.jsonl \
    --emit text

rule "receipts"
"$PY" - "$W" << 'PYEOF'
import json, sys
w = sys.argv[1]
m = json.load(open(f"{w}/run/MANIFEST.json"))
b = json.load(open(f"{w}/build/BUILD-MANIFEST.json"))
print(f"  corpus_build_hash    {m['corpus_build_hash']}")
print(f"  filter_config_sha    {b['filter_config_sha256']}")
print(f"  filtered_build_hash  {b['filtered_build_hash']}")
print(f"  kept {b['kept_docs']} of {m['full_pass']['total_docs']} documents; "
      f"{b['pii_redactions']} PII spans redacted")
print(f"  dropped by reason:   {b['dropped_by_reason']}")
print(f"  refused at the gate: {[r['shard_id'] for r in m['provenance_gate']['refused']]}")
PYEOF

cat <<TXT

Filtered text:  $W/build/*.filtered.txt
Full receipts:  $W/build/BUILD-MANIFEST.json  and  $W/run/MANIFEST.json

Re-running this script reproduces the same three hashes, on any machine.
Next: docs/QUICKSTART.md (your own corpus) · docs/USER-GUIDE.md (every stage).
TXT
