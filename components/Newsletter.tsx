"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import "./newsletter.css";

const SEEN_KEY = "hackathon-mi:newsletter-seen";

function Envelope() {
  return <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="4" y="7" width="24" height="18" rx="3" /><path d="m5 9 11 8L27 9M5 24l8-9m14 9-8-9" /></svg>;
}

export default function Newsletter({ available, promptMode = "always" }: { available: boolean; promptMode?: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");
  const [open, setOpen] = useState(false);

  function show() {
    if (dialog.current?.open) return;
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!dialog.current?.open) dialog.current?.showModal();
    setOpen(true);
    try { localStorage.setItem(SEEN_KEY, "1"); } catch { /* The prompt works without storage. */ }
  }
  function close() { dialog.current?.close(); }

  useEffect(() => {
    if (promptMode === "off") return;
    if (promptMode === "first-visit") {
      try { if (localStorage.getItem(SEEN_KEY)) return; } catch { /* Show when no preference can be read. */ }
    }
    const timer = window.setTimeout(() => {
      // Never steal focus while someone is filling the search or another form.
      if (document.visibilityState !== "visible" || document.activeElement?.matches("input, textarea, select, [contenteditable=true]")) return;
      show();
    }, 6500);
    return () => window.clearTimeout(timer);
  }, [promptMode]);

  useEffect(() => {
    if (!open) return;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = oldOverflow; };
  }, [open]);

  async function subscribe(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!available || status === "sending") return;
    const form = new FormData(event.currentTarget);
    setStatus("sending");
    setMessage("");
    try {
      const response = await fetch("/api/newsletter/subscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, consent, website: form.get("website") }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || "Non è stato possibile completare la richiesta. Riprova fra poco.");
      setStatus("sent");
      setMessage("Controlla la tua casella: apri il link e conferma l’iscrizione. Se non trovi l’email, verifica anche lo spam.");
      setEmail("");
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Connessione non disponibile. Riprova fra poco.");
    }
  }

  return <>
    <section className="newsletter-section container" aria-labelledby="newsletter-title">
      <div className="newsletter-inline-icon"><Envelope /></div>
      <div><span className="section-label">IL RADAR, NELLA TUA CASELLA</span><h2 id="newsletter-title">La prossima sfida <br /><em>arriva da te.</em></h2><p>Un riepilogo a settimana, solo quando troviamo nuovi hackathon.</p></div>
      <button type="button" className="btn btn-dark" onClick={show}>Avvisami via email <span aria-hidden="true">↗</span></button>
    </section>
    <dialog ref={dialog} className="newsletter-dialog" aria-labelledby="newsletter-dialog-title" aria-describedby="newsletter-dialog-description" onClose={() => { setOpen(false); previousFocus.current?.focus({ preventScroll: true }); }} onClick={event => { if (event.target === event.currentTarget) { const bounds = event.currentTarget.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close(); } }}>
      <button type="button" className="newsletter-close" onClick={close} aria-label="Chiudi l’invito alla newsletter" autoFocus><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
      <div className="newsletter-art" aria-hidden="true"><span className="newsletter-art-orbit" /><div className="newsletter-ticket"><span>HACKATHON MILANO</span><Envelope /><strong>La tua prossima<br /><em>buona idea.</em></strong><small>UN INCONTRO PUÒ CAMBIARE TUTTO.</small></div><svg className="newsletter-art-star" viewBox="0 0 80 80" fill="none" stroke="currentColor" strokeWidth="12"><path d="M40 4v72M4 40h72M15 15l50 50M15 65l50-50" /></svg></div>
      <div className="newsletter-dialog-content">
        <span className="section-label">UNA VOLTA A SETTIMANA</span><h2 id="newsletter-dialog-title">Le nuove sfide.<br /><em>Prima che ti sfuggano.</em></h2>
        <p id="newsletter-dialog-description">Ricevi gli hackathon appena trovati a Milano e dintorni. Solo novità, con date e link per partecipare.</p>
        {!available && <p className="newsletter-preview-note">Anteprima: le iscrizioni via email saranno disponibili a breve. Per ora puoi esplorare gli eventi sul sito.</p>}
        {status === "sent" ? <div className="newsletter-success" role="status"><Envelope /><h3>Manca solo la tua conferma.</h3><p>{message}</p><button type="button" className="btn btn-dark" onClick={close}>Torna agli eventi</button></div> : <form onSubmit={subscribe}>
          <label className="newsletter-email-label" htmlFor="newsletter-email">Il tuo indirizzo email</label>
          <input id="newsletter-email" name="email" type="email" inputMode="email" autoComplete="email" placeholder="tu@esempio.it" value={email} onChange={event => setEmail(event.target.value)} required maxLength={254} disabled={!available || status === "sending"} />
          <div className="newsletter-honeypot" aria-hidden="true"><label htmlFor="newsletter-website">Sito web</label><input id="newsletter-website" name="website" type="text" tabIndex={-1} autoComplete="off" /></div>
          <div className="newsletter-consent"><input id="newsletter-consent" type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} required disabled={!available || status === "sending"} /><span><label htmlFor="newsletter-consent">Desidero ricevere il riepilogo settimanale e ho letto l’</label><Link href="/privacy">informativa privacy</Link>.</span></div>
          <button className="btn btn-dark newsletter-submit" type="submit" disabled={!available || status === "sending"}>{status === "sending" ? "Invio in corso…" : "Avvisami dei nuovi hackathon"}<span aria-hidden="true">↗</span></button>
          {status === "error" && <p className="newsletter-error" role="alert">{message}</p>}
          <p className="newsletter-footnote">Confermi via email. Ti disiscrivi quando vuoi, da ogni messaggio.</p>
        </form>}
      </div>
    </dialog>
  </>;
}
