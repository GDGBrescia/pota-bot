# Pota Bot su Telegram — design

> Deciso il 16 ottobre 2026 (Nicola, con Matteo e Soumaya). Piano di implementazione: [`superpowers/plans/2026-10-16-pota-bot-telegram.md`](superpowers/plans/2026-10-16-pota-bot-telegram.md).

## Obiettivo

Portare Pota Bot (l'agente costruito al workshop del 1/10/2026) in un gruppo Telegram, online 24/7, e mostrarne il deploy in un webinar. Prima si prova tutto su un **gruppo finto**; il gruppo vero della community arriva dopo.

## Cosa fa

1. **Chat nel gruppo.** Nei gruppi risponde a `/chiedi <domanda>` o quando rispondi a un suo messaggio (le menzioni `@username` solo con la privacy mode disattivata); in privato risponde sempre. Strumenti del workshop: eventi, FAQ, news, proposte di temi. Comandi: `/chiedi`, `/start`, `/help`, `/privacy`.
2. **Digest settimanale.** Ogni lunedì alle 9:00 (Europe/Rome) pubblica nel gruppo le novità della settimana, prese da **feed RSS scelti da noi** (`pota_bot/data/feeds.json`), divise nelle categorie del sondaggio della community.
3. **Proposte di temi salvate** in Firestore (senza nome né id di chi propone).

## Architettura

```
Telegram ──webhook──► Cloud Run (FastAPI, max 1 istanza)
                        ├─ POST /telegram/webhook  → PotaBot → AgentChat (ADK + Gemini) → risposta
                        │                                         └─ propose_topic → ProposalStore (Firestore)
                        ├─ POST /tasks/digest      ← Cloud Scheduler (lun 9:00) → feed RSS → Gemini → messaggio
                        └─ GET  /health
Segreti (Secret Manager): token Telegram, chiave Gemini, segreto webhook, token dei task
```

## Decisioni

| Decisione | Scelta | Perché |
|---|---|---|
| Modello | `gemini-3.5-flash-lite` via **API key Gemini** (AI Studio) | Free tier per sviluppo e test; per il gruppo vero serve una chiave a pagamento (i termini Gemini ammettono solo servizi a pagamento per utenti nello Spazio economico europeo). Cambia solo il segreto |
| Fonti del digest | Feed RSS, niente Google Search | Google Search non è nel free tier; le fonti le controlliamo noi; ogni notizia ha il link per costruzione |
| Privacy mode di Telegram | Attiva (default); nei gruppi si usa /chiedi o la risposta a un messaggio del bot; le menzioni solo con privacy disattivata | Il bot non riceve i messaggi della chat che non lo riguardano |
| Ricezione messaggi | Webhook (produzione), polling (solo locale) | Cloud Run scala a zero tra un messaggio e l'altro |
| Lavoro nella richiesta | La risposta si genera **prima** di restituire 200 a Telegram | Su Cloud Run la CPU viene ridotta dopo la risposta: un task in background potrebbe non finire |
| Istanze | `--max-instances 1` | Il limite di messaggi per persona sta in memoria; tetto ai costi |
| Sessioni di conversazione | In memoria, una per (chat, persona) | Conversazioni brevi; si perdono al riavvio, accettabile |
| Proposte | Interfaccia `ProposalStore`: Firestore in produzione, memoria in locale e nei test | Stesso codice ovunque, test senza cloud |
| Sicurezza webhook | Header `X-Telegram-Bot-Api-Secret-Token` confrontato con un segreto | Senza, chiunque potrebbe far parlare il bot |
| Sicurezza digest | Header `X-Pota-Task-Token` impostato nel job di Cloud Scheduler | Più semplice della verifica OIDC; il token è visibile solo a chi gestisce il progetto |
| Guardrail aggiunti | 20 messaggi/ora per persona; digest con link verificati (solo link presenti nei feed), altrimenti versione di riserva senza AI | Bot pubblico: costi e affidabilità |
| Region | Cloud Run `europe-west8` (Milano), Scheduler `europe-west1`, Firestore `eur3` | Vicino agli utenti; località supportate dai servizi |

## Fuori perimetro (per ora)

Sessioni persistenti, pannello per leggere le proposte (si usa la console Firestore), multi-agente, voce.
