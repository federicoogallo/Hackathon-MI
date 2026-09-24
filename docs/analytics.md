# Metriche del progetto

## Visitatori e pagine viste, senza costi

Il sito integra Vercel Web Analytics, ma la raccolta resta disattivata finché non viene configurata. Per attivarla:

1. Apri il progetto su Vercel e controlla che il team sia sul piano **Hobby**. Non attivare Pro, prove Pro o Analytics Plus.
2. Nel progetto, apri **Analytics → Enable**.
3. In **Settings → Environment Variables**, aggiungi `NEXT_PUBLIC_ANALYTICS_ENABLED=true` per **Production**.
4. Esegui un nuovo deployment di produzione: la variabile viene letta durante la build.
5. Visita il dominio pubblico senza blocchi per le statistiche; dopo l’elaborazione verifica che il pannello mostri la visita. Le visite locali e le preview non sono raccolte.

Hobby include 50.000 eventi al mese, condivisi fra i progetti del team, e un mese di storico. Al raggiungimento dei limiti la raccolta viene sospesa, senza acquistare eventi aggiuntivi. Prezzi e limiti possono cambiare: controlla la [documentazione ufficiale](https://vercel.com/docs/analytics/limits-and-pricing) prima di attivare il servizio.

Il progetto raccoglie solo visualizzazioni delle pagine pubbliche `/`, `/review` e `/privacy`; non invia eventi personalizzati. Parametri di ricerca e frammenti vengono rimossi dall’URL, le pagine di conferma email sono escluse, e vengono rispettati i segnali Do Not Track e Global Privacy Control. Vercel fornisce statistiche aggregate senza cookie analitici: leggi le [modalità di trattamento](https://vercel.com/docs/analytics/privacy-policy) e l’informativa pubblicata su `/privacy`.

Per disattivare, imposta la variabile a `false` e ridistribuisci il sito; puoi anche disabilitare Analytics nel pannello Vercel. Se passi a un team Pro, disattiva prima la raccolta per evitare il modello a consumo.

## Come leggere i risultati

Confronta periodi della stessa durata, ad esempio gli ultimi sette giorni con i sette precedenti:

| Misura | Cosa indica | Limite |
| --- | --- | --- |
| Visitatori stimati | Quanti visitatori sono stati riconosciuti nel periodo | Non sono persone identificate: dispositivi, sessioni e blocchi possono cambiare il conteggio |
| Pagine viste | Quante pagine sono state aperte | Include visite ripetute; non misura iscrizioni a un hackathon |
| Pagine e provenienza | Quali pagine vengono consultate e da quali siti arriva traffico rilevabile | Una parte della provenienza può risultare sconosciuta |
| Iscritti newsletter | Contatti confermati e non disiscritti nella lista Brevo | Disponibile solo dopo l’attivazione; non coincide con i visitatori |

Non sono implementati tracciamenti dei salvataggi, dei click agli organizzatori o dei termini cercati. Non dedurre conversioni o tassi di partecipazione da semplici pagine viste. Mantieni eventuali esportazioni in `.local/metrics/` e non pubblicare dati individuali.

## Misure locali del catalogo

```bash
python scripts/project_metrics.py
```

Lo script legge l’archivio disponibile, la coda di revisione e l’ultimo report locale, senza avviare una scansione o inviare messaggi. Genera `.local/metrics/latest.json` e `.local/metrics/latest.md`, esclusi da Git e dal deployment.

Le date non interpretabili restano separate da quelle mancanti e non vengono conteggiate arbitrariamente come future. Il report della scansione conserva la propria data: un vecchio risultato non dimostra la salute attuale delle fonti. I conteggi del catalogo non misurano l’accuratezza della classificazione. Il traffico rimane non disponibile nel report locale: la fonte per le visite è il pannello Vercel.
