#!/usr/bin/env bash
# One-time setup. Works in Cloud Shell, on a laptop, anywhere with Python 3.11+.
set -euo pipefail
cd "$(dirname "$0")"

# --- 1. Python ------------------------------------------------------------
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)')
if [ "$PY_OK" != "1" ]; then
  echo "✗ Python 3.11+ required (ADK 2 workflows need it). Found: $(python3 --version)"
  exit 1
fi

# --- 2. Dependencies ------------------------------------------------------
# Re-running setup.sh has to work. The codelab tells you to do it after
# `gcloud auth application-default login`, and several errors below say so too.
if command -v uv >/dev/null 2>&1; then
  if [ -d .venv ]; then
    echo "→ venv       reusing .venv"
  else
    echo "→ venv       creating with uv"
    uv venv .venv --python 3.11 >/dev/null 2>&1 || uv venv .venv >/dev/null
  fi
  uv pip install -q --python .venv/bin/python -r requirements.txt
else
  if [ -d .venv ]; then
    echo "→ venv       reusing .venv"
  else
    echo "→ venv       creating with python -m venv (slower)"
    python3 -m venv .venv
    .venv/bin/pip install -q --upgrade pip
  fi
  .venv/bin/pip install -q -r requirements.txt
fi

# --- 3. Config ------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "→ created .env"
fi

mkdir -p artifacts memory
# The agent APPENDS to this file every time it calls remember(), so after a few
# runs it fills up with duplicate booking lines. seed/memory/ holds the pristine
# copies, and use-solution.sh restores from them at the start of every step.
[ -f memory/userx.md ] || cp seed/memory/default.md memory/userx.md

# --- 4. Google Cloud ------------------------------------------------------
# We use Vertex AI, so auth is Application Default Credentials rather than an
# API key. Everything below is a check with a fix attached, never a silent pass.
set +e

echo ""
if ! command -v gcloud >/dev/null 2>&1; then
  echo "✗ gcloud not found. Install the Google Cloud CLI, or use Cloud Shell"
  echo "  where it is already present:  https://shell.cloud.google.com"
  exit 1
fi

# --- which project? -------------------------------------------------------
# Everyone brings their own. We ask once and remember the answer in $HOME,
# which in Cloud Shell survives the idle timeout and a re-clone of this repo.
#
#   PROJECT_ID=x ./setup.sh   overrides and re-saves
#   rm ~/project_id.txt       forget it and ask again
PROJECT_FILE="$HOME/project_id.txt"
PROJECT=""

if [ -n "${PROJECT_ID:-}" ]; then
  PROJECT="$PROJECT_ID"
elif [ -n "${GOOGLE_CLOUD_PROJECT:-}" ]; then
  # Already set in this shell — somebody has configured their environment, so
  # use it quietly rather than asking a question they have already answered.
  PROJECT="$GOOGLE_CLOUD_PROJECT"
  REMEMBERED=env
elif [ -f "$PROJECT_FILE" ]; then
  PROJECT=$(tr -d '[:space:]' < "$PROJECT_FILE")
  [ -n "$PROJECT" ] && REMEMBERED=yes
fi

if [ -z "$PROJECT" ]; then
  SUGGESTED=$(gcloud config get-value project 2>/dev/null)
  [ "$SUGGESTED" = "(unset)" ] && SUGGESTED=""

  if [ ! -t 0 ]; then
    # No terminal to ask on — CI, or a piped run.
    if [ -n "$SUGGESTED" ]; then
      PROJECT="$SUGGESTED"
    else
      echo "✗ No project id. Run interactively, or:  PROJECT_ID=your-project ./setup.sh"
      exit 1
    fi
  else
    echo ""
    echo "  Which Google Cloud project should this workshop use?"
    echo "  Find yours at https://console.cloud.google.com  (top-left picker)"
    echo ""
    while [ -z "$PROJECT" ]; do
      if [ -n "$SUGGESTED" ]; then
        printf "  Project id [%s]: " "$SUGGESTED"
      else
        printf "  Project id: "
      fi
      read -r ANSWER
      PROJECT=$(printf '%s' "${ANSWER:-$SUGGESTED}" | tr -d '[:space:]')
      [ -z "$PROJECT" ] && echo "  (a project id is required)"
    done
    echo ""
  fi
fi

# Prove it exists and we can see it, before anything downstream depends on it.
if ! gcloud projects describe "$PROJECT" >/dev/null 2>&1; then
  echo "✗ Cannot access project '$PROJECT'."
  echo "  Either the id is wrong, or your account has no access to it."
  echo ""
  echo "  Projects you can see:"
  gcloud projects list --format='value(projectId)' 2>/dev/null | sed 's/^/      /' | head -10
  echo ""
  echo "  Then re-run:   rm -f $PROJECT_FILE && ./setup.sh"
  exit 1
fi

