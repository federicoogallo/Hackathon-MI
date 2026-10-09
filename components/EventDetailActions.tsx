"use client";

import { useEffect, useRef, useState } from "react";
import type { EventDetail } from "@/lib/event-details";
import { eventCalendar, validEventDate } from "@/lib/event-filters";

const SAVED_STORAGE_KEY = "hackathon-mi:saved-events";
const SAVED_CHANGE_EVENT = "hackathon-mi:saved-events-changed";

function readSavedIds(): string[] {
  const raw = window.localStorage.getItem(SAVED_STORAGE_KEY);
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error("Invalid saved events");
  return [...new Set(parsed.filter((id): id is string => typeof id === "string"))];
}

function ActionIcon({ name }: { name: "bookmark" | "calendar" | "link" }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === "bookmark" ? <path d="M7 3.5h10a1 1 0 0 1 1 1v16l-6-4-6 4v-16a1 1 0 0 1 1-1Z" /> : name === "calendar" ? <><rect x="4" y="5" width="16" height="16" rx="2" /><path d="M8 3v4m8-4v4M4 11h16m-8 3v4m-2-2h4" /></> : <><path d="m10 13 4-4m-6 6-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 2 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(1 1)" /></>}
  </svg>;
}

export default function EventDetailActions({ event }: { event: EventDetail }) {
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  const [storageError, setStorageError] = useState("");
  const [notice, setNotice] = useState("");
  const [copying, setCopying] = useState(false);
  const sessionSavedIds = useRef<string[] | null>(null);
  const saved = savedIds.includes(event.id);
  const hasDate = Boolean(validEventDate(event.dateIso)) && event.dateVerified !== false;

  useEffect(() => {
    setNotice("");
    const sync = () => {
      if (sessionSavedIds.current) { setSavedIds(sessionSavedIds.current); setReady(true); return; }
      try { setSavedIds(readSavedIds()); setStorageError(""); }
      catch { setStorageError("Il browser non consente di leggere i salvati. Puoi conservare l’evento per questa visita."); }
      setReady(true);
    };
    const visible = () => { if (document.visibilityState === "visible") sync(); };
    const storage = (change: StorageEvent) => { if (change.key === SAVED_STORAGE_KEY || change.key === null) sync(); };
    sync();
    window.addEventListener("storage", storage);
    window.addEventListener("focus", sync);
    window.addEventListener("pageshow", sync);
    window.addEventListener(SAVED_CHANGE_EVENT, sync);
    document.addEventListener("visibilitychange", visible);
    return () => {
      window.removeEventListener("storage", storage);
      window.removeEventListener("focus", sync);
      window.removeEventListener("pageshow", sync);
      window.removeEventListener(SAVED_CHANGE_EVENT, sync);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [event.id]);

  function toggleSaved() {
    // Read at the time of the action so saving here preserves changes in other tabs.
    let current = sessionSavedIds.current || savedIds;
    if (!sessionSavedIds.current) {
      try { current = readSavedIds(); } catch { /* Keep the list for this visit. */ }
    }
    const wasSaved = current.includes(event.id);
    const next = wasSaved ? current.filter((id) => id !== event.id) : [...current, event.id];
    setSavedIds(next);
    try {
      window.localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(next));
      sessionSavedIds.current = null;
      setStorageError("");
      setNotice(wasSaved ? "Evento rimosso dai salvati." : "Evento aggiunto ai salvati di questo browser.");
      window.dispatchEvent(new Event(SAVED_CHANGE_EVENT));
    } catch {
      sessionSavedIds.current = next;
      setStorageError("Il browser non consente il salvataggio permanente. La scelta resta disponibile per questa visita.");
      setNotice(wasSaved ? "Evento rimosso dalla lista di questa visita." : "Evento salvato per questa visita.");
    }
  }

  function downloadCalendar() {
    const contents = eventCalendar(event);
    if (!contents) return;
    let objectUrl: string | undefined;
    let link: HTMLAnchorElement | undefined;
    try {
      objectUrl = URL.createObjectURL(new Blob([contents], { type: "text/calendar;charset=utf-8" }));
      link = document.createElement("a");
      link.href = objectUrl;
      link.download = `${event.slug}.ics`;
      document.body.appendChild(link);
      link.click();
      setNotice("Calendario scaricato. Contiene la data di inizio: verifica orari e durata sul sito ufficiale.");
    } catch { setNotice("Download non riuscito. Riprova o consulta la data sul sito ufficiale."); }
    finally {
      link?.remove();
      if (objectUrl) { const url = objectUrl; window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
    }
  }

  async function copyLink() {
    setCopying(true);
    try {
      await navigator.clipboard.writeText(new URL(event.detailPath, window.location.origin).href);
      setNotice("Link della scheda copiato.");
    } catch { setNotice("Copia non disponibile. Puoi copiare il link dalla barra degli indirizzi."); }
    finally { setCopying(false); }
  }

  return <div className="event-detail-actions">
    <button className={`event-detail-action${saved ? " is-saved" : ""}`} type="button" aria-pressed={saved} disabled={!ready} onClick={toggleSaved}>
      <ActionIcon name="bookmark" /><span>{saved ? "Evento salvato" : "Salva evento"}</span>
    </button>
    {hasDate && <button className="event-detail-action" type="button" onClick={downloadCalendar} aria-describedby="event-calendar-note"><ActionIcon name="calendar" /><span>Aggiungi al calendario</span></button>}
    <button className="event-detail-action" type="button" onClick={copyLink} disabled={copying}><ActionIcon name="link" /><span>{copying ? "Copia in corso…" : "Copia link della scheda"}</span></button>
    <p className="event-detail-action-note">I salvati restano in questo browser.{hasDate && <> <span id="event-calendar-note">Il calendario contiene solo la data di inizio.</span></>}</p>
    {storageError && <p className="event-detail-action-error">{storageError}</p>}
    <p className="event-detail-action-feedback" role="status" aria-live="polite" aria-atomic="true">{notice}</p>
  </div>;
}
