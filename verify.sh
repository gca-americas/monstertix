#!/usr/bin/env bash
# Confirm the rig is ready, in one screen of ticks.
#
# Everything here is a thing that fails LATER and confusingly if it is wrong now.
# The asyncio SQLite drivers are the sharp one: without them nothing complains
# until the first session write, which is step 6, in front of the room.
#
# Cloud SQL is deliberately NOT checked. setup.sh starts it in the background and
# it takes eight to twelve minutes. Nothing before step 10 touches it, so a
# "still creating" here would be noise.
#
#     ./verify.sh

set -uo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
FAILED=0

pass() { printf "  \033[32m✓\033[0m %-34s %s\n" "$1" "${2:-}"; }
fail() { printf "  \033[31m✗\033[0m %-34s %s\n" "$1" "${2:-}"; FAILED=1; }

check() {          # check <label> <command...>   — quiet unless it breaks
  local label="$1"; shift
  local out
  if out=$("$@" 2>&1); then
    pass "$label" "$(echo "$out" | tail -1)"
  else
    fail "$label" "$(echo "$out" | tail -1 | cut -c1-60)"
  fi
}

echo ""
echo "  Checking the rig"
echo ""

# --- the toolchain --------------------------------------------------------
if [ ! -x "$PY" ]; then
  fail "virtualenv" ".venv missing — run ./setup.sh"
  echo ""; exit 1
fi
check "adk installed"        .venv/bin/adk --version

# --- the ADK 2 APIs the workshop is built on ------------------------------
check "adk 2 apis"           "$PY" -c \
  "from google.adk.apps.app import App, ResumabilityConfig; print('App + ResumabilityConfig')"
check "workflow graphs"      "$PY" -c \
  "from google.adk.workflow import Workflow, START, node; print('Workflow + node')"

# --- session storage, the one that fails late -----------------------------
check "async sqlite drivers" "$PY" -c \
  "import sqlalchemy, aiosqlite, greenlet; print('sqlalchemy + aiosqlite + greenlet')"

# --- credentials ----------------------------------------------------------
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi
if [ -n "${GOOGLE_CLOUD_PROJECT:-}" ]; then
  pass "project" "$GOOGLE_CLOUD_PROJECT"
else
  fail "project" "GOOGLE_CLOUD_PROJECT not in .env — run ./setup.sh"
fi
if [ "${GOOGLE_GENAI_USE_VERTEXAI:-}" = "true" ]; then
  pass "vertex ai" "no API keys anywhere"
else
  fail "vertex ai" "GOOGLE_GENAI_USE_VERTEXAI should be true"
fi

# --- the seeded conversation step 3 opens ---------------------------------
if [ -f sessions.db ]; then
  EVENTS=$(sqlite3 sessions.db "select count(*) from events;" 2>/dev/null || echo 0)
  if [ "${EVENTS:-0}" -gt 0 ]; then
    pass "seeded session" "$EVENTS events, two days old"
  else
    fail "seeded session" "sessions.db is empty — run: $PY -m seed.session"
  fi
else
  fail "seeded session" "no sessions.db — run: $PY -m seed.session"
fi

# --- the venue ------------------------------------------------------------
pass "region" "${GOOGLE_CLOUD_REGION:-us-central1}  (services)"

if [ -n "${VENUE_URL:-}" ]; then
  if curl -sf --max-time 20 "$VENUE_URL/health" >/dev/null 2>&1; then
    pass "venue" "$VENUE_URL"
  else
    fail "venue" "$VENUE_URL not answering — ./deploy-venue.sh"
  fi
else
  fail "venue" "not deployed yet — run ./deploy-venue.sh"
fi

echo ""
if [ "$FAILED" -eq 0 ]; then
  echo "  Ready. Cloud SQL is still building in the background and nothing"
  echo "  before step 10 needs it."
  echo ""
  exit 0
fi
echo "  Fix the ✗ rows above, then run ./verify.sh again."
echo ""
exit 1
