import type { Metadata } from "next";
import Link from "next/link";
import { getReviewData, REPO_URL } from "@/lib/data";
import Nav from "@/components/Nav";
import Fx from "@/components/Fx";
import HeroCanvas from "@/components/HeroCanvas";
import Materialize from "@/components/Materialize";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "Review queue - Hackathon Milano",
  description: "Candidati hackathon in attesa di revisione umana.",
};

const SvgPin = (
  <svg viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" /></svg>
);
const SvgCal = (
  <svg viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clipRule="evenodd" /></svg>
);
const SvgArrow = (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8h10M9 4l4 4-4 4" /></svg>
);

export default function ReviewPage() {
  const { candidates, lastScan } = getReviewData();

  return (
    <>
      <Fx />
      <Nav brandTitle="Review queue" brandSub="Manual confidence control" brandHref="/">
        <Link className="btn btn-primary" href="/">Eventi confermati</Link>
      </Nav>

      <header className="hero review-hero" id="top">
        <HeroCanvas />
        <div className="container">
          <div className="hero-grid review-grid">
            <div className="hero-copy">
              <div className="eyebrow"><span className="dot" />Manual review</div>
              <h1 className="hero-title" aria-label="Review queue">
                <span className="line"><Materialize text="Review" /></span>
                <span className="line title-accent">queue</span>
              </h1>
              <p className="hero-sub">
                {candidates.length} eventi hanno abbastanza segnale per una revisione umana.
                Gli utenti possono solo aprire issue di conferma o dubbio: la rimozione resta ai maintainer.
              </p>
              <div className="hero-status">
                <span className="ops-dot" />
                <strong>{candidates.length}</strong>
                <span>Aggiornato: {lastScan}</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="section" id="events">
        <div className="container">
          <div className="deck-head" data-reveal><strong>Da rivedere</strong><span>Manual layer</span></div>
          <div className="review-list">
            {candidates.length === 0 && (
              <div className="empty" data-reveal>
                <h3>Nessun candidato in revisione</h3>
                <p>La coda si popola solo quando il filtro AI non ha confidenza sufficiente.</p>
              </div>
            )}
            {candidates.map((c) => (
              <article key={c.id + c.url} className="review-card" data-reveal>
                <div className="review-head">
                  <div>
                    <div className="review-id">{c.id}</div>
                    <h2 className="review-title"><a href={c.url} target="_blank" rel="noopener noreferrer">{c.title}</a></h2>
                    <div className="card-meta">
                      <span className="source">{c.source}</span>
                      <span>{SvgPin}{c.location}</span>
                      <span>{SvgCal}{c.dateCompact}</span>
                    </div>
                  </div>
                  <span className="chip ai">AI {c.confidence}%</span>
                </div>
                <p className="review-reason">{c.reason}</p>
                <div className="actions">
                  <a href={c.issueOk} className="act" target="_blank" rel="noopener noreferrer">Valuta OK</a>
                  <a href={c.issueDoubt} className="act" target="_blank" rel="noopener noreferrer">Segnala dubbio</a>
                  <a href={c.url} className="act go" target="_blank" rel="noopener noreferrer">Vedi evento{SvgArrow}</a>
                </div>
              </article>
            ))}
          </div>
        </div>
      </main>

      <footer>
        <div className="container">
          <div className="footer-inner">
            <div className="footer-brand"><b>Hackathon Milano</b>Review queue generata dalla pipeline</div>
            <div className="footer-mid" />
            <div className="footer-links">
              <Link href="/">Calendario</Link>
              <a href={REPO_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
            </div>
          </div>
        </div>
      </footer>
    </>
  );
}
