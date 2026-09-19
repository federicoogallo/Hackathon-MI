import type { Metadata } from "next";
import Link from "next/link";
import { getReviewData } from "@/lib/data";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import "@/components/secondary-pages.css";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Eventi da verificare — Hackathon Milano",
  description: "Le opportunità individuate a Milano e dintorni che richiedono ancora una revisione. Consulta le fonti e contribuisci alla verifica.",
  alternates: { canonical: "/review" },
};

const arrow = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12h14m-6-6 6 6-6 6" />
  </svg>
);
const pin = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2" />
  </svg>
);
const calendar = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="5" width="16" height="16" rx="2" /><path d="M16 3v4M8 3v4M4 11h16" />
  </svg>
);

function sourceLabel(source: string): string {
  const names: Record<string, string> = {
    web_search: "Ricerca web", eventbrite: "Eventbrite", meetup: "Meetup",
    devpost: "Devpost", luma: "Luma", lu_ma: "Luma", mlh: "Major League Hacking",
  };
  return names[source.toLowerCase()] || source.replace(/_/g, " ") || "Fonte online";
}

export default function ReviewPage() {
  const { candidates, lastScan } = getReviewData();

  return (
    <>
      <Nav><Link className="btn btn-primary" href="/#events">Esplora gli eventi</Link></Nav>
      <main className="secondary-page" id="top" tabIndex={-1}>
        <header className="secondary-hero container">
          <div className="secondary-hero-copy">
            <p className="eyebrow">Dietro la selezione</p>
            <h1>Le prossime opportunità,<br /><span>sotto esame.</span></h1>
            <p className="secondary-lead">
              Ogni scoperta merita un controllo. Qui trovi gli eventi individuati
              dalla ricerca automatica che richiedono ancora una revisione.
              Non sono ancora confermati.
            </p>
          </div>
          <aside className="secondary-summary" aria-label="Stato della revisione">
            <span className="secondary-summary-label">In attesa di revisione</span>
            <strong className="secondary-count">{String(candidates.length).padStart(2, "0")}</strong>
            <span className="secondary-summary-caption">opportunità da approfondire</span>
            <div className="secondary-scan">
              <span>Ultima ricerca</span>
              <strong>{lastScan || "Aggiornamento non disponibile"}</strong>
            </div>
          </aside>
        </header>

        <section className="secondary-content container" id="events" aria-labelledby="review-heading">
          <div className="secondary-section-heading">
            <div>
              <p className="section-label">La revisione</p>
              <h2 id="review-heading">Un secondo sguardo, insieme.</h2>
            </div>
            <p>
              Conosci uno di questi eventi? Puoi proporre una conferma o segnalare
              un dubbio su GitHub. La decisione finale spetta ai curatori.
            </p>
          </div>
          {candidates.length === 0 ? (
            <div className="secondary-empty">
              <div className="secondary-empty-icon" aria-hidden="true">
                <svg viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="7" y="7" width="26" height="26" rx="7" /><path d="m13 20 5 5 9-10" />
                </svg>
              </div>
              <p className="secondary-empty-kicker">Nessun candidato in attesa</p>
              <h3>Tutto in ordine, per ora.</h3>
              <p>Al momento non ci sono eventi da rivedere. Il tuo prossimo progetto potrebbe già essere tra le opportunità pubblicate.</p>
              <Link className="btn btn-primary" href="/#events">Trova il tuo prossimo hackathon {arrow}</Link>
            </div>
          ) : (
            <>
              <p className="secondary-confidence-note">
                <span aria-hidden="true">i</span>
                La confidenza AI indica quanto il sistema ritiene pertinente un evento: non è una verifica della sua affidabilità.
              </p>
              <div className="secondary-review-list">
                {candidates.map((candidate, index) => (
                  <article key={candidate.id + candidate.url} className="secondary-review-card">
                    <div className="secondary-card-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</div>
                    <div className="secondary-card-content">
                      <div className="secondary-card-heading">
                        <div>
                          <p className="secondary-card-source">{sourceLabel(candidate.source)}</p>
                          <h3><a href={candidate.url} target="_blank" rel="noopener noreferrer">{candidate.title}<span className="sr-only"> (si apre in una nuova scheda)</span></a></h3>
                        </div>
                        <span className="secondary-confidence">Confidenza AI {candidate.confidence}%</span>
                      </div>
                      <div className="secondary-card-meta">
                        <span>{pin}{candidate.location || "Luogo da definire"}</span>
                        <span>{calendar}{candidate.dateCompact === "TBD" ? "Data da definire" : candidate.dateCompact}</span>
                      </div>
                      <div className="secondary-review-reason">
                        <strong>Da approfondire</strong>
                        <p>{candidate.reason}</p>
                      </div>
                      <div className="secondary-card-actions">
                        <a href={candidate.url} className="btn btn-primary" target="_blank" rel="noopener noreferrer">Visita l’evento {arrow}<span className="sr-only"> (si apre in una nuova scheda)</span></a>
                        <div className="secondary-review-actions">
                          <a href={candidate.issueOk} target="_blank" rel="noopener noreferrer">Proponi una conferma<span className="sr-only"> su GitHub (si apre in una nuova scheda)</span></a>
                          <a href={candidate.issueDoubt} target="_blank" rel="noopener noreferrer">Segnala un dubbio<span className="sr-only"> su GitHub (si apre in una nuova scheda)</span></a>
                        </div>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
      </main>
      <Footer />
    </>
  );
}
