# Contribuire a Pota Bot

Grazie! Pota Bot è il primo progetto open source della community GDG Brescia, e ogni contributo conta: anche una FAQ in più.

## Come si fa

1. Scegli una issue (quelle con `good first issue` sono pensate per iniziare) e scrivi un commento per dire che ci lavori.
2. Fai il **fork** del repo e crea un branch: `git checkout -b faq-parcheggio`.
3. Fai la modifica e provala in locale (vedi il [README](README.md#provalo-in-locale)).
4. Apri una **pull request** verso `main`, spiegando cosa cambia e perché.
5. Un organizer la rivede. Se servono modifiche, ne parliamo nella PR.

## Regole semplici

- **Codice in inglese** (nomi di funzioni e variabili), **testi e docstring in italiano**: sono le docstring che il modello legge.
- Una PR = una cosa. Meglio tre PR piccole che una grande.
- **Mai chiavi API o token nel codice.** Usa il file `.env` (è escluso da git).
- Se modifichi uno strumento, controlla che la docstring spieghi ancora bene *quando* usarlo.

## Comportamento

Seguiamo le [linee guida delle community Google](https://developers.google.com/community-guidelines): rispetto, inclusione, niente molestie. Per segnalazioni scrivi agli organizer di GDG Brescia.
