#!/usr/bin/env bash
# Load a step's finished code into agent/, and reset the state around it.
#
#     ./use-solution.sh 5        load step 5, from a clean slate
#     ./use-solution.sh 5 --keep load the code, leave memory and sessions alone
#     ./use-solution.sh          list what is available
#
# It replaces agent/concert entirely, and unless you pass --keep it also puts
# memory, sessions and artifacts back to their starting state. That is what
# makes a step behave the same on the fourth rehearsal as it did on the first.
#
# Your venue is never touched — press RESET THE VENUE on the panel for that.
set -euo pipefail
cd "$(dirname "$0")"

PY=./.venv/bin/python
[ -x "$PY" ] || PY=python

if [ $# -eq 0 ]; then
  echo "Which step?"
  for d in solutions/step*/; do
    n=$(basename "$d"); num=${n#step}; num=${num%%_*}
    printf "%03d\t%s\t%s\n" "$num" "$num" "$(echo "$n" | cut -d_ -f2- | tr '_' ' ')"
  done | sort | cut -f2,3 | while IFS=$'\t' read -r num name; do
    printf "  %-3s %s\n" "$num" "$name"
  done
  echo ""
  echo "  ./use-solution.sh 5"
  exit 0
fi

STEP="$1"
KEEP=""
FORCE=""
shift
for arg in "$@"; do
  case "$arg" in
    --keep)  KEEP=1 ;;
    --force) FORCE=1 ;;
    *) echo "✗ unknown option $arg  (--keep, --force)"; exit 1 ;;
  esac
done

MATCH=$(ls -d solutions/step"$STEP"_*/ 2>/dev/null | head -1 || true)
if [ -z "$MATCH" ]; then
  echo "✗ no solution for step $STEP"
  echo "  try:  ./use-solution.sh"
  exit 1
fi

# Anything in a solution folder that is not agent code belongs at the repo root,
# and it overwrites what is there. A step whose material is the trigger, or the
# frontend, or a deploy script is still a step — it just does not live in
# agent/. Step 3 is the first of those.
EXTRAS=""
for item in "$MATCH"*; do
  name=$(basename "$item")
  case "$name" in
    # These belong to agent/, and are copied there separately below. Without
    # this they land at the repo root and overwrite the VENUE's Dockerfile and
    # requirements.txt, which only shows up as a failed deploy much later.
    concert|nightly|server.py|README.md|Dockerfile|main.py|requirements.txt) continue ;;
  esac
  rm -rf "./$name"
  cp -r "$item" "./$name"
  find "./$name" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
  EXTRAS="$EXTRAS $name"
done

# A step made only of those is done — there is no agent state to reset.
if [ -n "$EXTRAS" ] && [ ! -d "$MATCH/concert" ]; then
  echo "→ loaded  $(basename "$MATCH") ·$EXTRAS"
  echo ""
  echo "  Start it with:"
  echo "      python -m monstertix.server        # then open http://127.0.0.1:8090"
  echo "      python -m monstertix.clock --in 10 # the other half, in a third terminal"
  echo ""
  echo "  (port 8090 already taken? TRIGGER_PORT=8091 python -m monstertix.server)"
  exit 0
fi

# Deleting sessions.db while `adk web` holds it open does not error — it leaves
# the running process writing to a file nobody can see, and the next thing that
# looks strange costs an hour. Stop first.
if [ -z "$KEEP" ] && [ -z "$FORCE" ] && lsof -ti:8000 >/dev/null 2>&1; then
  echo "✗ something is running on :8000, and this would delete sessions.db"
  echo "  underneath it. Ctrl-C the agent first, then run this again."
  echo ""
  echo "  or:  ./use-solution.sh $STEP --keep      code only, state untouched"
  echo "       ./use-solution.sh $STEP --force     reset anyway (not the agent"
  echo "                                           on :8000? then this is you)"
  exit 1
fi

