"""
Genera una pagina HTML statica con tutti gli hackathon futuri confermati.

Output: docs/index.html  servita via GitHub Pages.
Viene rigenerata ad ogni run della pipeline.
Design: light theme, Inter font, card grid responsive, search e filter JS.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, date
from pathlib import Path

import config
from models import HackathonEvent

logger = logging.getLogger(__name__)

_MONTHS_IT = [
    "gen", "feb", "mar", "apr", "mag", "giu",
    "lug", "ago", "set", "ott", "nov", "dic",
]


def _fmt_date_compact(date_str: str) -> str:
    if not (date_str or "").strip():
        return ""
    try:
        ev = HackathonEvent(title="", url="", source="", date_str=date_str)
        d = ev.parsed_date()
        if d:
            return f"{d.day} {_MONTHS_IT[d.month - 1]} {d.year}"
    except Exception:
        pass
    return date_str.strip()[:25]


def _fmt_date_day_month(date_str: str) -> tuple[str, str]:
    if not (date_str or "").strip():
        return ("", "")
    try:
        ev = HackathonEvent(title="", url="", source="", date_str=date_str)
        d = ev.parsed_date()
        if d:
            return (str(d.day), _MONTHS_IT[d.month - 1].upper())
    except Exception:
        pass
    return ("", "")


def _is_upcoming(e: dict) -> bool:
    try:
        ev = HackathonEvent(
            title=e.get("title", ""),
            url=e.get("url", ""),
            source=e.get("source", ""),
            date_str=e.get("date_str", ""),
        )
        return ev.is_upcoming()
    except Exception:
        return True


def _sort_key(e: dict):
    try:
        ev = HackathonEvent(
            title=e.get("title", ""),
            url=e.get("url", ""),
            source=e.get("source", ""),
            date_str=e.get("date_str", ""),
        )
        d = ev.parsed_date()
        return d if d is not None else date(9999, 12, 31)
    except Exception:
        return date(9999, 12, 31)


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# Source badge colors (bg, text)
_SOURCE_COLORS = {
    "web_search": ("#e8f5e9", "#2e7d32"),
    "eventbrite": ("#fff3e0", "#e65100"),
    "eventbrite_web": ("#fff3e0", "#e65100"),
    "luma": ("#e3f2fd", "#1565c0"),
    "devpost": ("#f3e5f5", "#7b1fa2"),
    "taikai": ("#e0f2f1", "#00695c"),
    "innovup": ("#fce4ec", "#c62828"),
    "polihub": ("#e8eaf6", "#283593"),
    "universities": ("#f9fbe7", "#827717"),
    "reddit": ("#fff8e1", "#ff6f00"),
    "google_cse": ("#e0f7fa", "#00838f"),
}
_DEFAULT_SOURCE_COLOR = ("#f5f5f5", "#616161")


def _source_style(source: str) -> tuple[str, str]:
    return _SOURCE_COLORS.get(source.lower(), _DEFAULT_SOURCE_COLOR)


# ---- CSS ----

_CSS = (
    ":root{"
    "--bg:#f5f4f1;--surface:#ffffff;--surface-2:#f8f6f1;"
    "--border:#e2dfd6;--border-strong:#c9c3b6;"
    "--accent:#1c3d5a;--accent-2:#c67a2b;--accent-soft:#eef2f6;"
    "--text:#101418;--text-secondary:#4f5b66;--text-muted:#8a95a1;"
    "--radius:18px;"
    "--shadow-sm:0 1px 2px rgba(16,20,24,.06);"
    "--shadow-lg:0 18px 40px rgba(16,20,24,.12)}"
    "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
    "html{scroll-behavior:smooth}"
    "body{background:"
    "radial-gradient(1200px 400px at 80% -50%,rgba(198,122,43,.18),transparent 60%),"
    "radial-gradient(800px 300px at -10% 20%,rgba(28,61,90,.16),transparent 60%),"
    "var(--bg);"
    "color:var(--text);"
    "font-family:'Manrope','Helvetica Neue',Arial,sans-serif;"
    "line-height:1.6;-webkit-font-smoothing:antialiased}"
    ".container{max-width:960px;margin:0 auto;padding:0 1.5rem}"
    # Hero
    ".hero{position:relative;padding:2.75rem 0 3.25rem;overflow:hidden}"
    ".hero::before{content:'';position:absolute;inset:-40% -10% auto -10%;height:320px;"
    "background:linear-gradient(120deg,rgba(28,61,90,.12),rgba(198,122,43,.16));"
    "filter:blur(10px);z-index:0}"
    ".hero::after{content:'';position:absolute;right:-120px;top:-120px;width:320px;"
    "height:320px;border-radius:50%;border:1px solid rgba(28,61,90,.2);"
    "box-shadow:0 0 0 12px rgba(28,61,90,.04);z-index:0}"
    ".hero-content{position:relative;z-index:1}"
    ".topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:2.5rem}"
    ".brand{display:flex;align-items:center;gap:.65rem}"
    ".brand-badge{width:40px;height:40px;border-radius:12px;"
    "background:linear-gradient(135deg,#132536,#1c3d5a);"
    "color:#fff;display:grid;place-items:center;font-weight:700;letter-spacing:.04em;font-size:.9rem}"
    ".brand-title{font-family:'Playfair Display',Georgia,serif;font-size:1.1rem;letter-spacing:.02em}"
    ".topbar-link{color:var(--accent);text-decoration:none;font-weight:600;font-size:.85rem;"
    "padding:.55rem 1rem;border-radius:999px;border:1px solid var(--border-strong);"
    "background:var(--surface);transition:transform .2s,box-shadow .2s,border-color .2s}"
    ".topbar-link:hover{transform:translateY(-1px);box-shadow:var(--shadow-sm);border-color:var(--accent)}"
    ".hero h1{font-family:'Playfair Display',Georgia,serif;font-size:2.6rem;"
    "letter-spacing:-.01em;line-height:1.1;margin-bottom:.75rem}"
    ".hero-sub{color:var(--text-secondary);font-size:1rem;max-width:560px;margin-bottom:1.75rem}"
    ".hero-actions{display:flex;align-items:center;gap:1rem;flex-wrap:wrap;margin-bottom:0}"
    ".hero-cta{display:inline-flex;align-items:center;gap:.5rem;"
    "background:var(--accent);color:#fff;text-decoration:none;font-weight:600;"
    "padding:.75rem 1.35rem;border-radius:999px;box-shadow:var(--shadow-sm);"
    "transition:transform .2s,box-shadow .2s;font-size:.95rem}"
    ".hero-cta:hover{transform:translateY(-1px);box-shadow:var(--shadow-lg)}"
    ".hero-note{font-size:.85rem;color:var(--text-muted)}"
    ".stats-row{display:flex;align-items:center;gap:1rem;margin-top:2rem;flex-wrap:wrap}"
    ".stat{background:var(--surface);border:1px solid var(--border);"
    "padding:.75rem 1rem;border-radius:12px;min-width:140px;box-shadow:var(--shadow-sm)}"
    ".stat-num{font-size:1.4rem;font-weight:700;line-height:1.2;color:var(--accent)}"
    ".stat-label{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted)}"
    # Toolbar
    ".toolbar-wrap{background:rgba(255,255,255,.75);border-top:1px solid var(--border);"
    "border-bottom:1px solid var(--border);backdrop-filter:blur(8px);"
    "position:sticky;top:0;z-index:50}"
    ".toolbar{display:flex;align-items:center;gap:1rem;padding:.9rem 0;flex-wrap:wrap}"
    ".search-box{position:relative;flex:1;min-width:220px}"
    ".search-icon{position:absolute;left:.8rem;top:50%;transform:translateY(-50%);"
    "width:16px;height:16px;color:var(--text-muted);pointer-events:none}"
    ".search-box input{width:100%;padding:.65rem .9rem .65rem 2.4rem;"
    "border:1px solid var(--border);border-radius:999px;font-family:inherit;"
    "font-size:.9rem;background:var(--surface);color:var(--text);outline:none;"
    "transition:border-color .15s,box-shadow .15s}"
    ".search-box input:focus{border-color:var(--accent);"
    "box-shadow:0 0 0 3px rgba(28,61,90,.12)}"
    ".filter-pills{display:flex;gap:.5rem;flex-wrap:wrap}"
    ".pill{padding:.4rem 1rem;border-radius:999px;border:1px solid var(--border);"
    "background:var(--surface);font-family:inherit;font-size:.8rem;"
    "color:var(--text-secondary);cursor:pointer;transition:all .15s;white-space:nowrap}"
    ".pill:hover{border-color:var(--accent);color:var(--accent)}"
    ".pill.active{background:var(--accent);color:#fff;border-color:var(--accent)}"
    # Grid + Cards
    ".grid{display:flex;flex-direction:column;gap:1rem;padding:2rem 0 2.5rem}"
    ".card{display:flex;gap:1rem;background:var(--surface);"
    "border:1px solid var(--border);border-radius:var(--radius);"
    "padding:1.25rem 1.4rem;box-shadow:var(--shadow-sm);"
    "transition:box-shadow .2s,border-color .2s,transform .2s}"
    ".card:hover{box-shadow:var(--shadow-lg);border-color:var(--border-strong);transform:translateY(-2px)}"
    # Date badge
    ".date-badge{display:flex;flex-direction:column;align-items:center;"
    "justify-content:center;min-width:60px;height:62px;"
    "background:var(--accent-soft);border-radius:14px;flex-shrink:0;border:1px solid var(--border)}"
    ".date-day{font-size:1.35rem;font-weight:700;color:var(--accent);line-height:1.2}"
    ".date-month{font-size:.65rem;font-weight:700;text-transform:uppercase;"
    "letter-spacing:.08em;color:var(--accent)}"
    ".date-tbd{background:var(--surface-2)}"
    ".date-tbd .date-day{color:var(--text-muted);font-size:.85rem}"
    # Card body
    ".card-body{flex:1;min-width:0}"
    ".card-title{font-size:1.05rem;font-weight:700;line-height:1.35;margin-bottom:.4rem}"
    ".card-title a{color:var(--text);text-decoration:none;transition:color .15s}"
    ".card-title a:hover{color:var(--accent)}"
    ".card-meta{display:flex;flex-wrap:wrap;gap:.15rem .85rem;margin-bottom:.5rem}"
    ".meta-item{display:inline-flex;align-items:center;gap:.35rem;"
    "font-size:.82rem;color:var(--text-secondary)}"
    ".meta-item svg{width:14px;height:14px;flex-shrink:0;opacity:.6}"
    ".card-desc{font-size:.85rem;color:var(--text-secondary);line-height:1.6;"
    "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;"
    "overflow:hidden;margin-bottom:.6rem}"
    ".card-footer{display:flex;align-items:center;justify-content:space-between;"
    "gap:.5rem;margin-top:.35rem}"
    ".source-tag{display:inline-block;padding:.2rem .7rem;border-radius:999px;"
    "font-size:.7rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase}"
    ".card-link{font-size:.85rem;font-weight:600;color:var(--accent);"
    "text-decoration:none;transition:opacity .15s}"
    ".card-link:hover{opacity:.75}"
    # Empty + footer
    ".empty-state,.no-results{text-align:center;padding:4rem 1rem;color:var(--text-secondary)}"
    ".empty-icon{font-size:3rem;margin-bottom:1rem}"
    ".empty-state h3{font-size:1.2rem;font-weight:700;color:var(--text);margin-bottom:.6rem}"
    ".empty-state p{font-size:.95rem;line-height:1.6}"
    ".no-results{font-size:.95rem}"
    "footer{padding:1.75rem 0 2.5rem;border-top:1px solid var(--border)}"
    ".footer-inner{display:flex;align-items:center;justify-content:center;"
    "flex-wrap:wrap;gap:.6rem;font-size:.78rem;color:var(--text-muted)}"
    ".footer-inner a{color:var(--accent);text-decoration:none;font-weight:600}"
    ".footer-inner a:hover{text-decoration:underline}"
    ".sep{opacity:.4}"
    "@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}"
    ".card{animation:fadeUp .45s ease both}"
    # Responsive
    "@media(max-width:700px){"
    ".container{padding:0 1.1rem}"
    ".hero{padding:2.25rem 0 2.75rem}"
    ".topbar{flex-direction:column;align-items:flex-start;gap:1rem}"
    ".hero h1{font-size:2rem}"
    ".hero-sub{font-size:.95rem}"
    ".stats-row{gap:.6rem}"
    ".stat{min-width:120px}"
    ".toolbar{gap:.6rem}"
    ".filter-pills{overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none;-ms-overflow-style:none}"
    ".filter-pills::-webkit-scrollbar{display:none}"
    ".card{padding:1.05rem;gap:.8rem}"
    ".date-badge{min-width:50px;height:54px}"
    ".date-day{font-size:1.1rem}"
    ".card-title{font-size:.95rem}}"
)

# ---- JS ----

_JS = (
    "(function(){"
    "var input=document.getElementById('search');"
    "var grid=document.getElementById('grid');"
    "var cards=Array.from(grid.querySelectorAll('.card'));"
    "var pills=document.querySelectorAll('.pill');"
    "var noResults=document.getElementById('no-results');"
    "var activeFilter='all';"
    "function filterDate(f,ds){"
    "if(!ds)return f==='all';"
    "var now=new Date();now.setHours(0,0,0,0);"
    "var d=new Date(ds);"
    "if(f==='week'){var e=new Date(now);e.setDate(e.getDate()+7);return d>=now&&d<=e}"
    "if(f==='month'){var e=new Date(now.getFullYear(),now.getMonth()+1,0);return d>=now&&d<=e}"
    "if(f==='later'){var e=new Date(now.getFullYear(),now.getMonth()+1,1);return d>=e}"
    "return true}"
    "function applyFilters(){"
    "var q=input.value.trim().toLowerCase();"
    "var visible=0;"
    "cards.forEach(function(card){"
    "var text=card.dataset.search||'';"
    "var ds=card.dataset.date||'';"
    "var show=true;"
    "if(q&&text.indexOf(q)===-1)show=false;"
    "if(show&&activeFilter!=='all')show=filterDate(activeFilter,ds);"
    "card.style.display=show?'':'none';"
    "if(show)visible++});"
    "noResults.style.display=(visible===0&&cards.length>0)?'':'none'}"
    "input.addEventListener('input',applyFilters);"
    "pills.forEach(function(pill){"
    "pill.addEventListener('click',function(){"
    "pills.forEach(function(p){p.classList.remove('active')});"
    "pill.classList.add('active');"
    "activeFilter=pill.dataset.filter;"
    "applyFilters()})});"
    "})();"
)


# ---- SVG icons ----

_SVG_SEARCH = '<svg class="search-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/></svg>'
_SVG_PIN = '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"/></svg>'
_SVG_CAL = '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd"/></svg>'


# ---- HTML builder ----

def _build_html(upcoming: list[dict], last_scan: str) -> str:
    event_count = len(upcoming)
    months_set: set[str] = set()
    for e in upcoming:
        _, mon = _fmt_date_day_month(e.get("date_str", ""))
        if mon:
            months_set.add(mon)

    cards_html = _build_cards(upcoming) if upcoming else _build_empty()
    evt_word = "eventi" if event_count != 1 else "evento"
    mon_word = "mesi" if len(months_set) != 1 else "mese"
    mon_count = str(len(months_set)) if months_set else "\u2014"

    html = (
        '<!DOCTYPE html>\n<html lang="it">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<meta name="description" content="{event_count} hackathon in programma a Milano e dintorni.">\n'
        '<meta property="og:title" content="Hackathon Milano">\n'
        f'<meta property="og:description" content="{event_count} hackathon in programma a Milano">\n'
        '<meta property="og:type" content="website">\n'
        '<title>Hackathon Milano</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Playfair+Display:wght@500;600;700&display=swap" rel="stylesheet">\n'
        f'<style>{_CSS}</style>\n'
        '</head>\n<body>\n\n'
        # Hero
        '<header class="hero"><div class="container"><div class="hero-content">\n'
        '  <div class="topbar">\n'
        '    <div class="brand">\n'
        '      <div class="brand-badge">HM</div>\n'
        '      <div class="brand-title">Hackathon Milano</div>\n'
        '    </div>\n'
        '    <a class="topbar-link" href="https://github.com/federicoogallo/Hackathon-MI" target="_blank" rel="noopener">Segui su GitHub</a>\n'
        '  </div>\n'
        '  <h1>Il calendario degli hackathon milanesi, curato ogni giorno.</h1>\n'
        '  <p class="hero-sub">Un hub essenziale con gli eventi reali a Milano. Aggiornato automaticamente e filtrato con AI per eliminare il rumore.</p>\n'
        '  <div class="hero-actions">\n'
        '    <a class="hero-cta" href="#grid">Scopri gli eventi</a>\n'
        '    <span class="hero-note">Ultimi aggiornamenti ogni 24 ore</span>\n'
        '  </div>\n'
        '  <div class="stats-row">\n'
        f'    <div class="stat"><span class="stat-num">{event_count}</span><span class="stat-label">{evt_word}</span></div>\n'
        f'    <div class="stat"><span class="stat-num">{mon_count}</span><span class="stat-label">{mon_word}</span></div>\n'
        '    <div class="stat"><span class="stat-num">24h</span><span class="stat-label">refresh</span></div>\n'
        '  </div>\n'
        '</div></div></header>\n\n'
        # Toolbar
        '<section class="toolbar-wrap"><div class="container toolbar">\n'
        f'  <div class="search-box">{_SVG_SEARCH}<input type="text" id="search" placeholder="Cerca hackathon..." autocomplete="off"></div>\n'
        '  <div class="filter-pills" id="filters">\n'
        '    <button class="pill active" data-filter="all">Tutti</button>\n'
        '    <button class="pill" data-filter="week">Questa settimana</button>\n'
        '    <button class="pill" data-filter="month">Questo mese</button>\n'
        '    <button class="pill" data-filter="later">Prossimi mesi</button>\n'
        '  </div>\n'
        '</div></section>\n\n'
        # Main
        '<main class="container"><div class="grid" id="grid">\n'
        f'{cards_html}\n'
        '</div>\n'
        '<p class="no-results" id="no-results" style="display:none">Nessun risultato per questa ricerca.</p>\n'
        '</main>\n\n'
        # Footer
        '<footer class="container"><div class="footer-inner">\n'
        f'  <span>Ultimo aggiornamento: {_escape(last_scan)}</span>\n'
        '  <span class="sep">&middot;</span>\n'
        '  <a href="https://github.com/federicoogallo/Hackathon-MI" target="_blank" rel="noopener">GitHub</a>\n'
        '  <span class="sep">&middot;</span>\n'
        '  <span>Dati raccolti automaticamente e verificati con AI</span>\n'
        '</div></footer>\n\n'
        f'<script>{_JS}</script>\n'
        '</body>\n</html>'
    )
    return html


def _build_cards(events: list[dict]) -> str:
    parts: list[str] = []
    for e in events:
        title = _escape((e.get("title") or "Senza titolo").strip())
        url = _escape(e.get("url") or "#")
        location = _escape((e.get("location") or "Milano").strip())
        source = (e.get("source") or "").strip()
        date_str = e.get("date_str", "")

        day, month = _fmt_date_day_month(date_str)
        date_compact = _fmt_date_compact(date_str)
        date_iso = ""
        try:
            ev = HackathonEvent(title="", url="", source="", date_str=date_str)
            d = ev.parsed_date()
            if d:
                date_iso = d.isoformat()
        except Exception:
            pass

        desc_raw = (e.get("description") or "").strip().replace("\n", " ")
        if len(desc_raw) > 200:
            desc_raw = desc_raw[:200].rsplit(" ", 1)[0] + "..."
        desc = _escape(desc_raw)

        bg, fg = _source_style(source)
        source_esc = _escape(source)

        if day and month:
            badge = f'<div class="date-badge"><span class="date-day">{day}</span><span class="date-month">{month}</span></div>'
        else:
            badge = '<div class="date-badge date-tbd"><span class="date-day">TBD</span><span class="date-month">&nbsp;</span></div>'

        meta = []
        if location:
            meta.append(f'<span class="meta-item">{_SVG_PIN}{location}</span>')
        if date_compact:
            meta.append(f'<span class="meta-item">{_SVG_CAL}{_escape(date_compact)}</span>')
        meta_html = "".join(meta)

        desc_html = f'<p class="card-desc">{desc}</p>' if desc else ""
        search_blob = _escape(f"{title} {desc} {location} {source_esc}".lower())

        parts.append(
            f'<article class="card" data-date="{date_iso}" data-search="{search_blob}">'
            f'<div class="card-left">{badge}</div>'
            f'<div class="card-body">'
            f'<h2 class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>'
            f'<div class="card-meta">{meta_html}</div>'
            f'{desc_html}'
            f'<div class="card-footer">'
            f'<span class="source-tag" style="background:{bg};color:{fg}">{source_esc}</span>'
            f'<a href="{url}" class="card-link" target="_blank" rel="noopener">Dettagli \u2192</a>'
            f'</div></div></article>'
        )
    return "\n".join(parts)


def _build_empty() -> str:
    return (
        '<div class="empty-state">'
        '<div class="empty-icon">\U0001f50d</div>'
        '<h3>Nessun hackathon in programma</h3>'
        '<p>Non ci sono hackathon futuri confermati a Milano al momento.<br>'
        'La lista si aggiorna automaticamente ogni giorno alle 12:00.</p>'
        '</div>'
    )


# ---- Generator ----

def generate_html(events_path=None, output_path=None):
    """Legge events.json e scrive docs/index.html con gli hackathon futuri."""
    events_path = events_path or config.EVENTS_FILE
    output_path = output_path or (config.BASE_DIR / "docs" / "index.html")

    all_events: list[dict] = []
    last_check = ""
    if events_path.exists():
        try:
            data = json.loads(events_path.read_text(encoding="utf-8"))
            raw = data.get("events", [])
            all_events = list(raw.values()) if isinstance(raw, dict) else raw
            last_check = data.get("last_check", "")
        except Exception as exc:
            logger.warning("Impossibile leggere events.json per HTML: %s", exc)

    confirmed = [e for e in all_events if e.get("is_hackathon")]
    upcoming = [e for e in confirmed if _is_upcoming(e)]
    upcoming.sort(key=_sort_key)

    now_str = datetime.now().strftime("%d %b %Y, %H:%M")
    last_scan = now_str
    if last_check:
        try:
            dt = datetime.fromisoformat(last_check)
            last_scan = dt.strftime("%d %b %Y alle %H:%M")
        except Exception:
            pass

    html = _build_html(upcoming, last_scan)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("HTML generato: %s (%d eventi)", output_path, len(upcoming))
    return output_path
