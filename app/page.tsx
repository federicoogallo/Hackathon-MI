import Link from "next/link";
import { getSiteData, REPO_URL } from "@/lib/data";
import Nav from "@/components/Nav";
import Fx from "@/components/Fx";
// Intro orbitale (globo -> Duomo) disattivata: il sito apre direttamente
// sull'hero. Codice e componente conservati per riattivarla in futuro —
// basta ripristinare l'import e <GlobeIntro /> qui sotto.
// import GlobeIntro from "@/components/GlobeIntro";
import HeroCanvas from "@/components/HeroCanvas";
import Materialize from "@/components/Materialize";
import EventsDeck from "@/components/EventsDeck";

export const dynamic = "force-static";

const SvgArrow = (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8h10M9 4l4 4-4 4" /></svg>
);

const MARQUEE = ["PUBLIC SOURCES", "DEDUPLICATION", "AI CONFIDENCE", "MANUAL REVIEW", "GITHUB PAGES OUTPUT"];

const STEPS: Array<[string, string, string]> = [
  ["01", "Collect", "Community, piattaforme eventi e ricerca web entrano nel radar."],
  ["02", "Dedupe", "I record sovrapposti diventano un solo candidato leggibile."],
  ["03", "AI score", "Luogo, data, formato e fonte generano un livello di fiducia."],
  ["04", "Review", "I casi incerti passano a controllo umano, fuori dalla pagina pubblica."],
  ["05", "Publish", "Gli eventi verificati diventano l'output stabile del sito."],
];

export default function Home() {
  const d = getSiteData();
  const evtWord = d.events.length === 1 ? "evento" : "eventi";
  const monWord = d.monthsCovered === 1 ? "mese" : "mesi";

  return (
    <>
      <Fx />
      <Nav>
        <Link className="btn btn-ghost nav-secondary" href="/review">Candidati in review</Link>
        <a className="btn btn-primary" href="#events">{SvgArrow}Eventi</a>
      </Nav>

      {/* <GlobeIntro /> */}

      <header className="hero" id="top">
        <HeroCanvas />
        <div className="container">
          <div className="hero-grid">
            <div className="hero-copy">
              <div className="eyebrow"><span className="dot" />Live AI scouting system</div>
              <h1 className="hero-title" id="hero-title" aria-label="Hackathon Milano">
                <span className="line"><Materialize text="Hackathon" /></span>
                <span className="line title-accent">Milano</span>
              </h1>
              <p className="hero-sub">
                Un prodotto editoriale e operativo per leggere il territorio: raccoglie segnali
                pubblici, comprime i duplicati, assegna un livello di fiducia e pubblica solo
                opportunita verificabili.
              </p>
              <div className="hero-cta">
                <a className="btn btn-primary" href="#events">Apri il deck eventi</a>
                <a className="btn btn-ghost" href={REPO_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
              </div>
              <div className="hero-status">
                <span className={d.statusOk ? "ops-dot" : "ops-dot warn"} />
                <strong>{d.statusLabel}</strong>
                <span>Ultimo scan: {d.lastScan}</span>
              </div>
              <div className="hero-metrics" aria-label="Metriche monitor">
                <div className="metric"><strong data-count={d.events.length}>{d.events.length}</strong><span>{evtWord} verificati</span></div>
                <div className="metric"><strong data-count={d.monthsCovered}>{d.monthsCovered}</strong><span>{monWord} coperti</span></div>
                <div className="metric"><strong data-count={24} data-suffix="h">24h</strong><span>refresh</span></div>
              </div>
            </div>
            <aside className="stage" aria-hidden="true">
              <div className="stage-orbit" />
              <div className="panel">
                <div className="panel-head">
                  <span className="win-dots"><i /><i /><i /></span>
                  <span className="tag">monitor // live</span>
                </div>
                <div className="pipe">
                  <div className="pipe-row"><span className="lead"><i />Collect</span><span className="val">fonti pubbliche</span></div>
                  <div className="pipe-row"><span className="lead"><i />Dedupe</span><span className="val">cluster simili</span></div>
                  <div className="pipe-row"><span className="lead"><i />AI score</span><span className="val">fiducia e contesto</span></div>
                  <div className="pipe-row"><span className="lead"><i />Publish</span><span className="val">output verificato</span></div>
                </div>
                <div className="panel-foot">
                  <div><span>scope</span><strong>Milano</strong></div>
                  <div><span>in review</span><strong>{d.reviewCount}</strong></div>
                  <div><span>refresh</span><strong>24h</strong></div>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </header>

      <section className="marquee" aria-hidden="true">
        <div className="marquee-track">
          {[0, 1].map((k) => MARQUEE.map((m) => (
            <span key={`${k}-${m}`}>{m}<b> / </b></span>
          )))}
        </div>
      </section>

      <section className="section system" id="system">
        <div className="container">
          <div className="sys-head">
            <div data-reveal>
              <span className="kicker">01 / Come funziona</span>
              <h2 className="h2">Dal rumore pubblico a un calendario <em>ad alta fiducia</em>.</h2>
            </div>
            <p className="lead-p" data-reveal data-delay="80">
              Il motore trasforma segnali pubblici dispersi in una mappa operativa: fonti,
              deduplica, scoring AI e review umana convergono in un output pronto da usare.
            </p>
          </div>
          <div className="rail" data-reveal>
            <div className="rail-line" aria-hidden="true"><i id="rail-fill" /></div>
            <ol className="rail-steps">
              {STEPS.map(([n, t, s]) => (
                <li key={n} className="rail-step" data-step="">
                  <code>{n}</code>
                  <h3>{t}</h3>
                  <p>{s}</p>
                </li>
              ))}
            </ol>
          </div>
          <div className="sys-foot" data-reveal>
            <span><b>28</b> fonti pubbliche</span>
            <span><b>4</b> livelli di dedup</span>
            <span><b>0.7</b> soglia di fiducia AI</span>
            <span><b>24h</b> ciclo di refresh</span>
          </div>
        </div>
      </section>

      <main className="section" id="events">
        <div className="container">
          <div className="events-head">
            <div data-reveal>
              <span className="kicker">02 / Event deck</span>
              <h2 className="h2">Output finale, pronto da <em>scansionare</em>.</h2>
              <p className="lead-p" style={{ marginTop: 16 }}>
                Gli eventi sono presentati come un deck operativo: pochi segnali forti, fonte
                visibile, qualita esplicita e azioni rapide per confermare o aprire dubbi.
              </p>
            </div>
            <div className="stats" data-reveal data-delay="80">
              <div className="stat"><strong data-count={d.events.length}>{d.events.length}</strong><span>{evtWord}</span></div>
              <div className="stat"><strong data-count={d.monthsCovered}>{d.monthsCovered}</strong><span>{monWord}</span></div>
              <div className="stat"><strong data-count={d.reviewCount}>{d.reviewCount}</strong><span>in review</span></div>
            </div>
          </div>
          <EventsDeck events={d.events} />
        </div>
      </main>

      <footer>
        <div className="container">
          <div className="footer-inner">
            <div className="footer-brand"><b>Hackathon Milano</b>Dati raccolti automaticamente con AI<br />
              <small>Icona: Madonnina da foto di Ibex73 (Wikimedia Commons, CC BY-SA 4.0)</small></div>
            <div className="footer-mid">aggiornato {d.lastScan}</div>
            <div className="footer-links">
              <a href={REPO_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
              <Link href="/review">Review</Link>
              <a href="#top">Top</a>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