# ── the code ───────────────────────────────────────────────────────────────
rm -rf agent/concert
cp -r "$MATCH/concert" agent/
find agent -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# From step 8 on there is a second package — the nightly workflow, served as
# its own app so `adk web` and Pub/Sub can both address it by name.
EXTRA=""
if [ -d "$MATCH/nightly" ]; then
  rm -rf agent/nightly
  cp -r "$MATCH/nightly" agent/
  EXTRA=" (concert + nightly"
else
  rm -rf agent/nightly
fi

# Step 10 also ships the deployable surface: an entrypoint, a container, and a
# copy of the front end. All of it lives in agent/, because agent/ is the build
# context `gcloud run deploy --source agent` uploads.
rm -f agent/main.py agent/server.py agent/Dockerfile agent/requirements.txt
rm -rf agent/monstertix
DEPLOYABLE=""
for f in main.py Dockerfile requirements.txt; do
  [ -f "$MATCH/$f" ] && cp "$MATCH/$f" "agent/$f" && DEPLOYABLE="$DEPLOYABLE $f"
done
if [ -d "$MATCH/monstertix" ]; then
  cp -r "$MATCH/monstertix" agent/monstertix
  DEPLOYABLE="$DEPLOYABLE monstertix/"
fi
[ -n "$DEPLOYABLE" ] && EXTRA="${EXTRA:+$EXTRA} +$DEPLOYABLE"
# `adk web` treats EVERY directory under agent/ as an app and errors on any that
# is not one — which empties the dropdown. A stray ./memory or ./artifacts left
# by running something from inside agent/ is enough to do it.
for d in agent/*/; do
  case "$(basename "$d")" in
    concert|nightly|monstertix) ;;
    *) rm -rf "$d"; echo "→ tidied  removed stray agent/$(basename "$d")/" ;;
  esac
done

[ -n "$EXTRA" ] && EXTRA="$EXTRA"
echo "→ loaded  $(basename "$MATCH")${EXTRA}"

# ── the state around it ────────────────────────────────────────────────────
if [ -z "$KEEP" ]; then
  # Memory. A step can have its own starting file; otherwise everyone gets the
  # same one. See seed/memory/README.md.
  SEED=seed/memory/step"$STEP".md
  [ -f "$SEED" ] || SEED=seed/memory/default.md
  mkdir -p memory
  cp "$SEED" memory/userx.md
  echo "→ memory  $SEED → memory/userx.md"

  # Sessions. Rebuilt rather than emptied, because step 4 opens a conversation
  # that has to already exist and be two days old.
  rm -f sessions.db
  if "$PY" -m seed.session >/dev/null 2>&1; then
    echo "→ session sessions.db rebuilt, with 'two-days-ago' back in it"
  else
    echo "⚠ session sessions.db deleted, but reseeding failed."
    echo "          run '$PY -m seed.session' and read the error."
  fi

  # Artifacts. The seat maps a previous run saved are not this run's.
  rm -rf artifacts
  mkdir -p artifacts
  echo "→ files   artifacts/ emptied"
else
  echo "→ state   left alone (--keep)"
fi

# `adk web` defaults to --reload (uvicorn restarts the server on file changes)
# but --reload_agents=false. Whether a running server picks up new agent code is
# therefore not something to rely on. Restarting takes two seconds and removes
# the question, which is worth more than being right about it.
if lsof -ti:8000 >/dev/null 2>&1; then
  echo ""
  echo "⚠ adk web is running on :8000. Restart it so you know it is running"
  echo "  the code you just loaded, and check the tool list in the left panel."
fi

echo ""
echo "  Now go and read what changed:"
for f in agent/concert/*.py; do
  case "$(basename "$f")" in
    venue.py|config.py|__init__.py) ;;
    *) printf "      %-34s %s\n" "$f" \
         "$(grep -m1 -oE '^"""[^"]*' "$f" | sed 's/^"""//' | cut -c1-52)" ;;
  esac
done
echo ""
echo "  Then start adk web in terminal 1, and press RESET THE VENUE on the panel."
