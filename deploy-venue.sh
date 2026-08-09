#!/usr/bin/env bash
# Deploy your own venue to Cloud Run, and write its URL into .env.
#
# Each student gets their own service, named after them. A shared venue would
# mean one person pressing SELL THE GOOD SEATS breaks everybody else's agent.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] && set -a && . ./.env && set +a

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT in .env}"
REGION="${VENUE_REGION:-us-central1}"

# Service names must be lowercase alphanumeric + dashes, so scrub the account.
WHO=$(gcloud config get-value account 2>/dev/null | cut -d@ -f1 \
      | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/-*$//' | cut -c1-30)
SERVICE="${VENUE_SERVICE:-venue-${WHO:-student}}"

echo "→ project   $PROJECT"
echo "→ region    $REGION"
echo "→ service   $SERVICE"
echo ""

gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "VENUE_DB=/tmp/venue.db" \
  --quiet

URL=$(gcloud run services describe "$SERVICE" \
        --project "$PROJECT" --region "$REGION" --format='value(status.url)')

if [ -z "$URL" ]; then
  echo "✗ deployed, but could not read the service URL"
  exit 1
fi

# Point the agent at it. Replace the line rather than appending a second one.
if grep -q '^VENUE_URL=' .env; then
  sed -i.bak "s|^VENUE_URL=.*|VENUE_URL=$URL|" .env && rm -f .env.bak
else
  echo "VENUE_URL=$URL" >> .env
fi

echo ""
echo "→ health    $(curl -s "$URL/health" || echo unreachable)"
echo ""
echo "✓ venue deployed"
echo "   panel     $URL/panel"
echo "   VENUE_URL written to .env"
