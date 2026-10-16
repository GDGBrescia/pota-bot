# 🤖 Pota Bot

**Il bot della community [GDG Brescia](https://gdg.community.dev/gdg-brescia/)**, costruito con [Google ADK](https://adk.dev/) e Gemini durante l'hands-on del **1 ottobre 2026** al CSMT Innovation Hub.

> *Un modello risponde. Un agente risolve.*

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/GDGBrescia/pota-bot/blob/main/workshop.ipynb)

## Cosa fa

- Risponde sugli **eventi** e sulle **domande frequenti** della community.
- Porta le **notizie su AI e Google** nelle 6 categorie scelte dalla community in un sondaggio Telegram.
- **Raccoglie proposte** di temi per i prossimi eventi.
- Lavora **dentro dei guardrail**: niente dati personali, massimo 3 proposte, niente argomenti fuori tema.

## Da dove partire

| Vuoi… | Vai a |
|---|---|
| Imparare come si costruisce un agente, passo per passo | [`workshop.ipynb`](workshop.ipynb): aprilo in Colab dal badge qui sopra. La prima cella scarica tutto il repo (codice e dati), poi si segue il notebook. Niente da installare |
| Far girare il bot sul tuo computer | [Provalo in locale](#provalo-in-locale) |
| Migliorarlo | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Parlarne con la community | [Gruppo Telegram](https://t.me/agentici) |

## Struttura

```
workshop.ipynb        il notebook del workshop (legge i dati da pota_bot/data/)
pota_bot/             lo stesso bot, organizzato in file
  agent.py            l'agente: istruzioni, strumenti, guardrail (root_agent)
  tools.py            gli strumenti: eventi, FAQ, notizie, proposte
  guardrails.py       le regole nel codice
  data/               eventi, FAQ e notizie in JSON
server/               il servizio web per Telegram (webhook e digest)
scripts/              run_polling.py: il bot su Telegram dal tuo computer
deploy/               deploy.sh e teardown.sh per Google Cloud
tests/                test automatici
docs/                 design.md e DEPLOY.md
```

## Provalo in locale

Serve Python 3.10+ e una chiave API gratuita da [AI Studio](https://aistudio.google.com/apikey).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example pota_bot/.env      # poi inserisci la tua GOOGLE_API_KEY
adk web                            # interfaccia web su http://localhost:8000
# oppure: adk run pota_bot         # chat da terminale
```

🔒 La chiave non va mai nel codice né nei commit: `.env` è già escluso da git.

## Su Telegram e in produzione

Su Telegram nei gruppi il bot risponde a `/chiedi <domanda>` o quando rispondi a un suo messaggio (le menzioni `@username` solo con la privacy mode di Telegram disattivata), e sempre in privato. Ogni lunedì alle 9:00 pubblica un **digest settimanale** delle novità prese da feed RSS scelti da noi. Il comando `/privacy` spiega come usa i messaggi.

```bash
pip install -r requirements-dev.txt        # una tantum, con il venv attivo
.venv/bin/python scripts/run_polling.py   # il bot su Telegram dal tuo computer, senza cloud
./deploy/deploy.sh                        # il deploy su Google Cloud (Cloud Run)
```

- Come è fatto e perché: [`docs/design.md`](docs/design.md)
- Il deploy passo per passo (guida del webinar): [`docs/DEPLOY.md`](docs/DEPLOY.md)
- Dipendenze: `requirements-server.txt` (il servizio) e `requirements-dev.txt` (sviluppo e test)
- Test: `.venv/bin/pytest`

## Roadmap

- [x] Workshop: agente con strumenti, stato e guardrail
- [x] Digest settimanale di notizie nel gruppo Telegram della community (nel codice; in prova sul gruppo di test)
- [x] Deploy (Cloud Run + webhook Telegram) (nel codice; in prova sul gruppo di test)
- [x] Test automatici per strumenti e guardrail

Le prossime cose da fare sono nelle [issue](../../issues), a partire da quelle con l'etichetta `good first issue`.

## Licenza

[MIT](LICENSE) © 2026 GDG Brescia
