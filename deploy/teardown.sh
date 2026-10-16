#!/usr/bin/env bash
# Smonta il servizio (per rifare il deploy da zero nel webinar).
# NON tocca segreti e Firestore: le proposte salvate restano.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.env
G="gcloud --project=$PROJECT_ID --quiet"

TOKEN=$($G secrets versions access latest --secret=pota-telegram-token)
curl -fsS -X POST "https://api.telegram.org/bot${TOKEN}/deleteWebhook" >/dev/null && echo "Webhook rimosso"
$G scheduler jobs delete pota-bot-digest --location "$SCHEDULER_REGION" 2>/dev/null && echo "Job del digest rimosso" || true
$G run services delete "$SERVICE" --region "$REGION" 2>/dev/null && echo "Servizio Cloud Run rimosso" || true
echo "✅ Smontato. Per ripartire: ./deploy/deploy.sh"
