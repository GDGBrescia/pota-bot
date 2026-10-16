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

# Riprova un comando fino a 3 volte: i permessi IAM appena creati possono impiegare qualche secondo a propagarsi.
retry() {
  local n
  for n in 1 2 3; do
    "$@" && return 0
    [ "$n" -lt 3 ] && { echo "Tentativo $n/3 fallito, riprovo tra 10 secondi..." >&2; sleep 10; }
  done
  return 1
}

secret_exists() { $G secrets describe "$1" >/dev/null 2>&1; }
create_secret() { printf '%s' "$2" | $G secrets create "$1" --data-file=- --replication-policy=automatic >/dev/null; }
ask_secret() {  # nome, variabile d'ambiente, domanda
  secret_exists "$1" && return
  local value="${!2:-}"
  if [ -z "$value" ]; then read -r -s -p "$3: " value; echo; fi
  [ -n "$value" ] || { echo "Valore vuoto per $1" >&2; exit 1; }
  create_secret "$1" "$value"
}

step "1/7 Abilito le API"
$G services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com \
  iam.googleapis.com compute.googleapis.com
PROJECT_NUMBER=$($G projects describe "$PROJECT_ID" --format='value(projectNumber)')

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
  retry $G projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$role" --condition=None >/dev/null
done
# Nei progetti nuovi di un'organizzazione la build di Cloud Run usa l'account di default di Compute Engine,
# che ha bisogno di roles/run.builder. Se l'account non esiste ancora non è un errore: avvisiamo e si continua.
if ! retry $G projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" --role="roles/run.builder" --condition=None >/dev/null; then
  echo "ATTENZIONE: non sono riuscito ad assegnare roles/run.builder all'account di default di Compute Engine" >&2
  echo "            (${PROJECT_NUMBER}-compute@developer.gserviceaccount.com, forse non esiste ancora)." >&2
  echo "            Se il passo 5 fallisce con un errore di permessi sulla build, assegnalo a mano e rilancia lo script." >&2
fi

step "5/7 Build e deploy su Cloud Run (2-4 minuti)"
# --no-invoker-iam-check: Telegram deve poter chiamare il servizio senza identità Google. A differenza di
# --allow-unauthenticated funziona anche quando l'organizzazione vieta allUsers; il webhook è protetto dal suo segreto.
$G run deploy "$SERVICE" --source . --region "$REGION" --service-account "$SA" \
  --no-invoker-iam-check --min-instances 0 --max-instances 1 --memory 1Gi --timeout 120 \
  --set-env-vars "TELEGRAM_BOT_USERNAME=$TELEGRAM_BOT_USERNAME,TELEGRAM_DIGEST_CHAT_ID=$TELEGRAM_DIGEST_CHAT_ID,POTA_USE_FIRESTORE=true" \
  --set-secrets "TELEGRAM_BOT_TOKEN=pota-telegram-token:latest,GOOGLE_API_KEY=pota-gemini-key:latest,TELEGRAM_WEBHOOK_SECRET=pota-webhook-secret:latest,POTA_TASK_TOKEN=pota-task-token:latest"
URL=$($G run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
curl -fsS "$URL/healthz" >/dev/null || { echo "healthz fallito: $URL" >&2; exit 1; }
echo "Servizio attivo: $URL"

step "6/7 Collego Telegram al servizio (webhook)"
TOKEN=$($G secrets versions access latest --secret=pota-telegram-token)
WEBHOOK_SECRET=$($G secrets versions access latest --secret=pota-webhook-secret)
RESP=$(curl -sS -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  --data-urlencode "url=${URL}/telegram/webhook" --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message"]')
case "$RESP" in
  *'"ok":true'*) echo "Webhook impostato";;
  *) echo "setWebhook fallito: $RESP" >&2; exit 1;;
esac

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