printf '%s\n' "$PROJECT" > "$PROJECT_FILE"
gcloud config set project "$PROJECT" >/dev/null 2>&1
if [ "${REMEMBERED:-}" = "env" ]; then
  echo "→ project    $PROJECT  (from GOOGLE_CLOUD_PROJECT in your shell)"
elif [ "${REMEMBERED:-}" = "yes" ]; then
  echo "→ project    $PROJECT  (remembered — rm $PROJECT_FILE to change)"
else
  echo "→ project    $PROJECT  (saved to $PROJECT_FILE)"
fi

# Location and region: use whatever is already set, and only fall back if it is
# not. Somebody with GOOGLE_CLOUD_LOCATION exported has told us where they work,
# and asking again or overwriting it would be rude.
#
#   GOOGLE_CLOUD_LOCATION   where the MODEL is served. "global" is right for
#                           Gemini on Vertex and is not a Cloud Run region.
#   GOOGLE_CLOUD_REGION     where SERVICES live: Cloud Run, Cloud SQL, buckets,
#                           Pub/Sub, Scheduler. Everything deployable uses this.
LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
REGION="${GOOGLE_CLOUD_REGION:-$(gcloud config get-value run/region 2>/dev/null)}"
case "$REGION" in ""|"(unset)") REGION="us-central1" ;; esac
export GOOGLE_CLOUD_LOCATION="$LOCATION" GOOGLE_CLOUD_REGION="$REGION"
echo "→ location   $LOCATION  (model)   ·   region  $REGION  (services)"

# The project id is the one line in .env that differs per student, so write it
# rather than making them edit it by hand.
if grep -q '^GOOGLE_CLOUD_PROJECT=' .env; then
  sed -i.bak "s|^GOOGLE_CLOUD_PROJECT=.*|GOOGLE_CLOUD_PROJECT=$PROJECT|" .env && rm -f .env.bak
else
  printf 'GOOGLE_CLOUD_PROJECT=%s\n' "$PROJECT" >> .env
fi

for pair in "GOOGLE_CLOUD_LOCATION=$LOCATION" "GOOGLE_CLOUD_REGION=$REGION"; do
  key="${pair%%=*}"
  if grep -q "^$key=" .env; then
    sed -i.bak "s|^$key=.*|$pair|" .env && rm -f .env.bak
  else
    printf '%s\n' "$pair" >> .env
  fi
done

. ./.env 2>/dev/null
GOOGLE_CLOUD_PROJECT="$PROJECT"

# Application Default Credentials. Rather than telling you to go and run a
# command and come back, just run it — one browser click in Cloud Shell.
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  if [ -t 0 ]; then
    echo "→ auth       no credentials yet, opening the sign-in flow"
    echo ""
    gcloud auth application-default login
    echo ""
  fi
  if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
    echo "✗ Still no Application Default Credentials. Run this, then ./setup.sh again:"
    echo ""
    echo "      gcloud auth application-default login"
    exit 1
  fi
fi
echo "→ auth       ok"

# Quota project mismatches are the single most common cause of a confusing
# 403 later, so fix it here rather than during Module 1.
gcloud auth application-default set-quota-project "$PROJECT" >/dev/null 2>&1 \
  && echo "→ quota      set to $PROJECT"

# Everything the workshop actually touches. Enabling an API that is already on
# is a no-op, but each call still costs a round trip — so we diff first and
# enable only what is missing, in one batched call.
REQUIRED_APIS=(
  aiplatform.googleapis.com        # Vertex AI — the models, every step
  run.googleapis.com               # Cloud Run — the venue, and the agent in step 8
  cloudbuild.googleapis.com        # builds the container for `run deploy --source`
  artifactregistry.googleapis.com  # where Cloud Build puts the image
  storage.googleapis.com           # Cloud Build's source staging bucket
  pubsub.googleapis.com            # step 8 — the trigger topic
  cloudscheduler.googleapis.com    # step 8 — the 3am cron
  cloudtrace.googleapis.com        # step 8 — seeing what happened overnight
  logging.googleapis.com           # step 8 — structured logs from an unattended run
  sqladmin.googleapis.com          # step 10 — Cloud SQL, where sessions live in the cloud
)

ENABLED=$(gcloud services list --enabled --project "$PROJECT" --format='value(config.name)' 2>/dev/null || true)
MISSING=()
for api in "${REQUIRED_APIS[@]}"; do
  grep -qx "$api" <<<"$ENABLED" || MISSING+=("$api")
done

