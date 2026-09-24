"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { markNewsletterInviteSeen, readNewsletterPreferences, shouldAutoPrompt, NEWSLETTER_STORAGE_EVENT } from "@/lib/newsletter-preferences";
import "./newsletter.css";

function Envelope() {
  return <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="4" y="7" width="24" height="18" rx="3" /><path d="m5 9 11 8L27 9M5 24l8-9m14 9-8-9" /></svg>;
}

export default function Newsletter({ available, promptMode = "first-visit" }: { available: boolean; promptMode?: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [message, setMessage] = useState("");
  const [open, setOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const previouslyConfirmed = useRef(false);

  const show = useCallback(() => {
    if (!dialog.current || dialog.current.open) return;
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current.showModal();
    setOpen(true);
    if (available) markNewsletterInviteSeen();
  }, [available]);
  function close() { dialog.current?.close(); }

  useEffect(() => {
    const sync = () => {
      const next = readNewsletterPreferences().confirmed;
      if (next && !previouslyConfirmed.current) dialog.current?.close();
      previouslyConfirmed.current = next;
      setConfirmed(next);
    };
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener(NEWSLETTER_STORAGE_EVENT, sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener(NEWSLETTER_STORAGE_EVENT, sync);
    };
  }, []);

  useEffect(() => {
    if (!shouldAutoPrompt(available, promptMode, readNewsletterPreferences())) return;
    const timer = window.setTimeout(() => {
      // Recheck preferences: another tab may have shown the invite or confirmed an address.
      if (!shouldAutoPrompt(available, promptMode, readNewsletterPreferences())) return;
      if (document.visibilityState !== "visible" || document.activeElement?.matches("input, textarea, select, [contenteditable=true]")) return;
      show();
    }, 6500);
    return () => window.clearTimeout(timer);
  }, [available, promptMode, confirmed, show]);

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
      <div><span className="section-label">IL RADAR, NELLA TUA CASELLA</span><h2 id="newsletter-title">La prossima sfida <br /><em>arriva da te.</em></h2><p>{available ? "Un riepilogo a settimana, solo quando troviamo nuovi hackathon." : "Stiamo preparando il riepilogo settimanale. Le iscrizioni non sono ancora aperte."}</p></div>
      <button type="button" className="btn btn-dark" onClick={show}>{available ? "Avvisami via email" : "Stato newsletter"} <span aria-hidden="true">↗</span></button>
    </section>
    <dialog ref={dialog} className="newsletter-dialog" aria-labelledby="newsletter-dialog-title" aria-describedby="newsletter-dialog-description" onClose={() => { setOpen(false); previousFocus.current?.focus({ preventScroll: true }); }} onClick={event => { if (event.target === event.currentTarget) { const bounds = event.currentTarget.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close(); } }}>
      <button type="button" className="newsletter-close" onClick={close} aria-label="Chiudi l’invito alla newsletter" autoFocus><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
      <div className="newsletter-art" aria-hidden="true"><span className="newsletter-art-orbit" /><div className="newsletter-ticket"><span>HACKATHON MILANO</span><Envelope /><strong>La tua prossima<br /><em>buona idea.</em></strong><small>UN INCONTRO PUÒ CAMBIARE TUTTO.</small></div><svg className="newsletter-art-star" viewBox="0 0 80 80" fill="none" stroke="currentColor" strokeWidth="12"><path d="M40 4v72M4 40h72M15 15l50 50M15 65l50-50" /></svg></div>
      <div className="newsletter-dialog-content">
        <span className="section-label">{available ? "UNA VOLTA A SETTIMANA" : "ISCRIZIONI NON ANCORA APERTE"}</span><h2 id="newsletter-dialog-title">{available ? <>Le nuove sfide.<br /><em>Prima che ti sfuggano.</em></> : <>Il radar via email.<br /><em>Ci stiamo lavorando.</em></>}</h2>
        <p id="newsletter-dialog-description">{available ? "Ricevi gli hackathon appena trovati a Milano e dintorni. Solo novità, con date e link per partecipare." : "Il servizio email non è ancora attivo. Appena saranno aperte le iscrizioni, qui potrai lasciare il tuo indirizzo e confermarlo via email."}</p>
        {!available ? <div className="newsletter-unavailable"><p>Nel frattempo puoi esplorare il calendario e salvare gli eventi che ti interessano.</p><button type="button" className="btn btn-dark" onClick={close}>Torna agli eventi <span aria-hidden="true">↗</span></button></div> : status === "sent" ? <div className="newsletter-success" role="status"><Envelope /><h3>Manca solo la tua conferma.</h3><p>{message}</p><button type="button" className="btn btn-dark" onClick={close}>Torna agli eventi</button></div> : <form onSubmit={subscribe}>
          {confirmed && <p className="newsletter-preview-note">Hai già confermato un’iscrizione da questo browser. Puoi usare il modulo anche per un altro indirizzo.</p>}
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
