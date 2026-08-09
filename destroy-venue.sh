#!/usr/bin/env bash
# Delete the venue ./deploy-venue.sh created. It scales to zero, so an idle one
# costs nothing — but leaving services lying around in a shared project is rude.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] && set -a && . ./.env && set +a

PROJECT="${GOOGLE_CLOUD_PROJECT:?set GOOGLE_CLOUD_PROJECT}"
REGION="${VENUE_REGION:-us-central1}"

WHO=$(gcloud config get-value account 2>/dev/null | cut -d@ -f1 \
      | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/-*$//' | cut -c1-30)
SERVICE="${VENUE_SERVICE:-venue-${WHO:-student}}"

gcloud run services delete "$SERVICE" --region="$REGION" --project "$PROJECT" \
  --quiet 2>/dev/null && echo "✓ removed $SERVICE" || echo "→ no service $SERVICE"
