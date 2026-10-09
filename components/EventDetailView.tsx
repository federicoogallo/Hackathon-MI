import Link from "next/link";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import EventDetailActions from "@/components/EventDetailActions";
import type { EventDetail } from "@/lib/event-details";
import { validEventDate } from "@/lib/event-filters";
import "./event-detail.css";

function Arrow({ back = false }: { back?: boolean }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{back ? <path d="M19 12H5m6-6-6 6 6 6" /> : <path d="M6 18 18 6M6 6h12v12" />}</svg>;
}

function safeLink(value: string): string | undefined {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : undefined; }
  catch { return undefined; }
}

function checkedDate(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Rome" }).format(date);
}

function DetailArtwork() {
  return <div className="event-detail-art" aria-hidden="true">
    <span className="event-detail-art-label">IDEE IN CONNESSIONE</span>
    <svg viewBox="0 0 360 340" fill="none">
      <g className="event-detail-art-grid" stroke="currentColor" strokeWidth=".65">
        <path d="M40 80h280M40 140h280M40 200h280M40 260h280M70 50v250M130 50v250M190 50v250M250 50v250M310 50v250" />
        <circle cx="180" cy="177" r="126" />
      </g>
      <g className="event-detail-art-orbits" transform="translate(180 177) rotate(-34)" stroke="currentColor">
        {Array.from({ length: 15 }, (_, index) => <ellipse key={index} rx={34 + index * 7} ry={20 + index * 4.3} strokeWidth={index === 14 ? "1.6" : ".9"} />)}
      </g>
      <path className="event-detail-art-axis" d="M41 270 319 83M60 89l237 178" stroke="currentColor" strokeWidth=".8" strokeDasharray="3 6" />
      <g className="event-detail-art-mark" fill="currentColor"><circle cx="286" cy="105" r="7" /><circle cx="76" cy="248" r="4" /></g>
      <g className="event-detail-art-center" transform="translate(180 177)" stroke="currentColor" strokeWidth="3"><path d="M-11 0h22M0-11v22" /></g>
    </svg>
    <span className="event-detail-art-caption">HACKATHON MILANO<span>SCOPRI. INCONTRA. COSTRUISCI.</span></span>
  </div>;
}

