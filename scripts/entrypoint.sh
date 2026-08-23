#!/usr/bin/env bash
# Container entrypoint: dispatches convenience verbs, otherwise passes
# everything straight through to the factory CLI.
set -euo pipefail

case "${1:-doctor}" in
  demo)
    shift
    exec /app/scripts/demo.sh "${1:-/work/demo-out}"
    ;;
  test)
    exec python -m pytest /app/tests -q
    ;;
  shell|bash)
    exec /bin/bash
    ;;
  *)
    exec shuddhi "$@"
    ;;
esac
