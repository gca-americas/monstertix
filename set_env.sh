# Source this in every terminal you open:  . ./set_env.sh
#
# It only sets things that never change between steps — your project, your
# venue's URL, the model. Everything ADK-specific stays visible on the command
# line, because in this workshop those flags ARE the material.

_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# The project root, as an absolute path. Every --session_service_uri and
# --artifact_service_uri uses this rather than $PWD, because $PWD is wrong the
# moment you run a command from anywhere but the root — and it fails quietly,
# by creating a second empty sessions.db instead of erroring.
export WORKSHOP="$_root"

# Your answers from ./setup.sh
if [ -f "$_root/.env" ]; then
  set -a
  . "$_root/.env"
  set +a
fi

# The virtualenv, so `adk` and `python` are the right ones
if [ -d "$_root/.venv" ]; then
  . "$_root/.venv/bin/activate"
fi

export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-$(cat "$HOME/project_id.txt" 2>/dev/null)}"
# Two different ideas, and they are not interchangeable.
#   LOCATION  where the MODEL is served. "global" is right for Gemini on Vertex.
#   REGION    where SERVICES live: Cloud Run, Cloud SQL, buckets, Pub/Sub,
#             Scheduler. Every deploy script reads this one.
export GOOGLE_CLOUD_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
export GOOGLE_CLOUD_REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
export GOOGLE_GENAI_USE_VERTEXAI="${GOOGLE_GENAI_USE_VERTEXAI:-true}"
export ADK_MODEL="${ADK_MODEL:-gemini-2.5-flash}"

# `. ./set_env.sh local` points this terminal at a venue on your own machine,
# without touching .env. Rehearse with it, open a new terminal to go back.
# Editing VENUE_URL in .env is how you end up debugging a Cloud Run venue that
# was never being called.
_local_arg=""
if [ "${1:-}" = "local" ]; then
  VENUE_URL="http://127.0.0.1:8080"
  _local_arg="yes"
fi

export VENUE_URL="${VENUE_URL:-http://127.0.0.1:8080}"
export AGENT_URL="${AGENT_URL:-http://127.0.0.1:8000}"
# Hardcoded, not defaulted. `${MEMORY_USER:-userx}` politely keeps whatever is
# already in the shell, so anyone who exported an old value once kept it through
# every restart — and a wrong value does not error, it just reads a file that is
# not there and reports an empty memory.
export MEMORY_DIR="$_root/memory"
export MEMORY_USER="userx"

echo "  folder   $WORKSHOP"
echo "  project  $GOOGLE_CLOUD_PROJECT"
echo "  model    $ADK_MODEL"
# Say which venue this terminal is talking to, and say it loudly when it is a
# local one — a local venue that nobody notices is a whole afternoon.
case "$VENUE_URL" in
  *127.0.0.1*|*localhost*)
    echo "  venue    $VENUE_URL   ← local, not Cloud Run"
    if [ -n "$_local_arg" ]; then
      echo "           (from 'local' — a new terminal without it reads .env)"
    else
      echo "           (this is what .env says. run 'python -m venue')"
    fi
    ;;
  *) echo "  venue    $VENUE_URL" ;;
esac

unset _root _local_arg
