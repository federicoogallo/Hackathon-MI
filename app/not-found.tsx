import Link from "next/link";
import type { Metadata } from "next";
import Nav from "@/components/Nav";
import { REPO_URL } from "@/lib/data";

export const metadata: Metadata = {
  title: "Pagina non trovata — Hackathon Milano",
  description: "La pagina cercata non esiste o e' stata spostata.",
  robots: { index: false, follow: true },
};

/**
 * 404 in tema col sito: senza questo file Next serve la sua pagina di default,
 * bianca, che rompe completamente l'estetica dark.
 */
export default function NotFound() {
  return (
    <>
      <Nav>
        <Link className="btn btn-ghost nav-secondary" href="/review">Candidati in review</Link>
        <Link className="btn btn-primary" href="/">Torna alla home</Link>
      </Nav>

      <main className="status-page" id="top" tabIndex={-1}>
        <div className="container">
          <div className="status-inner">
            <span className="status-code mono" aria-hidden="true">404</span>
            <h1 className="h2">Questa pagina non <em>esiste</em>.</h1>
            <p className="lead-p">
              Il link potrebbe essere scaduto o scritto male. Gli hackathon verificati
              sono tutti nel deck della home.
            </p>
            <div className="hero-cta">
              <Link className="btn btn-primary" href="/#events">Vai agli eventi</Link>
              <Link className="btn btn-ghost" href="/review">Candidati in review</Link>
              <a className="btn btn-ghost" href={`${REPO_URL}/issues/new`} target="_blank" rel="noopener noreferrer">
                Segnala un problema
              </a>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