if [ ${#MISSING[@]} -eq 0 ]; then
  echo "→ apis       all ${#REQUIRED_APIS[@]} already enabled"
else
  echo "→ apis       enabling ${#MISSING[@]} of ${#REQUIRED_APIS[@]} (this can take a minute)"
  for api in "${MISSING[@]}"; do echo "               $api"; done
  if gcloud services enable "${MISSING[@]}" --project "$PROJECT" 2>/tmp/svc-enable.err; then
    echo "→ apis       enabled"
  else
    echo ""
    echo "✗ Could not enable APIs on $PROJECT."
    echo "  $(head -2 /tmp/svc-enable.err | tr '\n' ' ')"
    echo ""
    echo "  If you do not own this project, ask someone who does to run:"
    echo ""
    echo "      gcloud services enable ${MISSING[*]} \\"
    echo "        --project $PROJECT"
    echo ""
    echo "  If it says billing is not enabled, the project needs a billing"
    echo "  account attached before Vertex AI or Cloud Run will work."
    exit 1
  fi
fi

# Prove the model actually answers, so nobody discovers a 404 mid-workshop.
MODEL="${ADK_MODEL:-gemini-2.5-flash}"
CHECK=$(.venv/bin/python - "$PROJECT" "$LOCATION" "$MODEL" <<'PY' 2>&1
import sys
try:
    from google import genai
    c = genai.Client(vertexai=True, project=sys.argv[1], location=sys.argv[2])
    c.models.generate_content(model=sys.argv[3], contents="hi")
    print("OK")
except Exception as exc:
    print(f"FAIL {type(exc).__name__}: {str(exc)[:160]}")
PY
)
set -e

if [ "${CHECK:0:2}" = "OK" ]; then
  echo "→ model      $MODEL responds"

  # --- 5. The pre-loaded session ------------------------------------------
  # Step 3 opens a session that has already been alive for two days. Without
  # this there is nothing to open. Safe to re-run: it rebuilds only the
  # 'two-days-ago' session and leaves the student's own work alone.
  if .venv/bin/python -m seed.session >/tmp/seed.log 2>&1; then
    echo "→ seed       session 'two-days-ago' ready (13 events, 2 days old)"
  else
    echo "→ seed       FAILED — step 3 has nothing to open"
    tail -4 /tmp/seed.log | sed 's/^/               /'
    echo "               retry with:  python -m seed.session"
  fi

  # ── Cloud SQL, started now and collected in step 10 ─────────────────────
  #
  # Creating a Postgres instance takes eight to twelve minutes, which is most of
  # a module. Nobody should sit and watch it, so it starts here, in the
  # background, while the workshop gets on with Module 1 — and step 10 picks up
  # whatever finished.
  #
  # db-f1-micro is the smallest thing Cloud SQL sells. It is the wrong size for
  # anything real and exactly right for one student's sessions table.
  SQL_INSTANCE="${SQL_INSTANCE:-workshop-sessions}"
  if gcloud sql instances describe "$SQL_INSTANCE" --project "$PROJECT" >/dev/null 2>&1; then
    echo "→ cloudsql   $SQL_INSTANCE already exists"
  else
    nohup gcloud sql instances create "$SQL_INSTANCE" \
      --project "$PROJECT" --database-version=POSTGRES_15 \
      --tier=db-f1-micro --region="$REGION" \
      --storage-size=10 --storage-type=HDD --no-backup --quiet \
      >"$HOME/.cloudsql-create.log" 2>&1 &
    echo "→ cloudsql   creating $SQL_INSTANCE in the background (~10 min)"
    echo "             log: ~/.cloudsql-create.log — step 10 needs it, nothing before does"
  fi


  # ── The venue, deployed now so the workshop starts with a world ──────────
  #
  # Every student gets their own. A shared one would mean the moment somebody
  # presses SELL THE GOOD SEATS, everyone else's agent starts failing for no
  # visible reason. `gcloud run deploy` is idempotent, so re-running setup
  # redeploys over the top rather than erroring.
  if ./deploy-venue.sh >/tmp/venue-deploy.log 2>&1; then
    # gcloud bolds the URL, so a greedy [^ ]* match swallows the trailing ANSI
    # reset and prints as a stray [m. Matching only URL-safe characters stops at
    # the escape byte instead, with no sed and no locale trouble.
    VENUE_URL=$(grep -m1 -ao 'https://venue-[A-Za-z0-9._~:/?#@!$&()*+,;=%-]*' \
                /tmp/venue-deploy.log)
    echo "→ venue      deployed  $VENUE_URL"
  else
    echo "→ venue      FAILED"
    tail -5 /tmp/venue-deploy.log | sed 's/^/               /'
    echo "               retry with:  ./deploy-venue.sh"
  fi

  echo ""
  echo "✓ setup complete."
  echo ""
  echo "  check it:  ./verify.sh"
  echo "  then:      source .venv/bin/activate"
  echo "             adk web agent      # the exact command is in the codelab"
else
  echo "→ model      $MODEL FAILED"
  echo ""
  echo "  $CHECK"
  echo ""
  echo "  If that is a 404: '-latest' aliases are AI Studio only and do not"
  echo "  exist on Vertex. Set a pinned id in .env, e.g. ADK_MODEL=gemini-2.5-flash"
  echo "  List what this project actually has:"
  echo ""
  echo "      .venv/bin/python -c \"from google import genai; \\"
  echo "        [print(m.name) for m in genai.Client(vertexai=True, \\"
  echo "        project='$PROJECT', location='global').models.list()]\""
  exit 1
fi
