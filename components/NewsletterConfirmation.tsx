"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { markNewsletterConfirmed } from "@/lib/newsletter-preferences";

export default function NewsletterConfirmation() {
  const token = useRef("");
  const initialized = useRef(false);
  const [status, setStatus] = useState<"loading" | "ready" | "sending" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    token.current = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
    window.history.replaceState(null, "", window.location.pathname);
    if (/^[a-f0-9]{64}$/.test(token.current)) setStatus("ready");
    else { setStatus("error"); setMessage("Il link non è completo. Apri il collegamento ricevuto via email oppure richiedi un nuovo invito dal sito."); }
  }, []);

  async function confirm() {
    if (!token.current || status === "sending") return;
    setStatus("sending");
    try {
      const response = await fetch("/api/newsletter/confirm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: token.current }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || "Non è stato possibile confermare l’iscrizione. Riprova fra poco.");
      markNewsletterConfirmed();
      token.current = "";
      setMessage("Riceverai il riepilogo settimanale quando troveremo nuovi hackathon. Puoi disiscriverti da ogni email.");
      setStatus("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Connessione non disponibile. Riprova fra poco.");
      setStatus("error");
    }
  }

  return <section className="confirmation-page container" aria-labelledby="confirmation-title"><p className="section-label">IL RADAR, NELLA TUA CASELLA</p><h1 id="confirmation-title">{status === "success" ? <>Ci vediamo<br /><em>nella tua casella.</em></> : <>La prossima sfida.<br /><em>A un passo da te.</em></>}</h1><p className="confirmation-lead">{status === "loading" ? "Verifica del collegamento…" : status === "ready" || status === "sending" ? "Conferma la tua iscrizione per ricevere una volta a settimana i nuovi hackathon a Milano e dintorni." : message}</p><div className="confirmation-actions">{token.current && status !== "success" && <button type="button" className="btn btn-dark" onClick={confirm} disabled={status === "sending"}>{status === "sending" ? "Conferma in corso…" : status === "error" ? "Riprova la conferma" : "Conferma iscrizione"}</button>}<Link className="btn btn-outline" href="/">Esplora gli hackathon <span aria-hidden="true">↗</span></Link></div><p className="confirmation-note" role="status" aria-live="polite">{status === "success" ? "Iscrizione confermata." : status === "error" ? "Iscrizione non confermata." : "La conferma avviene solo premendo il pulsante."} <Link href="/privacy">Informativa privacy</Link></p></section>;
}
