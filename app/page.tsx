import HeroExperience from "@/components/HeroExperience";
import DiscoveryStory from "@/components/DiscoveryStory";
import { getSiteData, REPO_URL, SITE_URL } from "@/lib/data";
import { homeStructuredData, serializeStructuredData } from "@/lib/seo";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import EventsDeck from "@/components/EventsDeck";
import Newsletter from "@/components/Newsletter";
import { newsletterConfigured } from "@/lib/newsletter-config";

export const dynamic = "force-static";

const Arrow = ({ diagonal = false }: { diagonal?: boolean }) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{diagonal ? <path d="M6 18 18 6M6 6h12v12" /> : <path d="M4 12h16m-6-6 6 6-6 6" />}</svg>;
const Search = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 4.5 4.5" /></svg>;

const FAQS = [
  ["Come vengono selezionati gli hackathon?", "Il monitor raccoglie eventi da fonti pubbliche, elimina i duplicati e usa l’intelligenza artificiale per selezionare quelli pertinenti a Milano. I casi incerti entrano in una coda di revisione. In ogni scheda trovi la fonte e il tipo di verifica."],
  ["Posso partecipare anche se non so programmare?", "Dipende dall’evento: molti hackathon coinvolgono anche designer, persone con competenze di business e appassionati di innovazione. Apri la pagina dell’organizzatore per controllare i requisiti, la composizione dei team e le modalità di partecipazione."],
  ["Come mi iscrivo a un evento?", "Il pulsante “Scopri evento” ti porta alla fonte originale. L’iscrizione avviene con l’organizzatore: verifica sempre scadenze, disponibilità, costi e luogo. Le informazioni raccolte automaticamente possono cambiare o contenere imprecisioni."],
  ["Dove vengono salvati i miei preferiti?", "I preferiti restano nel browser di questo dispositivo, senza creare un account. Li ritrovi dalla voce “Salvati”. Non vengono sincronizzati tra dispositivi e possono essere rimossi cancellando i dati del browser. Gli eventi conclusi non compaiono nel calendario dei prossimi eventi."],
];

export default function Home() {
  const d = getSiteData();
  const structuredData = homeStructuredData(SITE_URL, d.events);
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeStructuredData(structuredData) }} />
      <Nav />
      <main id="top" tabIndex={-1}>
        <section className="hero-section" aria-labelledby="hero-title">
          <HeroExperience events={d.events}>
            <div className="hero-content">
              <div className="hero-eyebrow"><span className="status-dot" /> IL RADAR DEGLI HACKATHON A MILANO</div>
              <h1 id="hero-title">Le grandi idee<br />iniziano <em className="hero-dynamic-word"><span className="sr-only">qui.</span><span className="hero-word-glyphs" aria-hidden="true"><span>q</span><span>u</span><span>i</span><span>.</span></span><svg className="hero-word-flourish" viewBox="0 0 180 15" fill="none" aria-hidden="true"><path pathLength="1" d="M4 10C45 2 100 2 172 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg></em></h1>
              <p className="hero-description">Trova la tua prossima sfida. Incontra il tuo team.<br className="desktop-break" /> Costruisci qualcosa che prima non c’era.</p>
              <form className="hero-search" action="/#events" method="get" role="search">
                <label htmlFor="hero-query">Cosa vuoi costruire?</label>
                <div className="hero-search-field"><Search /><input id="hero-query" name="q" type="search" placeholder="Cerca per tema, nome o luogo" autoComplete="off" /><button type="submit" aria-label="Cerca hackathon"><Arrow /></button></div>
              </form>
              <div className="hero-suggestions"><span>Esplora:</span><a href="/?q=AI#events">Intelligenza artificiale <span aria-hidden="true">↗</span></a><a href="/?q=game+jam#events">Game jam <span aria-hidden="true">↗</span></a><a href="/?q=dati#events">Dati <span aria-hidden="true">↗</span></a></div>
            </div>
          </HeroExperience>
        </section>
        <div className="discovery-strip container">
          <span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" /></svg>Fonti consultabili, sempre</span>
          <span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5M12 7v5l3 2" /></svg>Scouting automatico ogni giorno</span>
          <span className="scan-timestamp" data-nosnippet>{d.lastScan ? <>Ultima raccolta <time dateTime={d.lastScanIso}>{d.lastScan}</time></> : "Prima raccolta in attesa"}</span>
        </div>
        <section className="events-section container" id="events" aria-label="Ricerca degli hackathon">
          <EventsDeck events={d.events} />
          {!d.statusOk && <p className="data-notice" role="status">L’ultima raccolta richiede un controllo. Mostriamo gli eventi già disponibili; consulta le fonti per gli aggiornamenti.</p>}
          <p className="source-disclaimer">Una buona idea merita informazioni chiare. Controlla date, requisiti e disponibilità sul sito dell’organizzatore.</p>
        </section>
        <DiscoveryStory />
        <Newsletter available={newsletterConfigured()} promptMode={process.env.NEXT_PUBLIC_NEWSLETTER_PROMPT_MODE || "first-visit"} />
        <section className="faq-section container" aria-labelledby="faq-title"><div className="faq-intro"><span className="section-label">PRIMA DI INIZIARE</span><h2 id="faq-title">Qualche domanda?<br /><em>Ci sta.</em></h2><p>Le cose utili da sapere prima<br />del tuo prossimo hackathon.</p></div><div className="faq-list">{FAQS.map(([question, answer]) => <details key={question}><summary>{question}<span className="faq-plus" aria-hidden="true" /></summary><p>{answer}</p></details>)}</div></section>
        <section className="contribute-section container"><div className="contribute-card"><div className="contribute-icon" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="4"><path d="M24 2v44M2 24h44M8.5 8.5l31 31m-31 0 31-31" /></svg></div><div><span className="section-label">LE IDEE BELLE SI CONDIVIDONO</span><h2>Un hackathon fuori dal radar?</h2><p>Aiutaci a far incontrare le persone e le opportunità giuste.</p></div><a className="btn btn-dark" href={`${REPO_URL}/issues/new?title=Segnalazione%20hackathon&body=Nome%20evento%3A%0AData%3A%0ALuogo%3A%0ALink%20ufficiale%3A`} target="_blank" rel="noopener noreferrer">Segnala un evento<Arrow diagonal /></a></div></section>
      </main>
      <Footer />
    </>
  );
}
