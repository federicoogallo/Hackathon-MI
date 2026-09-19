# Hackathon Milano — frontend

Direzione: un radar cittadino per chi vuole partecipare a un hackathon. La ricerca è l'azione principale; la spiegazione del monitor arriva dopo gli eventi.

## Sistema visivo

- Avorio `#f5f4ee`, verde scuro `#17241e`, testo `#20231f`.
- Arancio `#f36a3d` per accenti e superfici; arancio scuro `#a53b1d` per testo su avorio.
- Space Grotesk per titoli, Inter per testo e controlli, Instrument Serif per accenti editoriali, JetBrains Mono per etichette e dati.
- Contenitore massimo 1248 px, spaziatura responsive, bordi sottili e raggi contenuti.
- Animazioni brevi di ingresso; nessun canvas o WebGL nel flusso principale. Rispetto di `prefers-reduced-motion`.
- Ricerca, filtri e azioni da tastiera; focus visibile e controlli da almeno 44 px.

## Funzioni

Ricerca nella descrizione completa, filtri di periodo e fonte, ordinamento, griglia/elenco, preferiti locali e download calendario del giorno di inizio. I parametri della ricerca sono condivisibili tramite URL. Le fonti rimangono consultabili e le informazioni non disponibili non vengono inventate.

La raccolta dei dati continua a essere quella della pipeline Python. Il frontend Next.js è il sito principale; il mirror in `docs/` è generato separatamente.

## Immagine originale

Asset: `public/milano-hero.webp` (1254 × 1254, circa 168 KiB), generato con lo strumento integrato ImageGen e ottimizzato in WebP. È un'illustrazione architettonica, non una mappa geografica o una fotografia documentaria.

Prompt finale:

> Use case: stylized-concept. Asset type: original hero artwork for a premium Italian hackathon discovery website, final image will occupy the RIGHT HALF of a deep forest-charcoal (#17241e) hero panel, while separate HTML headline and search form occupy the left. Create a sophisticated cinematic architectural art direction: a highly detailed ivory stone scale-model of Milan's Duomo cathedral viewed from a slightly elevated front three-quarter angle, a few tiny surrounding city blocks and modern Milan towers farther back, arranged on a circular low plinth which hovers above a dark forest-charcoal surface. Around the base a single bold vivid burnt orange (#f36a3d) sculptural orbital ribbon curves in a large clean arc, like a geographic discovery radar, passing behind the Duomo and curling across the foreground. Beautifully lit limestone detail and finely modeled gothic spires; tactile matte ceramic architecture contrasting the saturated orange satin ribbon. Sparse faint technical grid on the ground, no neon, no laser beams. Strong architectural photography lighting with soft warm key light from upper left and subtle shadows. Premium contemporary Italian design magazine meets architectural scale model, realistic materials, elegant surreal art direction. Image is square, cathedral center-right with breathing room, entire silhouette visible. Background flat deep forest charcoal #17241e, edges blend smoothly into that same flat dark color, especially generous negative space on LEFT side. Scene occupies 80% of frame height. High-quality photoreal CGI. No text, no letters, no typography, no logos, no watermark, no UI, no people, no stars, no space, no busy skyline, no cartoon, no blue or purple.

Linee guida ricavate dalla skill UI/UX Pro Max: directory con ricerca primaria, separazione delle gerarchie, rendering server per i contenuti statici, accessibilità e movimento ridotto. Palette e tipografia adattate al contesto editoriale milanese.

## Verifiche finali

- `npm run build`: build statica completata; pagina principale 11,7 kB, first load JavaScript 118 kB.
- `npm run typecheck`: nessun errore TypeScript.
- `npm run test:frontend`: 13 test superati, inclusi date/Roma/DST, filtri, ricerca completa, URL, preferiti e formato ICS.
- Verifica nel browser della build di produzione: ricerca dall'hero, URL condivisibili e reset dalla home, preferiti e rimozione, filtri periodo, indietro, ordinamento, griglia/elenco, export calendario, review e 404.
- Layout controllato a 320, 375, 768, 1024 e 1440 px; nessun overflow orizzontale. Menu mobile verificato anche a 568 × 320, con scorrimento interno e chiusura Escape che ripristina il focus.
- Contrasto: testo secondario su avorio 4,93:1; accento testuale 5,88:1; testo hero 9,30:1. Movimento ridotto gestito dalle media query CSS.
- Console della sessione di produzione pulita.

Per aprire localmente: `npm run dev`. Per verificare la versione compilata: `npm run build` e `npm run start`.
