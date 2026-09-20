import type { Metadata } from "next";
import Link from "next/link";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import { newsletterConfigured } from "@/lib/newsletter-config";
import "@/components/secondary-pages.css";

export const metadata: Metadata = { title: "Privacy e newsletter | Hackathon Milano", description: "Come vengono gestiti i preferiti locali e l’iscrizione al riepilogo email di Hackathon Milano.", alternates: { canonical: "/privacy" } };

export default function PrivacyPage() {
  const active = newsletterConfigured();
  const owner = process.env.NEWSLETTER_OWNER;
  const contact = process.env.NEWSLETTER_CONTACT_EMAIL;
  return <><Nav /><main id="top" tabIndex={-1} className="secondary-page container"><header className="secondary-intro"><p className="section-label">I TUOI DATI, CON CHIAREZZA</p><h1>Privacy e <em>newsletter.</em></h1><p>Ultimo aggiornamento: 20 settembre 2026.</p></header><div className="privacy-copy">
    <section><h2>Preferenze nel browser</h2><p>Tema, eventi salvati e visualizzazione dell’invito alla newsletter restano nella memoria locale del tuo browser. Non richiedono un account e non vengono sincronizzati con i nostri server. Puoi rimuoverli cancellando i dati del sito.</p></section>
    <section><h2>Riepilogo settimanale</h2><p>{active ? "L’iscrizione è facoltativa e richiede la conferma dell’indirizzo tramite email." : "Il modulo è attualmente in anteprima: le iscrizioni non sono attive e non raccogliamo indirizzi tramite il modulo."} Una volta attivo, il servizio invia al massimo un riepilogo a settimana, solo se sono stati trovati nuovi hackathon.</p><p>L’indirizzo viene usato per il riepilogo richiesto, sulla base della tua scelta esplicita. Ogni messaggio include un collegamento per disiscriverti. L’iscrizione non è necessaria per consultare il sito.</p></section>
    <section><h2>Dove vengono gestiti i dati</h2><p>Il sito è ospitato su Vercel. Il servizio newsletter utilizza Resend per conferme, contatti e invii; Upstash Redis conserva temporaneamente le richieste di conferma e i limiti contro gli abusi. Gli indirizzi email non vengono scritti nel repository pubblico GitHub.</p><p>Le richieste non confermate scadono dopo 24 ore. I contatori contro gli abusi conservano identificativi derivati dall’indirizzo e dalla connessione, senza memorizzare l’IP in chiaro, per un massimo di 24 ore. La prova del consenso (identificativo derivato dall’email, versione dell’informativa e date di richiesta e conferma) viene conservata per 365 giorni. Resend conserva il contatto e lo stato di disiscrizione per rispettare la scelta di non ricevere altri messaggi; puoi chiedere la cancellazione al gestore.</p><p>I fornitori possono trattare dati in paesi diversi dal tuo. Le rispettive informative descrivono infrastruttura, conservazione e garanzie applicabili: <a href="https://vercel.com/legal/privacy-policy" target="_blank" rel="noopener noreferrer">Vercel</a>, <a href="https://resend.com/legal/privacy-policy" target="_blank" rel="noopener noreferrer">Resend</a>, <a href="https://upstash.com/trust/privacy.pdf" target="_blank" rel="noopener noreferrer">Upstash</a>.</p></section>
    <section><h2>Gestore e richieste</h2>{owner && contact ? <p>Il gestore del servizio è {owner}. Per accesso, rettifica, cancellazione o revoca del consenso, scrivi a <a href={`mailto:${contact}`}>{contact}</a>. Puoi inoltre rivolgerti all’autorità competente per la protezione dei dati personali.</p> : <p>I recapiti del gestore saranno pubblicati prima dell’attivazione delle iscrizioni. Fino ad allora il modulo rimane disabilitato.</p>}</section>
    <section><h2>Fonti esterne</h2><p>I link agli hackathon aprono siti gestiti dai rispettivi organizzatori, con le loro informative. Verifica sempre requisiti, data e modalità di partecipazione alla fonte.</p></section>
    <Link className="btn btn-dark" href="/">Torna agli hackathon</Link>
  </div></main><Footer /></>;
}
