# Guida al deploy di Pota Bot (webinar)

Runbook per portare Pota Bot su Google Cloud dal vivo, con `./deploy/deploy.sh`. Architettura e decisioni: [`design.md`](design.md).

> **Stato:** la prova generale su Google Cloud non è ancora stata fatta. Dove c'è una durata trovi "⏱ da misurare nella prova generale"; vanno compilate dopo il Task 13 del piano.

## Prerequisiti

- [ ] **Progetto Google Cloud** dedicato a GDG Brescia (non un progetto di lavoro), con **fatturazione attiva**.
- [ ] Il tuo account ha il ruolo **Owner** (o Editor) sul progetto.
- [ ] **Configurazione gcloud separata**, per non toccare quella di lavoro:
  ```bash
  gcloud config configurations create gdg-brescia
  gcloud auth login                       # con l'account personale/GDG
  gcloud config set project <PROJECT_ID>
  ```
  Per tornare alla configurazione di lavoro: `gcloud config configurations activate default`.
- [ ] **Docker non serve**: la build la fa Cloud Build, sul cloud.
- [ ] **Bot di test** creato con [@BotFather](https://t.me/BotFather) (`/newbot`): servono token e username.
- [ ] **Gruppo di test** su Telegram, con il bot aggiunto.
- [ ] **Privacy mode di Telegram** (attiva di default): nei gruppi il bot vede solo `/chiedi ...` (e gli altri comandi) e le risposte ai suoi messaggi, non le menzioni semplici `@username`. Per rispondere anche alle menzioni: @BotFather → `/setprivacy` → Disable, poi togli e riaggiungi il bot al gruppo (da quel momento riceve tutti i messaggi del gruppo, ma ignora, e non manda mai a Gemini, quelli che non lo riguardano). Per il gruppo della community consigliamo di lasciarla attiva.
- [ ] **Chiave API Gemini** da [AI Studio](https://aistudio.google.com/apikey) (per il test va bene quella gratuita).
- [ ] `deploy/config.env` creato: `cp deploy/config.env.example deploy/config.env` e compilato (`PROJECT_ID`, `TELEGRAM_BOT_USERNAME` senza `@`, `TELEGRAM_DIGEST_CHAT_ID`).

### Come trovare l'id del gruppo di test

1. Copia `.env.example` (nella radice del repo) in `pota_bot/.env` e inserisci chiave Gemini, token e username del bot.
2. Avvia il bot in locale: `.venv/bin/python scripts/run_polling.py`
3. Nel gruppo di test scrivi `/start@username_del_bot` (con la privacy mode un messaggio normale non arriva al bot).
4. Nel log compare una riga tipo `📨 chat -1001234567890 (supergroup): ...`. Quel **numero negativo** è `TELEGRAM_DIGEST_CHAT_ID`.
5. Ferma lo script con Ctrl+C.

## 1. Prima del webinar (il giorno prima)

1. Login nella configurazione `gdg-brescia` (vedi Prerequisiti) e `gcloud config list` per controllare progetto e account.
2. Imposta un **avviso di budget a 5 €**: Console → Fatturazione → Budget e avvisi.
3. Parti da zero: `./deploy/teardown.sh`. Rimuove webhook, job dello Scheduler e servizio Cloud Run. **Non** tocca segreti e Firestore.
4. Apri Telegram con il bot e il gruppo di test.
5. Terminale con **font grande**; attenzione a non mostrare token o chiavi (lo script li chiede senza mostrarli a schermo).
6. Console Cloud aperta in schede già pronte: **Cloud Run**, **Firestore**, **Cloud Scheduler**, **Secret Manager**.
7. Per saltare le domande sui segreti dal vivo puoi preimpostarli: `TELEGRAM_BOT_TOKEN=... GEMINI_API_KEY=... ./deploy/deploy.sh`. Se i segreti esistono già in Secret Manager, lo script non li chiede.

## 2. Scaletta del deploy dal vivo

Lancia `./deploy/deploy.sh`. Ogni passo stampa `▶ N/7 ...`. Per ognuno: cosa fa, cosa dire, cosa mostrare.

### Passo 1/7: abilito le API
- **Cosa fa:** attiva i servizi Google Cloud che servono (Cloud Run, Cloud Build, Firestore, Secret Manager, Scheduler...).
- **Cosa dire:** "Su Google Cloud ogni servizio è spento finché non lo accendi. Lo script accende solo quelli che ci servono."
- **Console:** API e servizi → Servizi abilitati.
- **Durata:** ⏱ da misurare nella prova generale

### Passo 2/7: Firestore
- **Cosa fa:** crea il database (se non esiste) in `eur3`, multi-regione europea.
- **Cosa dire:** "Qui salviamo le proposte di temi. Senza nome né id di chi le propone."
- **Console:** Firestore → database `(default)`; più avanti la raccolta `proposals`.
- **Durata:** ⏱ da misurare nella prova generale

### Passo 3/7: segreti in Secret Manager
- **Cosa fa:** salva token Telegram e chiave Gemini (li chiede se mancano) e genera due segreti casuali: quello del webhook e il token dei task.
- **Cosa dire:** "I segreti non stanno mai nel codice né nei commit: stanno in Secret Manager e il servizio li legge a runtime. Il segreto del webhook impedisce a chiunque di far parlare il bot; il token dei task impedisce a chiunque di lanciare il digest."
- **Console:** Secret Manager → i 4 segreti `pota-*` (mostra l'elenco, **non** i valori).
- **Durata:** ⏱ da misurare nella prova generale

### Passo 4/7: service account con permessi minimi
- **Cosa fa:** crea l'identità `pota-bot@...` con solo due ruoli: `roles/datastore.user` (scrivere su Firestore) e `roles/secretmanager.secretAccessor` (leggere i segreti). Assegna anche `roles/run.builder` all'account di default di Compute Engine, necessario alla build.
- **Cosa dire:** "Il bot gira con un'identità dedicata che può fare solo due cose. Se qualcuno la compromette, non può toccare il resto del progetto."
- **Console:** IAM e amministrazione → Account di servizio, poi IAM per vedere i ruoli.
- **Nota:** i permessi appena creati possono metterci qualche secondo a propagarsi; lo script riprova da solo fino a 3 volte.
- **Durata:** ⏱ da misurare nella prova generale

### Passo 5/7: build e deploy su Cloud Run
- **Cosa fa:** Cloud Build costruisce il container dal `Dockerfile` e Cloud Run lo pubblica (0-1 istanze, 1 GiB, nessun costo quando nessuno scrive). Poi controlla `/health` (non `/healthz`: Cloud Run riserva i percorsi che finiscono in `z`).
- **Cosa dire:** "Non ho Docker sul portatile: carico il codice e la build la fa Google. Scala a zero: se nessuno scrive, non paghiamo."
- **Console:** Cloud Run → servizio `pota-bot` → Revisioni e Log; Cloud Build → Cronologia.
- **Durata:** circa 2-4 minuti secondo lo script, ⏱ da misurare nella prova generale. Tempo morto: riempilo con il passo 3 e 4 già spiegati, o con le domande del pubblico.

### Passo 6/7: collego Telegram al servizio (webhook)
- **Cosa fa:** dice a Telegram l'indirizzo del servizio e il segreto da mandare in ogni richiesta.
- **Cosa dire:** "Telegram ci chiama a ogni messaggio (webhook), invece di essere noi a chiedergli ogni secondo se c'è qualcosa di nuovo (polling). Il segreto nell'header serve a distinguere Telegram da un impostore."
- **Console:** nessuna; mostra solo l'output `Webhook impostato`.
- **Durata:** ⏱ da misurare nella prova generale

### Passo 7/7: digest settimanale con Cloud Scheduler
- **Cosa fa:** crea il job `pota-bot-digest` che ogni lunedì alle 9:00 (Europe/Rome) chiama `/tasks/digest` con il token dei task.
- **Cosa dire:** "È il cron del cloud. Il servizio dorme; lo Scheduler lo sveglia una volta a settimana, con un token che solo lui conosce."
- **Console:** Cloud Scheduler → job `pota-bot-digest`.
- **Durata:** ⏱ da misurare nella prova generale

A fine script compare `✅ Pota Bot è online: <URL>`.

## 3. Demo dopo il deploy

Prima di tutto: `source deploy/config.env` nel terminale, così `$PROJECT_ID`, `$REGION` e `$SCHEDULER_REGION` sono definiti per i comandi `gcloud` di questa guida.

Nel gruppo di test scrivi `/chiedi <domanda>`. Il secondo modo è rispondere a un messaggio del bot, senza comando. Le menzioni `@username` funzionano solo con la privacy mode disattivata. In quest'ordine:

1. **Evento:** `/chiedi Quando è il prossimo evento?`
2. **FAQ:** `/chiedi` con una domanda sulla community (es. "Chi può partecipare?").
3. **News:** `/chiedi Novità su AI e Google questa settimana?`
4. **Proposta valida:** `/chiedi Vorrei proporre un tema: ...`, oppure rispondi al messaggio del bot → Console → Firestore → `proposals` mostra il documento.
5. **Proposta con dato personale** (una email, sempre con `/chiedi` o in risposta al bot): il guardrail la blocca.
6. **Fuori tema** (`/chiedi` con una ricetta, politica...): il bot rifiuta.
7. **Digest a mano:**
   ```bash
   gcloud --project=$PROJECT_ID scheduler jobs run pota-bot-digest --location $SCHEDULER_REGION
   ```
   Il digest arriva nel gruppo.
8. **Log** (facoltativo): 
   ```bash
   gcloud --project=$PROJECT_ID run services logs read pota-bot --region $REGION --limit 50
   ```

## 4. Piano B e problemi noti

I comandi `gcloud` di questa sezione usano le variabili di `deploy/config.env`: se hai aperto un terminale nuovo, rilancia `source deploy/config.env`.

### Il build è lento
Mostra un servizio già deployato in un secondo progetto, o una registrazione. Intanto spiega i passi 6 e 7.

### Il passo 5 rifiuta `--no-invoker-iam-check`
Alcune versioni di gcloud non conoscono il flag. In `deploy/deploy.sh`, passo 5, sostituiscilo con `--allow-unauthenticated` e rilancia. Se l'organizzazione vieta `allUsers`, il flag alternativo non funziona e serve chiedere a chi amministra l'organizzazione.

### La build fallisce con errori di permessi
Assegna il ruolo all'account di default di Compute Engine e rilancia lo script:
```bash
gcloud --project=$PROJECT_ID projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/run.builder" --condition=None
```
Il numero di progetto: `gcloud projects describe $PROJECT_ID --format='value(projectNumber)'`.

### IAM: "does not exist" subito dopo aver creato il service account
È la propagazione: l'account esiste ma non è ancora visibile ovunque. Lo script riprova da solo; se esce comunque con errore, **rilancialo**. Il deploy è ripetibile.

### Gemini risponde 429 (quota esaurita)
Il free tier ha limiti bassi di richieste al minuto e al giorno, condivisi tra tutti gli utenti della chiave. In una demo con il pubblico che scrive in contemporanea si superano facilmente. Spiegalo al pubblico: i limiti dipendono dal *tier*, e con una chiave a pagamento (tier a consumo) le quote salgono. Nell'immediato: aspetta un minuto, oppure fai fare le domande una alla volta.

### Telegram non risponde
Controlla lo stato del webhook:
```bash
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo
```
> **Non farlo con il token visibile sullo schermo condiviso.** Fallo fuori inquadratura o oscura il token. Se il token compare per sbaglio, rigeneralo con @BotFather (`/revoke`).

Guarda `url` (deve essere quello del servizio), `last_error_message` e `pending_update_count`. Poi guarda i log di Cloud Run (comando nella sezione 3).

### Ruotare un segreto
Esempio per la chiave Gemini:
```bash
printf '%s' "NUOVO" | gcloud --project=$PROJECT_ID secrets versions add pota-gemini-key --data-file=-
./deploy/deploy.sh
```
Il servizio legge `latest` quando parte, quindi serve un nuovo deploy (o una nuova revisione) per usare la versione nuova. Stesso schema per `pota-telegram-token`; se cambi il token, il passo 6 rifà anche il webhook.

## 5. Passare al gruppo vero

(Anche qui: `source deploy/config.env` per avere `$PROJECT_ID`.)

> **Chiave Gemini a pagamento: obbligatoria.** I [termini dell'API Gemini](https://ai.google.dev/gemini-api/terms) ammettono solo servizi a pagamento quando l'applicazione è disponibile a utenti nello Spazio economico europeo. Inoltre, con il free tier Google può usare i messaggi per migliorare i suoi prodotti. Il gruppo vero non può usare una chiave gratuita.

1. **Chiave a pagamento:** crea una chiave da un progetto con fatturazione attiva (AI Studio → chiave → collega al progetto fatturabile) e verifica che sia sul tier a pagamento.
2. **Aggiornala nel segreto:**
   ```bash
   printf '%s' "NUOVA_CHIAVE" | gcloud --project=$PROJECT_ID secrets versions add pota-gemini-key --data-file=-
   ```
3. **Budget alert** (es. 5 €) sul progetto: Console → Fatturazione → Budget e avvisi. Controlla che sia attivo.
4. **Nuovo `TELEGRAM_DIGEST_CHAT_ID`** in `deploy/config.env` (stessa procedura della sezione Prerequisiti, con il gruppo vero e `/start@username_del_bot`). Attenzione: `run_polling.py` **rimuove il webhook**, quindi la produzione resta offline finché non rilanci `./deploy/deploy.sh`, e usa la chiave locale di `pota_bot/.env`. Usalo solo per leggere l'id, poi rilancia subito `./deploy/deploy.sh` (passo 6).
5. **Bot nel gruppo vero:** aggiungilo; se usi un bot diverso da quello di test, aggiorna anche `TELEGRAM_BOT_USERNAME` e il segreto `pota-telegram-token`.
6. **Rilancia il deploy:** `./deploy/deploy.sh`. Aggiorna servizio, webhook e job.
7. **Verifica:** una domanda nel gruppo, `scheduler jobs run` per il digest, controllo dei log.

## Dopo il webinar: smontare tutto

`./deploy/teardown.sh` rimuove webhook, job e servizio. Le immagini del container restano in Artifact Registry (repository `cloud-run-source-deploy`) e costano pochi centesimi: se vuoi, eliminale dalla console (Artifact Registry).
