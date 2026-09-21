# Hackathon Milano — frontend

Direzione: un radar cittadino per chi vuole partecipare a un hackathon. La ricerca è l'azione principale; la spiegazione del monitor arriva dopo gli eventi.

## Sistema visivo

- Avorio `#f5f4ee`, verde scuro `#17241e`, testo `#20231f`.
- Arancio `#f36a3d` per accenti e superfici; arancio scuro `#a53b1d` per testo su avorio.
- Space Grotesk per titoli, Inter per testo e controlli, Instrument Serif per accenti editoriali, JetBrains Mono per etichette e dati.
- Contenitore massimo 1248 px, spaziatura responsive, bordi sottili e raggi contenuti.
- Scena a livelli con profondità al puntatore e allo scroll, radar collegato ai tre prossimi eventi reali, ingresso tipografico e transizioni brevi dei risultati. Nessun canvas o WebGL nel flusso principale.
- Movimento disattivabile dalla hero, ridotto automaticamente su touch e reattivo ai cambi di `prefers-reduced-motion` anche a pagina aperta. I contenuti restano visibili nel rendering server.
- Ricerca, filtri e azioni da tastiera; focus visibile e controlli da almeno 44 px.

## Direzione scenica

- `HeroExperience`: immagine architettonica su livelli, orbite SVG, tre selettori di data e scheda con fonte reale. Il radar è una composizione illustrativa: i punti non indicano indirizzi geografici.
- `EventsDeck`: copertine SVG originali con variazioni deterministiche, date in primo piano, fonte esplicita, passaggio animato fra griglia ed elenco e feedback dei salvati. La grafica non attribuisce categorie non presenti nei dati.
- `DiscoveryStory`: composizione asimmetrica con connessioni, biglietto e promemoria, per spiegare il percorso dalla scoperta alla partecipazione.

