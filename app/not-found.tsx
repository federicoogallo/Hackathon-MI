import Link from "next/link";
import type { Metadata } from "next";
import Nav from "@/components/Nav";
import { REPO_URL } from "@/lib/data";
import "@/components/secondary-pages.css";

export const metadata: Metadata = {
  title: "Pagina non trovata — Hackathon Milano",
  description: "La pagina cercata non esiste o è stata spostata. Torna agli hackathon di Milano e dintorni.",
  robots: { index: false, follow: true },
};

export default function NotFound() {
  return (
    <>
      <Nav><Link className="btn btn-primary" href="/#events">Esplora gli eventi</Link></Nav>
      <main className="secondary-page secondary-status-page" id="top" tabIndex={-1}>
        <div className="container secondary-status-layout">
          <div className="secondary-status-art" aria-hidden="true">
            <span>404</span>
            <svg viewBox="0 0 80 80" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 62 62 18M18 18h44v44" /></svg>
          </div>
          <div className="secondary-status-copy">
            <p className="eyebrow">Fuori percorso</p>
            <h1>Questa pagina ha preso<br /><span>un’altra strada.</span></h1>
            <p className="secondary-lead">Il link potrebbe essere incompleto o la pagina potrebbe essere stata spostata. Le prossime opportunità ti aspettano nella raccolta degli eventi.</p>
            <div className="secondary-status-actions">
              <Link className="btn btn-primary" href="/#events">Esplora gli hackathon</Link>
              <Link className="btn btn-ghost" href="/review">Eventi da verificare</Link>
            </div>
            <a className="secondary-help-link" href={`${REPO_URL}/issues/new`} target="_blank" rel="noopener noreferrer">Segnala un link non funzionante<span className="sr-only"> su GitHub (si apre in una nuova scheda)</span></a>
          </div>
        </div>
      </main>
    </>
  );
}
