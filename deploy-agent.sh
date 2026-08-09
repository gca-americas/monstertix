#!/usr/bin/env bash
# Module 6 — put your own agent on Cloud Run, and give it an alarm clock.
#
#     ./deploy-agent.sh
#
# Five things, in order:
#   1. deploy agent/ to Cloud Run with a Pub/Sub trigger endpoint
#   2. a topic for Cloud Scheduler to publish to
#   3. a service account Pub/Sub can push as
#   4. a push subscription: topic → your agent's trigger endpoint
#   5. a Scheduler job that publishes on a cron
#
# Each student gets their own service, named after them, exactly like the venue.
# Re-running is safe.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] && set -a && . ./.env && set +a

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT — run ./setup.sh}"
REGION="${AGENT_REGION:-us-central1}"

WHO=$(gcloud config get-value account 2>/dev/null | cut -d@ -f1 \
      | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/-*$//' | cut -c1-24)
SERVICE="${AGENT_SERVICE:-concert-${WHO:-student}}"
TOPIC="${PRESALE_TOPIC:-presale-${WHO:-student}}"
SA="concert-trigger"
CRON="${PRESALE_CRON:-0 3 * * *}"

if [ ! -f agent/main.py ]; then
  echo "✗ agent/main.py is missing. Run ./use-solution.sh 10 first."
  exit 1
fi

# Durable state, or an honest warning. A Cloud Run container's filesystem is
# destroyed when the instance goes away, so sqlite in /tmp is a session store
# that forgets — silently, overnight, exactly when nobody is watching.
if [ -n "${CLOUD_SESSION_SERVICE_URI:-}" ]; then
  SESSION_URI="$CLOUD_SESSION_SERVICE_URI"
  ARTIFACT_URI="${CLOUD_ARTIFACT_SERVICE_URI:?run ./setup-cloud-state.sh}"
  SQL_FLAG=(--add-cloudsql-instances "${SQL_CONNECTION_NAME:?run ./setup-cloud-state.sh}")
  echo "→ state     Cloud SQL + $ARTIFACT_URI"
else
  SESSION_URI="sqlite+aiosqlite:////tmp/sessions.db"
  ARTIFACT_URI="gs://none"
  SQL_FLAG=()
  echo "⚠ state     sqlite in /tmp — this DIES with the container."
  echo "            Run ./setup-cloud-state.sh first for a real database."
fi

echo "→ project  $PROJECT"
echo "→ region   $REGION"
echo "→ service  $SERVICE"
echo "→ topic    $TOPIC"
echo ""

# 1. The agent. Cloud Run or GKE only — Agent Runtime does not accept scheduled
#    or event-driven triggers, which is the whole point of this step.
#
#    --session_service_uri matters more than it looks. Trigger sessions default
#    to in-memory, so without it a 3am run that joins a queue has forgotten its
#    ticket by the time anything wakes it.
#
#    The GOOGLE_* vars are not optional either. Credentials come free on Cloud
#    Run — the service account is the identity — but the genai client still has
#    to be told which project and location to call Vertex in, and config.py
#    exits at import if they are missing. A container that exits at import looks
#    like "failed to listen on PORT", which is a long way from the real cause.
#
#    ^|^ is gcloud's alternative delimiter. The default is a comma, which the
#    session URI would survive — but `@` would NOT, because the URI contains one
#    between the password and the host. Splitting on it silently truncates the
#    URI to `postgresql+asyncpg://user:password` and the container dies at
#    startup with an unrelated-looking int() error.
# `gcloud run deploy --source`, not `adk deploy cloud_run`.
#
# adk deploy generates its own entrypoint, which serves the agent and nothing
# else — no MonsterTix, no /wake. It has no flag for supplying your own. So this
# builds agent/ with its own Dockerfile, which is the same command the venue has
# used since Module 1.
echo "→ deploying (3-4 minutes)"
gcloud run deploy "$SERVICE" \
  --source agent \
  --project "$PROJECT" --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "^|^SESSION_SERVICE_URI=$SESSION_URI|ARTIFACT_SERVICE_URI=$ARTIFACT_URI|VENUE_URL=${VENUE_URL:-}|UNATTENDED=1|MEMORY_USER=${MEMORY_USER:-userx}|GOOGLE_CLOUD_PROJECT=$PROJECT|GOOGLE_CLOUD_LOCATION=${GOOGLE_CLOUD_LOCATION:-global}|GOOGLE_GENAI_USE_VERTEXAI=true|ADK_MODEL=${ADK_MODEL:-gemini-2.5-flash}" \
  "${SQL_FLAG[@]}" \
  --quiet

# UNATTENDED tells the graph there is nobody to answer a question. Without it
# the 3am run stops on "what are you willing to spend?" and waits for a person
# who is asleep, and no tickets are ever bought.
#
# `adk deploy cloud_run` has no flag for environment variables, so this is a
# second call rather than part of the deploy.
[ -n "${STATE_BUCKET:-}" ] && gcloud run services update "$SERVICE" \
  --project "$PROJECT" --region "$REGION" \
  --update-env-vars MEMORY_DIR="$STATE_BUCKET/memory" --quiet >/dev/null
echo "→ env      state URIs, VENUE_URL, UNATTENDED=1"

URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" \
        --region "$REGION" --format='value(status.url)')
[ -n "$URL" ] || { echo "✗ deployed, but could not read the service URL"; exit 1; }
echo "→ agent    $URL"

# 2. The topic Scheduler publishes to.
gcloud pubsub topics create "$TOPIC" --project "$PROJECT" 2>/dev/null \
  && echo "→ topic    $TOPIC created" || echo "→ topic    $TOPIC exists"

# 3. A service account Pub/Sub can push as, allowed to invoke the agent.
gcloud iam service-accounts create "$SA" --project "$PROJECT" \
  --display-name="Concert presale trigger" 2>/dev/null || true
SA_EMAIL="$SA@$PROJECT.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding "$SERVICE" \
  --project "$PROJECT" --region "$REGION" \
  --member="serviceAccount:$SA_EMAIL" --role=roles/run.invoker --quiet >/dev/null
echo "→ iam      $SA_EMAIL may invoke $SERVICE"

# 4. topic → the trigger endpoint. One app, `concert`, whose root_agent IS the
#    graph — so waking the app runs the graph.
ENDPOINT="$URL/apps/concert/trigger/pubsub"
gcloud pubsub subscriptions create "$TOPIC-push" --project "$PROJECT" \
  --topic="$TOPIC" \
  --push-endpoint="$ENDPOINT" \
  --push-auth-service-account="$SA_EMAIL" 2>/dev/null \
  && echo "→ push     → $ENDPOINT" \
  || echo "→ push     subscription exists"

# 5. The alarm clock. This is clock.py from Module 2, run by Google instead of
#    by your terminal: it has retries, a timezone, and it does not stop when
#    you close your laptop.
gcloud scheduler jobs create pubsub "$TOPIC" --project "$PROJECT" \
  --location="$REGION" --schedule="$CRON" --time-zone="Etc/UTC" \
  --topic="$TOPIC" --message-body='{"kind":"presale_drop"}' 2>/dev/null \
  && echo "→ schedule $CRON" || echo "→ schedule job exists"

echo ""
echo "✓ deployed."
echo ""
echo "  fire it now, without waiting for 3am:"
echo "      gcloud scheduler jobs run $TOPIC --location=$REGION --project=$PROJECT"
echo ""
echo "  then read what it did:"
echo "      gcloud run services logs read $SERVICE --region=$REGION --project=$PROJECT --limit=50"
echo ""
echo "  and the front door — the page, not the dev UI:"
echo "      $URL"
echo ""
echo "  and clean up when you are done:"
echo "      ./destroy-agent.sh"
