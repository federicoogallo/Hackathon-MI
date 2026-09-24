# Newsletter settimanale · Brevo Free

## Attivazione da zero

La newsletter usa **Brevo Free** e l’identità **Hackathon Milano**. I link portano a [hackathon-milano.vercel.app](https://hackathon-milano.vercel.app). Finché mancano account e credenziali, il modulo mostra “Anteprima”, rimane disabilitato e non raccoglie indirizzi.

Il sottodominio `hackathon-milano.vercel.app` ospita il sito: **non crea una casella email e non permette di autenticare un dominio mittente che controlli**. Non usare indirizzi inventati come `newsletter@hackathon-milano.vercel.app`. Senza acquistare un dominio, usa una casella reale che controlli, verificata in Brevo, con nome mittente “Hackathon Milano”. Brevo documenta la sostituzione temporanea del dominio delle caselle gratuite con un proprio dominio di invio; disponibilità e recapitabilità dipendono dal servizio. [Requisiti ufficiali del mittente](https://help.brevo.com/hc/en-us/articles/14925263522578-Comply-with-Gmail-Yahoo-and-Microsoft-s-requirements-for-email-senders).

1. Crea un account **Brevo Free** dedicato al progetto. Non attivare piani a pagamento, crediti aggiuntivi o ricariche automatiche. Completa le verifiche richieste da Brevo per campagne ed email transazionali.
2. Aggiungi una casella reale nella sezione mittenti e confermala dal messaggio ricevuto. Inserisci solo quell’indirizzo in `NEWSLETTER_FROM`; il nome visibile “Hackathon Milano” è già impostato dal codice. Usa un recapito controllato per `NEWSLETTER_CONTACT_EMAIL`.
3. Crea una lista **vuota e dedicata** “Hackathon Milano” e annota il suo ID numerico (`BREVO_LIST_ID`). Non importare contatti o aggiungerli manualmente: il sito inserisce solo indirizzi confermati, rispettando il limite gratuito.
4. Genera una chiave API Brevo per invii, contatti, campagne e lettura account. Conservala come `BREVO_API_KEY`; non serve un SDK o un piano Automations a pagamento.
5. Attiva **Anonymous email tracking** sia per le campagne sia per le email transazionali, seguendo la [guida Brevo](https://help.brevo.com/hc/it/articles/11643306229906-Posso-rendere-anonimo-il-tracciamento-delle-aperture-e-dei-clic-per-le-mie-email). Le impostazioni sono separate: verifica entrambe prima di abilitare il modulo. Non raccogliamo un consenso al tracciamento individuale delle aperture.
6. Crea un database **Upstash Redis Free**, senza upgrade o ricariche. Copia URL REST e token REST nella configurazione privata. Redis conserva conferme, limiti e stato degli invii: non può essere sostituito con file nel repository o memoria temporanea del server. [Guida Upstash](https://upstash.com/docs/redis/overall/getstarted).
7. Nel progetto Vercel apri **Settings → Environment Variables** e inserisci le variabili sotto per Production, inclusi nome del gestore, recapito e un `CRON_SECRET` casuale di almeno 32 caratteri. I secret Python/GitHub non configurano automaticamente Vercel. [Guida Vercel](https://vercel.com/docs/environment-variables).
8. Imposta `NEWSLETTER_ENABLED=true`, effettua un nuovo deploy e verifica l’intero percorso con un indirizzo che controlli. In locale usa `.env.local`, escluso da Git, e riavvia il server. Attivare il flag non verifica credenziali, mittente o consegna: il test reale resta necessario.

Account, recapito mittente e credenziali devono essere forniti dal gestore. Il repository non contiene un account già attivo. Non inviare chiavi API o token di conferma in chat, issue o commit.

## Configurazione

Copia i valori del modello [`.env.newsletter.example`](../.env.newsletter.example) nelle impostazioni private.

| Variabile | Utilizzo |
| --- | --- |
| `NEWSLETTER_ENABLED` | `true` solo dopo aver configurato i servizi |
| `BREVO_API_KEY` | Chiave server Brevo |
| `BREVO_LIST_ID` | ID numerico della lista dedicata agli iscritti confermati |
| `NEWSLETTER_FROM` | Email reale verificata in Brevo, senza nome o parentesi angolari |
| `NEWSLETTER_CONTACT_EMAIL` | Recapito pubblico per risposte e richieste sui dati |
| `NEWSLETTER_OWNER` | Identità pubblica del gestore |
| `UPSTASH_REDIS_REST_URL` | Endpoint HTTPS del database privato |
| `UPSTASH_REDIS_REST_TOKEN` | Credenziale server Redis |
| `CRON_SECRET` | Segreto casuale di almeno 32 caratteri, anche per identificativi HMAC |
| `NEXT_PUBLIC_SITE_URL` | `https://hackathon-milano.vercel.app`, origine dei link e delle richieste |
| `NEXT_PUBLIC_NEWSLETTER_PROMPT_MODE` | `always`, `first-visit` oppure `off` |

Le credenziali non devono mai avere prefisso `NEXT_PUBLIC_`. La newsletter accetta richieste dalla propria origine; un deploy di anteprima su un’origine diversa richiede configurazione coerente. HTTP è consentito solo in sviluppo su localhost.

## Gratuità e limiti

Brevo Free comprende attualmente **300 invii al giorno**, condivisi tra conferme e campagne, con marchio Brevo nelle email e statistiche di base. Gli invii inutilizzati non si accumulano. [Limiti ufficiali](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan).

Il sito applica limiti più prudenti:

- **250 posti** per la lista. Il conteggio include contatti bloccati e prenotazioni il cui esito è incerto; non si libera automaticamente cancellando un contatto nel pannello. Una prenotazione atomica Redis evita di superare il limite con conferme simultanee o conteggi Brevo in ritardo.
- **40 tentativi di email di conferma nelle ultime 24 ore**, anche con richieste simultanee. Le richieste fallite consumano comunque il limite, per non rischiare reinvii dopo risposte incerte.
- Cinque richieste per connessione/ora, venti/giorno e un’ora di attesa per lo stesso indirizzo. Fuori da Vercel le connessioni condividono un limite prudente.
- Prima degli invii, `/account` deve attestare il piano email **Free**, crediti residui numerici sufficienti e servizio transazionale abilitato. Piani a pagamento, crediti sconosciuti o risposte anomale sospendono l’invio. Prima di una campagna serve almeno il numero totale di contatti della lista più dieci crediti di margine.
- Al massimo una campagna avviata in 24 ore, anche se due esecuzioni manuali attraversano il cambio di settimana. Il codice non acquista crediti e non cambia piani.

Usa un account dedicato: invii manuali o automazioni esterne consumano la stessa quota. Se la lista viene modificata manualmente, le quote sono insufficienti o uno dei servizi gratuiti si sospende, l’invio si ferma; controlla lo stato prima di riprovare. Non abilitare servizi a pagamento per aggirare il blocco. I limiti e le condizioni dei piani gratuiti restano soggetti ai rispettivi fornitori.

## Iscrizione e dati privati

Il visitatore inserisce email e consenso. Riceve un link valido 24 ore e completa la conferma premendo un pulsante sul sito. Solo allora il contatto entra nella lista Brevo. Una semplice visita o il caricamento automatico del link da parte di uno scanner email non iscrive nessuno.

Il token usa `/newsletter/confirm#token=…`: il frammento non viene inviato nella prima richiesta al server; la conferma usa POST. Nel database si conserva l’hash del token, non il token originale. Il codice non registra indirizzi, token o errori completi dei fornitori nei log.

I contatti già disiscritti, bloccati o presenti in altre liste non vengono riattivati automaticamente. Un contatto già attivo nella lista non subisce aggiornamenti. I casi che richiedono reiscrizione vengono rimandati al gestore. La creazione usa `updateEnabled: false` per evitare che una richiesta concorrente sovrascriva un blocco.

| Dati | Conservazione |
| --- | --- |
| Richiesta in attesa: email, data, versione informativa | Redis, 24 ore |
| Indicatore di token già utilizzato | Redis, 24 ore |
| Limiti connessione/email e quota conferme | Redis, massimo 24 ore; IP ed email identificati con HMAC |
| Prova consenso: HMAC email, date e versione | Redis, 365 giorni |
| Prenotazione posto: HMAC email e contatore | Redis, fino alla riconciliazione/cancellazione da parte del gestore |
| Stato campagna, ID eventi già inviati | Redis, senza scadenza automatica; nessun indirizzo iscritto |
| Email confermata e stato disiscrizione | Brevo, gestiti secondo le impostazioni del servizio e le richieste al gestore |

Gli HMAC restano dati privati riconducibili agli iscritti, non dati anonimi pubblicabili. Quando cancelli i dati di un iscritto, tratta anche la prenotazione e la prova del consenso in Redis, riconciliando il contatore senza riaprire posti occupati o incerti. La scadenza Redis non cancella email già consegnate, registri o backup dei fornitori. Il database non deve comparire in Git, file pubblici, esportazioni o issue.

Il prompt resta temporaneamente su `always` per la verifica su ogni visita. `first-visit` lo mostra una volta per browser; `off` lascia l’iscrizione manuale. La preferenza non riconosce una persona su browser diversi e non sostituisce mai il consenso.

## Invio settimanale e recupero

Vercel Cron richiama `/api/newsletter/weekly` il **lunedì alle 08:00 UTC**, con `Authorization: Bearer <CRON_SECRET>`. A Milano sono le 09:00 d’inverno e le 10:00 d’estate. Il riepilogo usa l’ultima settimana completa chiusa lunedì alle 08:00 UTC; eventuali ritardi usano la stessa finestra.

Vengono selezionati hackathon accettati, scoperti o approvati nella finestra, con data futura o esplicitamente da confermare. Gli eventi passati, rifiutati o già inviati vengono esclusi. Con zero novità non parte nessuna email; con zero iscritti non viene creata una campagna. L’archivio è quello incluso nel deploy: nuovi dati in Git richiedono il relativo deploy.

Le conferme usano l’[API email transazionali](https://developers.brevo.com/reference/send-transac-email). Il digest crea una [campagna marketing](https://developers.brevo.com/reference/create-email-campaign) in bozza per la lista dedicata, poi chiama `sendNow`. Il link `{{ unsubscribe }}` usa la disiscrizione Brevo. Il corpo HTML viene passato alla campagna; Brevo gestisce la versione di testo della campagna. Le conferme includono HTML e testo espliciti.

Prima della creazione e prima dell’invio il server salva lo stato. Le esecuzioni ripetute riusano sempre lo stesso ID. `processing` significa in coda/in elaborazione/in verifica; **non equivale a consegna**. Solo lo stato Brevo `sent` conclude il lavoro e memorizza gli eventi come inviati; neppure questo garantisce che ogni email sia arrivata nella posta in entrata.

Un esito ambiguo, una campagna sospesa o un tentativo rimasto in bozza dopo l’invio restituisce `needs_review`: l’automatismo non reinvia. Anche una settimana precedente irrisolta blocca i nuovi invii. Controlla il record privato Redis e la campagna Brevo prima di intervenire. Non cancellare semplicemente lo stato per riprovare: il messaggio potrebbe essere già partito. Se mancano crediti, riprova il cron autenticato dopo il ripristino della quota e prima che cambi la finestra settimanale; il blocco non acquista crediti né invia recuperi arretrati automaticamente.

La migrazione usa il namespace Redis `hackathon-mi:newsletter:brevo:`. Eventuali vecchi contatti o job del provider precedente non vengono importati né reinviati: un’installazione già attiva richiederebbe una migrazione privata esplicita di consensi, disiscrizioni e stato.

## Verifica prima di considerarla attiva

Esegui `node scripts/test-newsletter.mjs` e `npm run typecheck`: i test sono offline e simulano Brevo/Redis, comprese quote, concorrenza, disiscrizione, timeout e ripetizioni del cron.

Dopo la configurazione privata, usa un indirizzo che controlli per verificare conferma, mittente reale, link e disiscrizione. Controlla entrambe le impostazioni di tracciamento anonimo e i log di cron/deploy, senza esportare dati degli iscritti. I test simulati e l’anteprima del modulo non verificano l’account esterno o l’arrivo in posta.
