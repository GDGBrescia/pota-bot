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
| Imparare come si costruisce un agente, passo per passo | [`workshop.ipynb`](workshop.ipynb) (apri in Colab, niente da installare) |
| Far girare il bot sul tuo computer | [Provalo in locale](#provalo-in-locale) |
| Migliorarlo | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

## Struttura

```
workshop.ipynb        il notebook del workshop (autosufficiente)
pota_bot/             lo stesso bot, organizzato in file
  agent.py            l'agente: istruzioni, strumenti, guardrail (root_agent)
  tools.py            gli strumenti: eventi, FAQ, notizie, proposte
  guardrails.py       le regole nel codice
  data/               eventi, FAQ e notizie in JSON
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

## Roadmap

- [x] Workshop: agente con strumenti, stato e guardrail
- [ ] Digest settimanale di notizie nel gruppo Telegram della community
- [ ] Deploy (Cloud Run + webhook Telegram)
- [ ] Test automatici per strumenti e guardrail

Le prossime cose da fare sono nelle [issue](../../issues), a partire da quelle con l'etichetta `good first issue`.

## Licenza

[MIT](LICENSE) © 2026 GDG Brescia
