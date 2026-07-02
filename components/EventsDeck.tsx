"use client";
import { useMemo, useState } from "react";
import type { HackEvent } from "@/lib/data";

const SvgPin = (
  <svg viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clipRule="evenodd" /></svg>
);
const SvgCal = (
  <svg viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clipRule="evenodd" /></svg>
);
const SvgArrow = (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8h10M9 4l4 4-4 4" /></svg>
);

type Filter = "all" | "week" | "month" | "later";

function inFilter(e: HackEvent, f: Filter): boolean {
  if (f === "all") return true;
  if (!e.dateIso) return f === "later";
  const d = new Date(e.dateIso + "T12:00:00");
  const now = new Date();
  const diff = (d.getTime() - now.getTime()) / 86400000;
  if (f === "week") return diff >= 0 && diff <= 7;
  if (f === "month") return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  return diff > 31;
}

function onSpot(ev: React.PointerEvent<HTMLElement>) {
  const el = ev.currentTarget;
  const r = el.getBoundingClientRect();
  el.style.setProperty("--mx", `${((ev.clientX - r.left) / r.width) * 100}%`);
  el.style.setProperty("--my", `${((ev.clientY - r.top) / r.height) * 100}%`);
}

export default function EventsDeck({ events }: { events: HackEvent[] }) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const shown = useMemo(() => {
    const query = q.trim().toLowerCase();
    return events.filter((e) => e.searchBlob.includes(query) && inFilter(e, filter));
  }, [events, q, filter]);

  const pills: Array<[Filter, string]> = [["all", "Tutti"], ["week", "Settimana"], ["month", "Mese"], ["later", "Prossimi"]];

  return (
    <>
      <div className="toolbar" aria-label="Filtri eventi">
        <div className="search">
          <label className="sr-only" htmlFor="search">Cerca eventi</label>
          <svg className="search-icon" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" /></svg>
          <input type="text" id="search" placeholder="Cerca hackathon, fonte o luogo..." autoComplete="off" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="pills">
          {pills.map(([f, label]) => (
            <button key={f} className={`pill${filter === f ? " active" : ""}`} onClick={() => setFilter(f)}>{label}</button>
          ))}
        </div>
      </div>
      <div className="deck-head">
        <strong>Prossimi eventi verificati</strong>
        <span id="count-label">{shown.length} {shown.length === 1 ? "evento" : "eventi"}</span>
      </div>
      <div className="grid" id="grid">
        {events.length === 0 && (
          <div className="empty" data-reveal>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 3v3M17 3v3M4.5 9h15M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" />
              <path d="m9 14 2 2 4-4" />
            </svg>
            <h3>Nessun hackathon in programma</h3>
            <p>Non ci sono hackathon futuri confermati a Milano al momento.<br />La lista si aggiorna ogni giorno automaticamente.</p>
          </div>
        )}
        {events.map((e) => (
          <article key={e.id} className="card" hidden={!shown.includes(e)} onPointerMove={onSpot} data-reveal>
            <div className="date">
              <div>
                <strong>{e.day || "TBD"}</strong>
                <span>{e.month || "DATA"}</span>
              </div>
            </div>
            <div className="card-body">
              <h3 className="card-title"><a href={e.url} target="_blank" rel="noopener noreferrer">{e.title}</a></h3>
              <div className="card-meta">
                <span>{SvgPin}{e.location}</span>
                {e.dateCompact && <span>{SvgCal}{e.dateCompact}</span>}
              </div>
              <div className="chips">
                {e.reviewStatus === "manual_approved"
                  ? <span className="chip manual">Verifica manuale</span>
                  : e.confidence > 0 && <span className="chip ai">AI {Math.round(e.confidence * 100)}%</span>}
                {!e.dateIso && <span className="chip tbd">Data da confermare</span>}
              </div>
              {e.description && <p className="card-desc">{e.description}</p>}
              <div className="card-foot">
                <span className="source">{e.source}</span>
                <div className="actions">
                  <a href={e.issueOk} className="act" target="_blank" rel="noopener noreferrer">Valuta OK</a>
                  <a href={e.issueDoubt} className="act" target="_blank" rel="noopener noreferrer">Segnala dubbio</a>
                  <a href={e.url} className="act go" target="_blank" rel="noopener noreferrer">Vedi evento{SvgArrow}</a>
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
      {events.length > 0 && shown.length === 0 && <p className="no-results">Nessun risultato trovato.</p>}
    </>
  );
}
