"use client";

import { Suspense, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { useSearchParams } from "next/navigation";
import type { HackEvent } from "@/lib/data";
import {
  DEFAULT_EVENT_FILTERS, eventCalendar, filterEvents, readEventFilters, sourceLabel,
  todayInRome, validEventDate, writeEventFilters, type EventFilters, type EventPeriod,
} from "@/lib/event-filters";
import "./events-deck.css";

const SAVED_STORAGE_KEY = "hackathon-mi:saved-events";
const PERIODS: Array<[EventPeriod, string]> = [["all", "Tutti gli eventi"], ["week", "Prossimi 7 giorni"], ["month", "Questo mese"], ["undated", "Data da definire"]];

function Icon({ name, className = "" }: { name: "search" | "bookmark" | "arrow" | "pin" | "calendar" | "grid" | "list" | "close" | "check"; className?: string }) {
  const paths = {
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    bookmark: <path d="M7 3.5h10a1 1 0 0 1 1 1v16l-6-4-6 4v-16a1 1 0 0 1 1-1Z" />,
    arrow: <path d="M6 18 18 6M6 6h12v12" />,
    pin: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
    calendar: <><rect x="4" y="5" width="16" height="16" rx="2" /><path d="M8 3v4m8-4v4M4 11h16m-8 3v4m-2-2h4" /></>,
    grid: <><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="4" y="14" width="6" height="6" rx="1" /><rect x="14" y="14" width="6" height="6" rx="1" /></>,
    list: <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    check: <path d="m5 12 4 4L19 6" />,
  };
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function readSavedIds(value: string | null): string[] {
  if (!value) return [];
  const parsed: unknown = JSON.parse(value);
  if (!Array.isArray(parsed)) throw new Error("Invalid saved events");
  return [...new Set(parsed.filter((id): id is string => typeof id === "string"))];
}

function safeLink(value: string): string | undefined {
  try { const url = new URL(value); return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined; }
  catch { return undefined; }
}

// Keep the server-rendered event collection outside the query hook's Suspense
// boundary, while also observing Next client navigations and native history.
function QuerySync({ onChange }: { onChange: Dispatch<SetStateAction<EventFilters>> }) {
  const params = useSearchParams();
  const search = params.toString();
  useEffect(() => { onChange(readEventFilters(search)); }, [search, onChange]);
  return null;
}

export default function EventsDeck({ events }: { events: HackEvent[] }) {
  const [filters, setFilters] = useState<EventFilters>(DEFAULT_EVENT_FILTERS);
  const [savedIds, setSavedIds] = useState<string[]>([]);
  const [today, setToday] = useState("");
  const [notice, setNotice] = useState("");
  const [storageError, setStorageError] = useState("");

  useEffect(() => {
    const readUrl = () => setFilters(readEventFilters(window.location.search));
    const updateDay = () => setToday(todayInRome());
    readUrl();
    updateDay();
    try { setSavedIds(readSavedIds(window.localStorage.getItem(SAVED_STORAGE_KEY))); }
    catch { setStorageError("Non è possibile leggere i salvati in questo browser. Puoi comunque creare una lista per questa visita."); }
    const onStorage = (event: StorageEvent) => {
      if (event.key !== SAVED_STORAGE_KEY) return;
      try { setSavedIds(readSavedIds(event.newValue)); setStorageError(""); }
      catch { setStorageError("Non è stato possibile sincronizzare i salvati. La lista attuale resta disponibile."); }
    };
    window.addEventListener("popstate", readUrl);
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", updateDay);
    const dayTimer = window.setInterval(updateDay, 60_000);
    return () => {
      window.removeEventListener("popstate", readUrl);
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", updateDay);
      window.clearInterval(dayTimer);
    };
  }, []);

  const sources = useMemo(() => [...new Set(events.map((event) => event.source))].sort((a, b) => sourceLabel(a).localeCompare(sourceLabel(b), "it")), [events]);
  const shown = useMemo(() => filterEvents(events, filters, savedIds, today), [events, filters, savedIds, today]);
  const savedCount = events.filter((event) => savedIds.includes(event.id)).length;
  const hasFilters = !!filters.q.trim() || filters.period !== "all" || filters.source !== "all" || filters.saved;

  function updateFilters(patch: Partial<EventFilters>, replace = false) {
    const next = { ...filters, ...patch };
    setFilters(next);
    const url = writeEventFilters(new URL(window.location.href), next);
    if (`${window.location.pathname}${window.location.search}${window.location.hash}` !== url) {
      window.history[replace ? "replaceState" : "pushState"](window.history.state, "", url);
    }
  }

  function resetFilters() { updateFilters({ ...DEFAULT_EVENT_FILTERS, view: filters.view, order: filters.order }); }

  function toggleSaved(event: HackEvent) {
    const wasSaved = savedIds.includes(event.id);
    const next = wasSaved ? savedIds.filter((id) => id !== event.id) : [...savedIds, event.id];
    setSavedIds(next);
    try {
      window.localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(next));
      setStorageError("");
      setNotice(wasSaved ? `${event.title}: rimosso dai salvati.` : `${event.title}: aggiunto ai salvati.`);
    } catch {
      setStorageError("Il browser non consente il salvataggio permanente. La tua lista è disponibile per questa visita.");
      setNotice(wasSaved ? "Evento rimosso dalla lista di questa visita." : "Evento salvato nella lista di questa visita.");
    }
  }

  function downloadCalendar(event: HackEvent) {
    const contents = eventCalendar(event);
    if (!contents) return;
    try {
      const url = URL.createObjectURL(new Blob([contents], { type: "text/calendar;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${event.title.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80) || "hackathon"}.ics`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(`Calendario scaricato per ${event.title}. Contiene la data di inizio: verifica orari e durata sul sito dell’organizzatore.`);
    } catch { setNotice("Non è stato possibile scaricare il calendario. Riprova o consulta la data sul sito dell’evento."); }
  }

  return (
    <div className="explorer">
      <Suspense fallback={null}><QuerySync onChange={setFilters} /></Suspense>
      <div className="explorer-heading">
        <div>
          <p className="explorer-eyebrow"><span />Il radar degli hackathon</p>
          <h2>Trova la tua<br className="explorer-heading-break" /> prossima sfida.</h2>
          <p className="explorer-intro">Un’idea, un team, un weekend diverso. Il prossimo passo inizia qui.</p>
        </div>
        <div className="explorer-total"><span>{String(events.length).padStart(2, "0")}</span><p>eventi nel radar<br /><strong>Milano e dintorni</strong></p></div>
      </div>
      <div className="explorer-controls" role="search" aria-label="Cerca e filtra gli hackathon">
        <div className="explorer-main-controls">
          <div className="explorer-search-field">
            <label htmlFor="event-search">Cerca un hackathon</label>
            <div className="explorer-search-input">
              <Icon name="search" />
              <input id="event-search" type="search" placeholder="Nome, argomento o luogo…" autoComplete="off" value={filters.q} onChange={(event) => updateFilters({ q: event.target.value }, true)} aria-controls="event-results" />
              {filters.q && <button type="button" className="explorer-clear" onClick={() => { updateFilters({ q: "" }, true); document.getElementById("event-search")?.focus(); }} aria-label="Cancella la ricerca"><Icon name="close" /></button>}
            </div>
          </div>
          <div className="explorer-source-field">
            <label htmlFor="event-source">Fonte</label>
            <select id="event-source" value={filters.source} onChange={(event) => updateFilters({ source: event.target.value })} aria-controls="event-results">
              <option value="all">Tutte le fonti</option>
              {filters.source !== "all" && !sources.includes(filters.source) && <option value={filters.source}>{sourceLabel(filters.source)}</option>}
              {sources.map((source) => <option key={source} value={source}>{sourceLabel(source)}</option>)}
            </select>
          </div>
          <button className={`explorer-saved-toggle${filters.saved ? " is-active" : ""}`} type="button" aria-pressed={filters.saved} onClick={() => updateFilters({ saved: !filters.saved })}>
            <Icon name="bookmark" /><span>I miei salvati</span><span className="explorer-saved-count">{savedCount}</span>
          </button>
        </div>
        <div className="explorer-filter-row">
          <div className="explorer-periods" role="group" aria-label="Periodo dell’evento">
            {PERIODS.map(([period, label]) => <button key={period} type="button" aria-pressed={filters.period === period} className={filters.period === period ? "is-active" : ""} onClick={() => updateFilters({ period })}>{label}</button>)}
          </div>
          <div className="explorer-view-toggle" role="group" aria-label="Visualizzazione eventi">
            <button type="button" aria-label="Visualizza a griglia" aria-pressed={filters.view === "grid"} onClick={() => updateFilters({ view: "grid" })}><Icon name="grid" /></button>
            <button type="button" aria-label="Visualizza come elenco" aria-pressed={filters.view === "list"} onClick={() => updateFilters({ view: "list" })}><Icon name="list" /></button>
          </div>
        </div>
      </div>
      <div className="explorer-result-bar">
        <p role="status" aria-live="polite" aria-atomic="true"><strong>{shown.length} {shown.length === 1 ? "evento" : "eventi"}</strong>{hasFilters ? " per la tua ricerca" : " da scoprire"}</p>
        <div className="explorer-result-actions">
          {hasFilters && <button type="button" className="explorer-reset" onClick={resetFilters}>Azzera filtri<Icon name="close" /></button>}
          <div className="explorer-order"><label htmlFor="event-order">Ordina per</label><select id="event-order" value={filters.order} onChange={(event) => updateFilters({ order: event.target.value === "name" ? "name" : "date" })}><option value="date">Data più vicina</option><option value="name">Nome A–Z</option></select></div>
        </div>
      </div>
      {storageError && <p className="explorer-storage-error" role="alert">{storageError}</p>}
      <div className={`explorer-results explorer-results--${filters.view}`} id="event-results">
        {shown.map((event) => {
          const saved = savedIds.includes(event.id);
          const date = validEventDate(event.dateIso);
          const url = safeLink(event.url);
          const issueUrl = safeLink(event.issueDoubt);
          return (
            <article key={event.id} className="explorer-card" aria-labelledby={`event-${event.id}`}>
              <div className="explorer-card-top">
                <div className={`explorer-date${date ? "" : " explorer-date--unknown"}`} aria-label={date ? `Data di inizio: ${event.dateCompact}` : "Data da definire"}>
                  <span>{date ? event.day : "—"}</span><span>{date ? event.month : "TBD"}</span>
                </div>
                <div className="explorer-card-source" title={`Trovato tramite ${sourceLabel(event.source)}`}><span>Fonte</span><strong>{url ? new URL(url).hostname.replace(/^www\./, "") : sourceLabel(event.source)}</strong></div>
                <button className={`explorer-save${saved ? " is-saved" : ""}`} type="button" aria-label={`${saved ? "Rimuovi dai salvati" : "Salva"}: ${event.title}`} aria-pressed={saved} title={saved ? "Rimuovi dai salvati" : "Salva evento"} onClick={() => toggleSaved(event)}><Icon name="bookmark" /></button>
              </div>
              <div className="explorer-card-content">
                <div className="explorer-card-meta"><span><Icon name="pin" />{event.location}</span><span>{date ? date.slice(0, 4) : "Data da definire"}</span></div>
                <h3 id={`event-${event.id}`}>{url ? <a href={url} target="_blank" rel="noopener noreferrer">{event.title}<span className="explorer-sr-only"> (si apre in una nuova scheda)</span></a> : event.title}</h3>
                <p className="explorer-description">{event.description || "Tutti i dettagli, il programma e le modalità di partecipazione sul sito dell’evento."}</p>
                <span className={`explorer-verification${event.reviewStatus === "manual_approved" ? " explorer-verification--manual" : ""}`}><Icon name="check" />{event.reviewStatus === "manual_approved" ? "Verifica manuale" : "Selezionato dal monitor"}</span>
              </div>
              <div className="explorer-card-bottom">
                <div className="explorer-card-actions">
                  {url ? <a className="explorer-discover" href={url} target="_blank" rel="noopener noreferrer">Scopri evento<Icon name="arrow" /><span className="explorer-sr-only"> (si apre in una nuova scheda)</span></a> : <span className="explorer-unavailable">Link da verificare</span>}
                  {date && <button type="button" className="explorer-calendar" onClick={() => downloadCalendar(event)} title="Aggiunge il giorno di inizio; verifica durata e orari alla fonte" aria-label={`Aggiungi la data di inizio al calendario: ${event.title}`}><Icon name="calendar" /><span>Calendario</span></button>}
                </div>
                {issueUrl && <a className="explorer-report" href={issueUrl} target="_blank" rel="noopener noreferrer">Segnala un dubbio<span className="explorer-sr-only"> su {event.title} (GitHub, nuova scheda)</span><Icon name="arrow" /></a>}
              </div>
            </article>
          );
        })}
        {shown.length === 0 && <div className="explorer-empty">
          <div className="explorer-empty-icon"><Icon name={filters.saved ? "bookmark" : "search"} /></div>
          <p className="explorer-eyebrow">Un nuovo punto di partenza</p>
          <h3>{events.length === 0 ? "Il radar è in ascolto." : filters.saved && savedCount === 0 ? "Le prossime idee, tutte qui." : "Nessuna sfida con questi filtri."}</h3>
          <p>{events.length === 0 ? "Al momento non ci sono hackathon in programma nel radar. Torna dopo la prossima scansione per scoprire nuove opportunità." : filters.saved && savedCount === 0 ? "Salva gli eventi che ti interessano con l’icona segnalibro. Li ritroverai qui, in questo browser, senza creare un account." : "Prova un altro nome, amplia il periodo o cambia la fonte. Il tuo prossimo hackathon potrebbe essere a un filtro di distanza."}</p>
          {events.length > 0 && <button type="button" onClick={resetFilters}>Esplora tutti gli eventi<Icon name="arrow" /></button>}
        </div>}
      </div>
      <div className="explorer-footnote"><span><Icon name="bookmark" />I salvati restano nel tuo browser.</span><span>Date e iscrizioni? L’ultima parola è dell’organizzatore.</span></div>
      <p className="explorer-sr-only" aria-live="polite" aria-atomic="true">{notice}</p>
    </div>
  );
}