Riferimenti: [Stripe — progettazione del globo](https://stripe.com/blog/globe) per profondità e interazione, [Linear — redesign dell'interfaccia](https://linear.app/now/how-we-redesigned-the-linear-ui) per gerarchia e disciplina visiva, [Luma Discover](https://luma.com/discover) per centralità degli eventi. Composizione, palette e illustrazioni sono adattate al progetto.

## Tema e movimento

- Tema `Sistema` predefinito, con scelte `Chiaro` e `Scuro` nella navigazione desktop e mobile. La scelta è salvata in `hackathon-mi:theme` e sincronizzata fra schede. Un bootstrap nel documento applica la preferenza prima del rendering; in modalità Sistema risponde anche ai cambi del sistema operativo.
- Il tema scuro usa sfondi verde carbone, testo avorio e arancio caldo. La scena architettonica e il biglietto del radar mantengono la loro palette illustrativa. Contrasti del tema scuro: testo principale 15,68:1, secondario 7,76:1, accento 7,53:1.
- Il radar avanza ogni 7 secondi con indicatore di avanzamento e controllo pausa/ripresa. Tocco, selezione manuale e focus da tastiera interrompono l'automatismo fino a una ripresa esplicita. Hover, scheda nascosta e scena fuori schermo sospendono il timer; il movimento ridotto disattiva l'avanzamento automatico.
- L'accento `qui.` ha un ingresso breve per lettera e una sottolineatura disegnata una sola volta. Il testo non cambia durante la lettura e rimane accessibile come parola intera. Anche questo ingresso rispetta la preferenza di movimento ridotto.

## Funzioni

Ricerca nella descrizione completa, filtri di periodo e fonte, ordinamento, griglia/elenco, preferiti locali e download calendario del giorno di inizio. I parametri della ricerca sono condivisibili tramite URL. Le fonti rimangono consultabili e le informazioni non disponibili non vengono inventate.

La raccolta dei dati continua a essere quella della pipeline Python. Il frontend Next.js è il sito principale; il mirror in `docs/` è generato separatamente.

## Identità nei browser e nelle anteprime

La Madonnina è un segno vettoriale semplificato, oro su verde scuro, definito in `public/brand/madonnina.svg`. Le varianti raster e ICO servono favicon, ricerca e icone dei dispositivi; la composizione sociale in `app/opengraph-image.png` mantiene palette e tipografia del sito. Questi elementi devono restare leggibili anche a dimensioni ridotte.

Nome del sito, descrizione e dati strutturati sono definiti in `lib/seo.ts`; il dominio canonico proviene da `NEXT_PUBLIC_SITE_URL`. Titoli e favicon nei risultati di ricerca possono aggiornarsi dopo una successiva scansione del motore.

## Immagine originale

Asset: `public/milano-hero.webp` (1254 × 1254, circa 168 KiB), generato con lo strumento integrato ImageGen e ottimizzato in WebP. È un'illustrazione architettonica, non una mappa geografica o una fotografia documentaria.

Prompt finale:

> Use case: stylized-concept. Asset type: original hero artwork for a premium Italian hackathon discovery website, final image will occupy the RIGHT HALF of a deep forest-charcoal (#17241e) hero panel, while separate HTML headline and search form occupy the left. Create a sophisticated cinematic architectural art direction: a highly detailed ivory stone scale-model of Milan's Duomo cathedral viewed from a slightly elevated front three-quarter angle, a few tiny surrounding city blocks and modern Milan towers farther back, arranged on a circular low plinth which hovers above a dark forest-charcoal surface. Around the base a single bold vivid burnt orange (#f36a3d) sculptural orbital ribbon curves in a large clean arc, like a geographic discovery radar, passing behind the Duomo and curling across the foreground. Beautifully lit limestone detail and finely modeled gothic spires; tactile matte ceramic architecture contrasting the saturated orange satin ribbon. Sparse faint technical grid on the ground, no neon, no laser beams. Strong architectural photography lighting with soft warm key light from upper left and subtle shadows. Premium contemporary Italian design magazine meets architectural scale model, realistic materials, elegant surreal art direction. Image is square, cathedral center-right with breathing room, entire silhouette visible. Background flat deep forest charcoal #17241e, edges blend smoothly into that same flat dark color, especially generous negative space on LEFT side. Scene occupies 80% of frame height. High-quality photoreal CGI. No text, no letters, no typography, no logos, no watermark, no UI, no people, no stars, no space, no busy skyline, no cartoon, no blue or purple.

Linee guida ricavate dalla skill UI/UX Pro Max: directory con ricerca primaria, separazione delle gerarchie, rendering server per i contenuti statici, accessibilità e movimento ridotto. Palette e tipografia adattate al contesto editoriale milanese.

## Validazione e controlli visivi

- `npm run build`: verifica la compilazione di produzione e mostra le dimensioni aggiornate delle route.
- `npm run typecheck`: controlla i tipi TypeScript, dopo la generazione dei tipi delle route durante la build.
- `npm run test:frontend`: esegue i controlli di regressione, inclusi date/Roma/DST, filtri, ricerca completa, URL, preferiti, formato ICS e bootstrap del tema (preferenza di sistema, override, valori non validi e storage indisponibile).
- Verifica nel browser della build di produzione: ricerca dall'hero, URL condivisibili e reset dalla home, preferiti e rimozione, filtri periodo, indietro, ordinamento, griglia/elenco, export calendario, review e 404.
- Layout controllato a 320, 375, 768, 1024 e 1440 px; nessun overflow orizzontale. Menu mobile verificato anche a 568 × 320, con scorrimento interno e chiusura Escape che ripristina il focus.
- Contrasto: testo secondario su avorio 4,93:1; accento testuale 5,88:1; testo hero 9,30:1. Movimento ridotto gestito da media query CSS e hook reattivo per Motion.
- Secondo passaggio: radar, titoli lunghi, pausa della scena, ricerca, feedback preferiti, elenco e nuova composizione illustrata verificati nel browser sui breakpoint indicati.
- Tema: scelta manuale, persistenza dopo reload e ritorno a Sistema verificati nel browser; controllo visivo di home, ricerca, FAQ, footer e revisione in scuro. Radar verificato in avanzamento automatico, ripresa esplicita e arresto dopo l'interazione.
- Controllare la console della build di produzione dopo le modifiche alle interazioni.

Per la newsletter, configurazione privata, consenso e invio settimanale sono documentati in [docs/newsletter.md](../docs/newsletter.md). Il prompt deve rimanere utilizzabile da tastiera e non deve mostrare conferme di iscrizione quando i servizi non sono configurati.

Per aprire localmente: `npm run dev`. Per verificare la versione compilata: `npm run build` e `npm run start`.