export default function EventDetailView({ event, related }: { event: EventDetail; related: EventDetail[] }) {
  const sourceUrl = safeLink(event.url);
  const reportUrl = safeLink(event.issueDoubt);
  const checked = checkedDate(event.checkedAt);
  const startDate = validEventDate(event.dateIso);
  const relatedEvents = related.filter((item) => item.id !== event.id).slice(0, 3);
  // The catalogue summary may repeat the first facts verbatim. Keep those facts
  // beside their individual sources instead of presenting the same text twice.
  const factsSummary = event.facts.slice(0, 2).map((fact) => `${fact.label}: ${fact.value}.`).join(" ");
  const showOverview = Boolean(event.description && event.description !== factsSummary);

  return <>
    <Nav><Link className="btn btn-nav" href="/#events">Tutti gli eventi <span aria-hidden="true">↗</span></Link></Nav>
    <main id="top" tabIndex={-1} className="event-detail">
      <div className="container">
        <nav className="event-detail-breadcrumb" aria-label="Percorso di navigazione">
          <ol><li><Link href="/#events"><Arrow back />Calendario</Link></li><li aria-hidden="true">/</li><li aria-current="page">{event.title}</li></ol>
        </nav>
        <article aria-labelledby="event-detail-title">
          <header className="event-detail-hero">
            <div className="event-detail-heading">
              <div className="event-detail-kicker"><span className="section-label">NEL RADAR</span>{event.isPast && <span className="event-detail-past">Evento passato</span>}</div>
              <h1 id="event-detail-title">{event.title}</h1>
              {event.organizer && <p className="event-detail-organizer">Organizzato da <strong>{event.organizer}</strong></p>}
              <div className="event-detail-key-facts">
                <div><span>QUANDO</span><strong>{startDate ? <time dateTime={startDate}>{event.dateLabel}</time> : event.dateLabel || "Data da confermare"}</strong></div>
                <div><span>DOVE</span><strong>{event.location || "Luogo da confermare"}</strong></div>
              </div>
            </div>
            <DetailArtwork />
          </header>

          <div className="event-detail-body">
            <aside className="event-detail-sidebar" aria-label="Link e strumenti per l’evento">
              <div className="event-detail-action-panel">
                <span className="section-label">IL PROSSIMO PASSO</span>
                <h2>{event.isPast ? "Consulta l’evento." : "Tieni a mente questa sfida."}</h2>
                <p>Trovi programma e modalità di partecipazione sul sito dell’organizzatore.</p>
                {sourceUrl && <a className="event-detail-official" href={sourceUrl} target="_blank" rel="noopener noreferrer">Sito ufficiale <Arrow /><span className="sr-only"> (si apre in una nuova scheda)</span></a>}
                <EventDetailActions event={event} />
              </div>
              <Link className="event-detail-return" href="/#events"><Arrow back />Torna al calendario</Link>
            </aside>
            <div className="event-detail-information">
              {showOverview && <section className="event-detail-overview" aria-labelledby="event-overview-title">
                <p className="section-label">L’EVENTO</p>
                <h2 id="event-overview-title">Le informazioni essenziali.</h2>
                <p className="event-detail-description">{event.description}</p>
              </section>}
              {event.facts.length > 0 && <section className={`event-detail-facts${showOverview ? "" : " event-detail-facts--lead"}`} aria-labelledby="event-facts-title">
                {!showOverview && <p className="section-label">L’EVENTO</p>}
                <h2 id="event-facts-title">{showOverview ? "Da sapere" : "Le informazioni essenziali."}</h2>
                <dl>{event.facts.map((fact, index) => {
                  const factUrl = safeLink(fact.sourceUrl);
                  return <div className="event-detail-fact" key={`${fact.label}-${index}`}><dt>{fact.label}</dt><dd><span>{fact.value}</span>{factUrl && <a href={factUrl} target="_blank" rel="noopener noreferrer" aria-label={`Consulta la fonte: ${fact.label}`}>Fonte <Arrow /></a>}</dd></div>;
                })}</dl>
              </section>}
              {event.missing.length > 0 && <section className="event-detail-missing" aria-labelledby="event-missing-title">
                <h2 id="event-missing-title">Da verificare sul sito ufficiale</h2>
                <p>Questi dettagli non sono confermati nella scheda:</p>
                <ul>{event.missing.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
              </section>}
              <section className="event-detail-provenance" aria-labelledby="event-source-title">
                <h2 id="event-source-title">Dalla fonte alla scheda</h2>
                {sourceUrl ? <a className="event-detail-source" href={sourceUrl} target="_blank" rel="noopener noreferrer"><span>{event.sourceLabel || "Sito ufficiale dell’evento"}</span><Arrow /></a> : <p>Link alla fonte non disponibile.</p>}
                {checked && <p>Informazioni controllate il <time dateTime={event.checkedAt}>{checked}</time>.</p>}
                <p>Programma, requisiti e disponibilità possono cambiare. Consulta il sito ufficiale prima di organizzarti.</p>
                {reportUrl && <a className="event-detail-report" href={reportUrl} target="_blank" rel="noopener noreferrer">Segnala un’informazione da correggere <Arrow /></a>}
              </section>
            </div>
          </div>
        </article>

        {relatedEvents.length > 0 && <section className="event-detail-related" aria-labelledby="event-related-title">
          <div className="event-detail-related-heading"><div><span className="section-label">CONTINUA A ESPLORARE</span><h2 id="event-related-title">Altre idee in calendario.</h2></div><Link href="/#events">Tutti gli eventi <Arrow /></Link></div>
          <div className="event-detail-related-grid">{relatedEvents.map((item) => <Link className="event-detail-related-card" key={item.id} href={item.detailPath}>
            <div className="event-detail-related-date">{validEventDate(item.dateIso) ? <time dateTime={item.dateIso}>{item.dateLabel}</time> : <span>{item.dateLabel || "Data da confermare"}</span>}<Arrow /></div>
            <h3>{item.title}</h3><p>{item.location || "Luogo da confermare"}</p><span className="event-detail-related-label">Leggi la scheda</span>
          </Link>)}</div>
        </section>}
      </div>
    </main>
    <Footer />
  </>;
}
