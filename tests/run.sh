#!/usr/bin/env bash
# Run the step tests. Starts a scratch venue on :8099 so a test run never
# touches the venue you are teaching from on :8080.
#
#     ./tests/run.sh                          fast suite, seconds
#     ./tests/run.sh --live                   everything, minutes, costs tokens
#     ./tests/run.sh tests/step9_the_budget   one step
#     ./tests/run.sh --live -k budget -v      any pytest arguments
set -euo pipefail
cd "$(dirname "$0")/.."
. ./set_env.sh >/dev/null

if [ "${1:-}" = "--live" ]; then
  export WORKSHOP_TEST_LIVE=1
  shift
fi

# Anything left over goes to pytest. If none of it names a path, add tests/ so
# that bare flags like `-k budget` still have somewhere to look.
if [ $# -eq 0 ]; then
  ARGS=(tests/)
else
  HAS_PATH=""
  for a in "$@"; do
    case "$a" in -*) ;; *) [ -e "$a" ] && HAS_PATH=1 ;; esac
  done
  if [ -n "$HAS_PATH" ]; then ARGS=("$@"); else ARGS=(tests/ "$@"); fi
fi

if ! curl -s http://127.0.0.1:8099/health >/dev/null 2>&1; then
  echo "→ starting a scratch venue on :8099"
  VENUE_DB=/tmp/test-venue.db VENUE_PORT=8099 python -m venue >/tmp/test-venue.log 2>&1 &
  until curl -s http://127.0.0.1:8099/health >/dev/null 2>&1; do sleep 1; done
fi

VENUE_URL=http://127.0.0.1:8099 pytest -q "${ARGS[@]}"
