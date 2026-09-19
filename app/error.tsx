"use client";

import { useEffect } from "react";
import Link from "next/link";
import Nav from "@/components/Nav";
import "@/components/secondary-pages.css";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("[hackathon-milano]", error);
  }, [error]);

  return (
    <>
      <Nav><Link className="btn btn-primary" href="/#events">Esplora gli eventi</Link></Nav>
      <main className="secondary-page secondary-status-page" id="top" tabIndex={-1}>
        <div className="container secondary-status-layout">
          <div className="secondary-status-art" aria-hidden="true">
            <span>Ops.</span>
            <svg viewBox="0 0 80 80" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M62 28a25 25 0 1 0 2 20M62 13v15H47" /></svg>
          </div>
          <div className="secondary-status-copy" role="alert">
            <p className="eyebrow">Un piccolo imprevisto</p>
            <h1>Facciamo<br /><span>un altro tentativo.</span></h1>
            <p className="secondary-lead">Non siamo riusciti a caricare questa pagina. Riprova tra un momento oppure torna alla ricerca degli hackathon.</p>
            {error.digest && <p className="secondary-error-code">Codice errore: <code>{error.digest}</code></p>}
            <div className="secondary-status-actions">
              <button className="btn btn-primary" onClick={reset} type="button">Riprova a caricare</button>
              <Link className="btn btn-ghost" href="/">Torna alla home</Link>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
