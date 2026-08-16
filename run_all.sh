#!/usr/bin/env bash
# Drive all 15 Sangraha shards through the factory on the LLM VM (2 cores):
#   phase 1: per-language trigram LMs (perplexity proxy)
#   phase 2: measurement runs (LID, quality, ppx, PII, dedup, contamination)
#   phase 3: merge -> corpus MANIFEST
# Usage: ./run_all.sh <out-dir> [extra factory-run args...]
# An applied-filter build then runs separately:
#   python3 factory.py build --registry ... --run-dir <out-dir> --build-out <dir> --lm-dir lms ...
set -euo pipefail
cd "$(dirname "$0")"

OUT="${1:?usage: run_all.sh <out-dir> [extra args]}"
shift || true
REG="configs/tatva-sangraha-v1.json"

python3 factory.py check --registry "$REG"

# largest-first order (bytes, from the VM listing)
SHARDS="sangraha_hin sangraha_nep sangraha_ben sangraha_tam sangraha_eng \
sangraha_tel sangraha_mal sangraha_mar sangraha_guj sangraha_urd \
sangraha_san sangraha_kan sangraha_ori sangraha_pan sangraha_asm"

echo "== phase 1: language models =="
echo "$SHARDS" | tr ' ' '\n' | xargs -P 2 -I{} sh -c '
  lang="${1#sangraha_}"
  [ -f "lms/${lang}.lm.gz" ] && { echo "  lms/${lang}.lm.gz exists, skip"; exit 0; }
  python3 factory.py train-lm --registry configs/tatva-sangraha-v1.json --shard "$1" --lm-dir lms
' _ {}

echo "== phase 2: measurement =="
for s in $SHARDS; do echo "$s"; done | xargs -P 2 -I{} sh -c '
  shard="$1"; out="$2"; shift 2
  lang="${shard#sangraha_}"
  python3 factory.py run --registry configs/tatva-sangraha-v1.json --shard "$shard" --out "$out" \
    --eval-set eval-set.jsonl \
    --fasttext-model lid.176.ftz \
    --tokenizer tokenizer.json \
    --lm "lms/${lang}.lm.gz" --pii-scan "$@"
' _ {} "$OUT" "$@"

echo "== phase 3: merge =="
python3 factory.py merge --registry "$REG" --out "$OUT"
