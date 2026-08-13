#!/usr/bin/env bash
# Remove everything ./deploy-agent.sh created. The venue is separate — delete
# that with ./destroy-venue.sh or the command in the handbook.
set -euo pipefail
cd "$(dirname "$0")"

_shell_region="${GOOGLE_CLOUD_REGION:-}"
[ -f .env ] && set -a && . ./.env && set +a
[ -n "$_shell_region" ] && export GOOGLE_CLOUD_REGION="$_shell_region"

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${AGENT_REGION:-${GOOGLE_CLOUD_REGION:-us-central1}}"

WHO=$(gcloud config get-value account 2>/dev/null | cut -d@ -f1 \
      | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/-*$//' | cut -c1-24)
SERVICE="${AGENT_SERVICE:-concert-${WHO:-student}}"
TOPIC="${PRESALE_TOPIC:-presale-${WHO:-student}}"

# Scheduler first, so nothing fires at a half-deleted stack.
gcloud scheduler jobs delete "$TOPIC" --location="$REGION" --project "$PROJECT" \
  --quiet 2>/dev/null && echo "→ removed schedule $TOPIC" || echo "→ no schedule"
gcloud pubsub subscriptions delete "$TOPIC-push" --project "$PROJECT" \
  --quiet 2>/dev/null && echo "→ removed subscription" || echo "→ no subscription"
gcloud pubsub topics delete "$TOPIC" --project "$PROJECT" \
  --quiet 2>/dev/null && echo "→ removed topic $TOPIC" || echo "→ no topic"
gcloud run services delete "$SERVICE" --region="$REGION" --project "$PROJECT" \
  --quiet 2>/dev/null && echo "→ removed service $SERVICE" || echo "→ no service"

# The durable state, which is the part that keeps billing. A db-f1-micro
# instance is a few dollars a month and a bucket is pennies, but neither stops
# on its own — deleting the Cloud Run service does not touch either.
SQL_INSTANCE="${SQL_INSTANCE:-workshop-sessions}"
BUCKET="${STATE_BUCKET:-}"

if [ "${1:-}" = "--all" ]; then
  gcloud sql instances delete "$SQL_INSTANCE" --project "$PROJECT" --quiet 2>/dev/null \
    && echo "→ removed Cloud SQL $SQL_INSTANCE" || echo "→ no Cloud SQL instance"
  [ -n "$BUCKET" ] && gcloud storage rm -r "$BUCKET" --project "$PROJECT" --quiet 2>/dev/null \
    && echo "→ removed bucket $BUCKET" || echo "→ no bucket"
else
  echo ""
  echo "  Left alone, because they hold your data and they keep billing:"
  echo "     Cloud SQL   $SQL_INSTANCE"
  echo "     bucket      ${BUCKET:-<not set>}"
  echo ""
  echo "  Delete those too with:  ./destroy-agent.sh --all"
fi

echo ""
echo "✓ Module 6 infrastructure removed."
