"use client";

import { useEffect } from "react";

/**
 * Error boundary di rotta: senza questo, un errore a runtime mostra la pagina
 * di default di Next (bianca, fuori tema). Qui resta in tema e offre una via
 * d'uscita concreta: riprova, home, oppure apri una issue.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[hackathon-milano]", error);
  }, [error]);

  return (
    <main className="status-page" id="top" tabIndex={-1}>
      <div className="container">
        <div className="status-inner" role="alert">
          <span className="status-code mono" aria-hidden="true">500</span>
          <h1 className="h2">Qualcosa si e&apos; <em>rotto</em>.</h1>
          <p className="lead-p">
            Errore imprevisto nel caricamento della pagina. Riprovare di solito basta;
            se persiste, segnalalo e verra&apos; corretto.
          </p>
          {error.digest && (
            <p className="status-digest mono">codice errore: {error.digest}</p>
          )}
          <div className="hero-cta">
            <button className="btn btn-primary" onClick={reset} type="button">Riprova</button>
            <a className="btn btn-ghost" href="/">Torna alla home</a>
          </div>
        </div>
      </div>
    </main>
  );
}
