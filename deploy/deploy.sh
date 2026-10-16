#!/usr/bin/env bash
# Deploy di Pota Bot su Google Cloud, da zero o in aggiornamento.
# Uso: ./deploy/deploy.sh   (legge deploy/config.env)
# Al primo avvio chiede token Telegram e chiave Gemini (oppure: TELEGRAM_BOT_TOKEN=... GEMINI_API_KEY=... ./deploy/deploy.sh)
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.env
: "${PROJECT_ID:?Manca PROJECT_ID in deploy/config.env}"
: "${TELEGRAM_BOT_USERNAME:?Manca TELEGRAM_BOT_USERNAME}"
: "${TELEGRAM_DIGEST_CHAT_ID:?Manca TELEGRAM_DIGEST_CHAT_ID}"

G="gcloud --project=$PROJECT_ID --quiet"
SA="pota-bot@${PROJECT_ID}.iam.gserviceaccount.com"
step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$1"; }

secret_exists() { $G secrets describe "$1" >/dev/null 2>&1; }
create_secret() { printf '%s' "$2" | $G secrets create "$1" --data-file=- --replication-policy=automatic >/dev/null; }
ask_secret() {  # nome, variabile d'ambiente, domanda
  secret_exists "$1" && return
  local value="${!2:-}"
  if [ -z "$value" ]; then read -r -s -p "$3: " value; echo; fi
  create_secret "$1" "$value"
}

step "1/7 Abilito le API"
$G services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com

step "2/7 Firestore"
$G firestore databases describe --database="(default)" >/dev/null 2>&1 || \
  $G firestore databases create --location="$FIRESTORE_LOCATION" --type=firestore-native

step "3/7 Segreti in Secret Manager"
ask_secret pota-telegram-token TELEGRAM_BOT_TOKEN "Token del bot Telegram"
ask_secret pota-gemini-key GEMINI_API_KEY "Chiave API Gemini"
secret_exists pota-webhook-secret || create_secret pota-webhook-secret "$(openssl rand -hex 24)"
secret_exists pota-task-token || create_secret pota-task-token "$(openssl rand -hex 24)"

step "4/7 Service account con i permessi minimi"
$G iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  $G iam service-accounts create pota-bot --display-name="Pota Bot"
for role in roles/datastore.user roles/secretmanager.secretAccessor; do
  $G projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$role" --condition=None >/dev/null
done

step "5/7 Build e deploy su Cloud Run (2-4 minuti)"
$G run deploy "$SERVICE" --source . --region "$REGION" --service-account "$SA" \
  --allow-unauthenticated --min-instances 0 --max-instances 1 --memory 1Gi --timeout 120 \
  --set-env-vars "TELEGRAM_BOT_USERNAME=$TELEGRAM_BOT_USERNAME,TELEGRAM_DIGEST_CHAT_ID=$TELEGRAM_DIGEST_CHAT_ID,POTA_USE_FIRESTORE=true" \
  --set-secrets "TELEGRAM_BOT_TOKEN=pota-telegram-token:latest,GOOGLE_API_KEY=pota-gemini-key:latest,TELEGRAM_WEBHOOK_SECRET=pota-webhook-secret:latest,POTA_TASK_TOKEN=pota-task-token:latest"
URL=$($G run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
curl -fsS "$URL/healthz" >/dev/null && echo "Servizio attivo: $URL"

step "6/7 Collego Telegram al servizio (webhook)"
TOKEN=$($G secrets versions access latest --secret=pota-telegram-token)
WEBHOOK_SECRET=$($G secrets versions access latest --secret=pota-webhook-secret)
curl -fsS -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  --data-urlencode "url=${URL}/telegram/webhook" --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message"]' | grep -q '"ok":true' && echo "Webhook impostato"

step "7/7 Digest settimanale con Cloud Scheduler"
TASK_TOKEN=$($G secrets versions access latest --secret=pota-task-token)
JOB_ARGS=(--location "$SCHEDULER_REGION" --schedule "$DIGEST_SCHEDULE" --time-zone "Europe/Rome"
  --uri "$URL/tasks/digest" --http-method POST)
if $G scheduler jobs describe pota-bot-digest --location "$SCHEDULER_REGION" >/dev/null 2>&1; then
  $G scheduler jobs update http pota-bot-digest "${JOB_ARGS[@]}" --update-headers "X-Pota-Task-Token=$TASK_TOKEN"
else
  $G scheduler jobs create http pota-bot-digest "${JOB_ARGS[@]}" --headers "X-Pota-Task-Token=$TASK_TOKEN"
fi

printf '\n\033[1;32m✅ Pota Bot è online: %s\033[0m\n' "$URL"
echo "Digest subito: $G scheduler jobs run pota-bot-digest --location $SCHEDULER_REGION"
