"""
Genera le pagine statiche del monitor (docs/index.html + docs/review.html).

Architettura UI: il markup e' pre-renderizzato qui (SSG), lo stile e le
interazioni vivono in asset statici versionati (docs/assets/):
- site.css  — design tokens + layout (dark premium, ispirazione meuze.ai)
- site.js   — micro-interazioni (materialize title, reveal, count-up, filtri)
- globe.js  — intro orbitale WebGL (three.js): dal mondo visto dall'alto a Milano

Gli asset non vengono riscritti dalla pipeline: qui si genera solo l'HTML,
con cache-busting basato sull'hash degli asset. Fallback totale senza JS:
contenuto visibile, intro collassata.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, date
from pathlib import Path
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

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


def _issue_base_url() -> str:
    repo_url = str(getattr(config, "GITHUB_REPO_URL", "") or "").strip().rstrip("/")
    if not repo_url:
        return ""
    return f"{repo_url}/issues/new"


def _issue_url(event: dict, mode: str) -> str:
    """Crea URL issue precompilata per conferma o dubbio evento."""
    base = _issue_base_url()
    if not base:
        return "#"

    title = (event.get("title") or "Senza titolo").strip()
    url = (event.get("url") or "").strip()
    source = (event.get("source") or "").strip()
    location = (event.get("location") or "").strip()
    date_str = (event.get("date_str") or "").strip()
    confidence = int(round(float(event.get("confidence") or 0.0) * 100))

    if mode == "confirmed_ok":
        issue_title = f"[VALUTAZIONE OK] {title}"
        kind = "Conferma evento sicuro"
    elif mode == "confirmed_doubt":
        issue_title = f"[DUBBIO] {title}"
        kind = "Segnalazione dubbio su evento pubblicato"
    elif mode == "review_ok":
        issue_title = f"[REVIEW OK] {title}"
        kind = "Conferma candidato incerto"
    else:
        issue_title = f"[REVIEW DUBBIO] {title}"
        kind = "Segnalazione candidato incerto"

    body = (
        f"Tipo valutazione: {kind}\n"
        f"Titolo: {title}\n"
        f"URL: {url}\n"
        f"Source: {source}\n"
        f"Location: {location or '(non specificata)'}\n"
        f"Data: {date_str or 'TBD'}\n"
        f"Confidence AI: {confidence}%\n\n"
        "Note utente:\n"
        "- \n\n"
        "Nota: gli utenti non eliminano eventi direttamente; la decisione resta ai maintainer.\n"
    )

    return f"{base}?title={quote_plus(issue_title)}&body={quote_plus(body)}"


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


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _review_count() -> int:
    data = _read_json(config.REVIEW_QUEUE_FILE)
    candidates = data.get("candidates", [])
    return len(candidates) if isinstance(candidates, list) else 0


def _parse_report_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _scan_status(events_last_check: str = "") -> tuple[str, int]:
    data = _read_json(config.DATA_DIR / "last_report.json")
    report_dt = _parse_report_datetime(str(data.get("date") or ""))
    events_dt = _parse_report_datetime(events_last_check)
    if report_dt and events_dt and report_dt.date() < events_dt.date():
        return "completed", 0

    status = data.get("status") or "completed"
    failures = data.get("failed_collectors", [])
    if not isinstance(failures, list):
        failures = []
    return str(status), len(failures)


def _scan_status_label(scan_status: str, collector_failures: int) -> str:
    if scan_status == "completed" and collector_failures == 0:
        return "OK"
    if scan_status == "llm_failed_preserved":
        return "LLM non attivo"
    return "Da controllare"


def _asset_version() -> str:
    """Hash degli asset UI per cache-busting nei link."""
    assets_dir = config.BASE_DIR / "docs" / "assets"
    h = hashlib.sha1()
    found = False
    try:
        for name in ("site.css", "site.js", "globe.js"):
            fp = assets_dir / name
            if fp.exists():
                h.update(fp.read_bytes())
                found = True
    except Exception:
        return "1"
    return h.hexdigest()[:10] if found else "1"


# ---- SVG icons ----

_SVG_SEARCH = '<svg class="search-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/></svg>'
_SVG_PIN = '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"/></svg>'
_SVG_CAL = '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd"/></svg>'
_SVG_ARROW = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8h10M9 4l4 4-4 4"/></svg>'
_SVG_LOGO = '<svg viewBox="0 0 24 24"><path d="M12 3 3.8 8.2 12 13.4l8.2-5.2L12 3Z"/><path d="m3.8 12.2 8.2 5.2 8.2-5.2"/><path d="m3.8 16.2 8.2 5.2 8.2-5.2"/></svg>'

_FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@400;500;600;700;800;900&'
    'family=JetBrains+Mono:wght@400;500;600;700;800&'
    'family=Space+Grotesk:wght@500;600;700&'
    'family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">\n'
)


# ---- card / block builders ----

def _build_elite_cards(events: list[dict]) -> str:
    parts: list[str] = []
    for e in events:
        title = _escape((e.get("title") or "Senza titolo").strip())
        url = _escape(e.get("url") or "#")
        location = _escape((e.get("location") or "Milano").strip())
        source = _escape((e.get("source") or "").strip())
        date_str = e.get("date_str", "")
        review_status = (e.get("review_status") or "ai_verified").strip()
        confidence = float(e.get("confidence") or 0.0)
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
        if len(desc_raw) > 210:
            desc_raw = desc_raw[:210].rsplit(" ", 1)[0] + "..."
        desc = _escape(desc_raw)
        issue_ok_url = _escape(_issue_url(e, "confirmed_ok"))
        issue_doubt_url = _escape(_issue_url(e, "confirmed_doubt"))
        date_badge = (
            f'<div class="date"><div><strong>{day}</strong><span>{month}</span></div></div>'
            if day and month
            else '<div class="date"><div><strong>TBD</strong><span>DATA</span></div></div>'
        )
        chips = []
        if review_status == "manual_approved":
            chips.append('<span class="chip manual">Verifica manuale</span>')
        elif confidence > 0:
            chips.append(f'<span class="chip ai">AI {int(round(confidence * 100))}%</span>')
        if not date_iso:
            chips.append('<span class="chip tbd">Data da confermare</span>')
        chips_html = f'<div class="chips">{"".join(chips)}</div>' if chips else ""
        desc_html = f'<p class="card-desc">{desc}</p>' if desc else ""
        search_blob = _escape(f"{title} {desc} {location} {source}".lower())
        parts.append(
            f'<article class="card" data-date="{date_iso}" data-search="{search_blob}" data-reveal>'
            f'{date_badge}'
            '<div class="card-body">'
            f'<h3 class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>'
            '<div class="card-meta">'
            f'<span>{_SVG_PIN}{location}</span>'
            + (f'<span>{_SVG_CAL}{_escape(date_compact)}</span>' if date_compact else '')
            + '</div>'
            f'{chips_html}'
            f'{desc_html}'
            '<div class="card-foot">'
            f'<span class="source">{source}</span>'
            '<div class="actions">'
            f'<a href="{issue_ok_url}" class="act" target="_blank" rel="noopener">Valuta OK</a>'
            f'<a href="{issue_doubt_url}" class="act" target="_blank" rel="noopener">Segnala dubbio</a>'
            f'<a href="{url}" class="act go" target="_blank" rel="noopener">Vedi evento{_SVG_ARROW}</a>'
            '</div></div></div></article>'
        )
    return "\n".join(parts)


def _build_empty() -> str:
    return (
        '<div class="empty" data-reveal>'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M7 3v3M17 3v3M4.5 9h15M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/>'
        '<path d="m9 14 2 2 4-4"/></svg>'
        '<h3>Nessun hackathon in programma</h3>'
        '<p>Non ci sono hackathon futuri confermati a Milano al momento.<br>'
        'La lista si aggiorna ogni giorno automaticamente.</p>'
        '</div>'
    )


def _build_review_cards(candidates: list[dict]) -> str:
    if not candidates:
        return (
            '<div class="empty" data-reveal>'
            '<h3>Nessun candidato in revisione</h3>'
            '<p>La coda si popola solo quando il filtro AI non ha confidenza sufficiente.</p>'
            '</div>'
        )

    parts: list[str] = []
    for item in candidates:
        title = _escape((item.get("title") or "Senza titolo").strip())
        url = _escape(item.get("url") or "#")
        source = _escape(item.get("source") or "")
        reason = _escape(item.get("review_reason") or "Motivazione non disponibile")
        candidate_id = _escape(str(item.get("id", ""))[:12])
        confidence = int(round(float(item.get("confidence") or 0.0) * 100))
        location = _escape(item.get("location") or "Milano")
        date_str = _escape(_fmt_date_compact(item.get("date_str", "")) or "TBD")
        issue_ok_url = _escape(_issue_url(item, "review_ok"))
        issue_doubt_url = _escape(_issue_url(item, "review_doubt"))
        parts.append(
            '<article class="review-card" data-reveal>'
            '<div class="review-head"><div>'
            f'<div class="review-id">{candidate_id}</div>'
            f'<h2 class="review-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>'
            f'<div class="card-meta"><span class="source">{source}</span>'
            f'<span>{_SVG_PIN}{location}</span><span>{_SVG_CAL}{date_str}</span></div>'
            '</div>'
            f'<span class="chip ai">AI {confidence}%</span>'
            '</div>'
            f'<p class="review-reason">{reason}</p>'
            '<div class="actions">'
            f'<a href="{issue_ok_url}" class="act" target="_blank" rel="noopener">Valuta OK</a>'
            f'<a href="{issue_doubt_url}" class="act" target="_blank" rel="noopener">Segnala dubbio</a>'
            f'<a href="{url}" class="act go" target="_blank" rel="noopener">Vedi evento{_SVG_ARROW}</a>'
            '</div>'
            '</article>'
        )
    return "\n".join(parts)


def _head(title: str, description: str, body_class: str, asset_v: str) -> str:
    return (
        '<!DOCTYPE html>\n<html lang="it">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<meta name="description" content="{_escape(description)}">\n'
        f'<meta property="og:title" content="{_escape(title)}">\n'
        f'<meta property="og:description" content="{_escape(description)}">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:image" content="hero-hackathon-milano.png">\n'
        '<meta name="theme-color" content="#070a11">\n'
        f'<title>{_escape(title)}</title>\n'
        f'{_FONTS_LINK}'
        f'<link rel="stylesheet" href="assets/site.css?v={asset_v}">\n'
        f'</head>\n<body class="{body_class}">\n'
        '<div class="scroll-progress" id="scroll-progress"></div>\n'
    )


def _nav(brand_title: str, brand_sub: str, brand_href: str, actions_html: str) -> str:
    return (
        '<nav class="nav-fixed" id="nav" aria-label="Navigazione principale">'
        '<div class="container"><div class="nav">'
        f'<a class="brand" href="{brand_href}"><span class="brand-mark">{_SVG_LOGO}</span>'
        f'<span><b>{brand_title}</b><span>{brand_sub}</span></span></a>'
        f'<div class="nav-actions">{actions_html}</div>'
        '</div></div></nav>\n'
    )


# Attiva l'intro in modo sincrono (prima di site.js) per evitare che gli
# observer dell'hero scattino mentre l'intro non e' ancora stata espansa
# da globe.js (import asincrono). globe.js rimuove la classe in caso di
# errore dati/CDN, ripristinando il layout senza intro.
_INTRO_BOOT = (
    "<script>(function(){try{"
    "if(location.hash)return;"
    "if(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)return;"
    "var c=document.createElement('canvas');"
    "if(!(window.WebGLRenderingContext&&(c.getContext('webgl')||c.getContext('experimental-webgl'))))return;"
    "document.documentElement.classList.add('has-intro');"
    "}catch(e){}})();</script>\n"
)


def _intro_section() -> str:
    """Intro orbitale (attivata da globe.js solo se WebGL + motion ok)."""
    return (
        '<section class="intro" id="intro" aria-label="Introduzione: dal mondo a Milano">\n'
        '<div class="intro-sticky">\n'
        '<canvas id="globe-canvas" aria-hidden="true"></canvas>\n'
        '<div class="intro-ui">\n'
        '<div class="intro-caption mono" id="intro-caption">Low earth orbit</div>\n'
        '<div class="intro-coords mono" id="intro-coords">45.4642&deg; N &mdash; 9.1900&deg; E</div>\n'
        '<div class="intro-label" id="intro-label"><b>MILANO</b><span>45.4642&deg; N / 9.1900&deg; E</span></div>\n'
        '<div class="intro-hint mono" id="intro-hint">Scroll</div>\n'
        '<button class="intro-skip mono" id="intro-skip" type="button">Salta l\'intro &darr;</button>\n'
        '</div>\n'
        '<div class="intro-fade"></div>\n'
        '</div>\n'
        '</section>\n'
    )


def _build_html(
    upcoming: list[dict],
    last_scan: str,
    review_count: int = 0,
    scan_status: str = "completed",
    collector_failures: int = 0,
) -> str:
    event_count = len(upcoming)
    months_set: set[str] = set()
    for e in upcoming:
        _, mon = _fmt_date_day_month(e.get("date_str", ""))
        if mon:
            months_set.add(mon)

    cards_html = _build_elite_cards(upcoming) if upcoming else _build_empty()
    evt_word = "eventi" if event_count != 1 else "evento"
    mon_word = "mesi" if len(months_set) != 1 else "mese"
    mon_count = len(months_set) if months_set else 0
    status_label = _scan_status_label(scan_status, collector_failures)
    status_dot = "ops-dot" if status_label == "OK" else "ops-dot warn"
    asset_v = _asset_version()

    return (
        _head(
            "Hackathon Milano",
            f"{event_count} hackathon in programma a Milano e dintorni.",
            "elite-shell",
            asset_v,
        )
        + _INTRO_BOOT
        + _nav(
            "Hackathon Milano",
            "Milano intelligence layer",
            "#top",
            '<a class="btn btn-ghost nav-secondary" href="review.html">Candidati in review</a>'
            f'<a class="btn btn-primary" href="#events">{_SVG_ARROW}Eventi</a>',
        )
        + _intro_section()
        + '<header class="hero" id="top">\n'
        '<canvas class="hero-canvas" id="hero-canvas" aria-hidden="true"></canvas>\n'
        '<div class="container">\n'
        '<div class="hero-grid">\n'
        '<div class="hero-copy">\n'
        '<div class="eyebrow"><span class="dot"></span>Live AI scouting system</div>\n'
        '<h1 class="hero-title" id="hero-title" aria-label="Hackathon Milano">'
        '<span class="line"><span class="materialize" data-materialize="Hackathon">Hackathon</span></span>'
        '<span class="line title-accent">Milano</span></h1>\n'
        '<p class="hero-sub">Un prodotto editoriale e operativo per leggere il territorio: '
        'raccoglie segnali pubblici, comprime i duplicati, assegna un livello di fiducia e '
        'pubblica solo opportunita verificabili.</p>\n'
        '<div class="hero-cta">'
        '<a class="btn btn-primary" href="#events">Apri il deck eventi</a>'
        '<a class="btn btn-ghost" href="https://github.com/federicoogallo/Hackathon-MI" target="_blank" rel="noopener">GitHub</a>'
        '</div>\n'
        f'<div class="hero-status"><span class="{status_dot}"></span>'
        f'<strong>{_escape(status_label)}</strong><span>Ultimo scan: {_escape(last_scan)}</span></div>\n'
        '<div class="hero-metrics" aria-label="Metriche monitor">\n'
        f'<div class="metric"><strong data-count="{event_count}">{event_count}</strong><span>{evt_word} verificati</span></div>\n'
        f'<div class="metric"><strong data-count="{mon_count}">{mon_count}</strong><span>{mon_word} coperti</span></div>\n'
        '<div class="metric"><strong data-count="24" data-suffix="h">24h</strong><span>refresh</span></div>\n'
        '</div>\n'
        '</div>\n'
        '<aside class="stage" aria-hidden="true">\n'
        '<div class="stage-orbit"></div>\n'
        '<div class="panel">\n'
        '<div class="panel-head"><span class="win-dots"><i></i><i></i><i></i></span>'
        '<span class="tag">monitor // live</span></div>\n'
        '<div class="pipe">\n'
        '<div class="pipe-row"><span class="lead"><i></i>Collect</span><span class="val">fonti pubbliche</span></div>\n'
        '<div class="pipe-row"><span class="lead"><i></i>Dedupe</span><span class="val">cluster simili</span></div>\n'
        '<div class="pipe-row"><span class="lead"><i></i>AI score</span><span class="val">fiducia e contesto</span></div>\n'
        '<div class="pipe-row"><span class="lead"><i></i>Publish</span><span class="val">output verificato</span></div>\n'
        '</div>\n'
        '<div class="panel-foot">'
        '<div><span>scope</span><strong>Milano</strong></div>'
        f'<div><span>in review</span><strong>{review_count}</strong></div>'
        f'<div><span>errori</span><strong>{collector_failures}</strong></div>'
        '</div>\n'
        '</div>\n'
        '</aside>\n'
        '</div>\n'
        '</div>\n'
        '</header>\n'
        '<section class="marquee" aria-hidden="true"><div class="marquee-track">'
        + (
            '<span>PUBLIC SOURCES</span><b>/</b><span>DEDUPLICATION</span><b>/</b>'
            '<span>AI CONFIDENCE</span><b>/</b><span>MANUAL REVIEW</span><b>/</b>'
            '<span>GITHUB PAGES OUTPUT</span><b>/</b>'
        ) * 2
        + '</div></section>\n'
        '<section class="section system" id="system">\n'
        '<div class="container">\n'
        '<div class="sys-head">\n'
        '<div data-reveal><span class="kicker">01 / Come funziona</span>\n'
        '<h2 class="h2">Dal rumore pubblico a un calendario <em>ad alta fiducia</em>.</h2></div>\n'
        '<p class="lead-p" data-reveal data-delay="80">Il motore trasforma segnali pubblici dispersi '
        'in una mappa operativa: fonti, deduplica, scoring AI e review umana convergono '
        'in un output pronto da usare.</p>\n'
        '</div>\n'
        '<div class="rail" data-reveal>\n'
        '<div class="rail-line" aria-hidden="true"><i id="rail-fill"></i></div>\n'
        '<ol class="rail-steps">\n'
        '<li class="rail-step" data-step><code>01</code><h3>Collect</h3><p>Community, piattaforme eventi e ricerca web entrano nel radar.</p></li>\n'
        '<li class="rail-step" data-step><code>02</code><h3>Dedupe</h3><p>I record sovrapposti diventano un solo candidato leggibile.</p></li>\n'
        '<li class="rail-step" data-step><code>03</code><h3>AI score</h3><p>Luogo, data, formato e fonte generano un livello di fiducia.</p></li>\n'
        '<li class="rail-step" data-step><code>04</code><h3>Review</h3><p>I casi incerti passano a controllo umano, fuori dalla pagina pubblica.</p></li>\n'
        '<li class="rail-step" data-step><code>05</code><h3>Publish</h3><p>Gli eventi verificati diventano output stabile su GitHub Pages.</p></li>\n'
        '</ol>\n'
        '</div>\n'
        '<div class="sys-foot" data-reveal>'
        '<span><b>28</b> fonti pubbliche</span>'
        '<span><b>4</b> livelli di dedup</span>'
        '<span><b>0.7</b> soglia di fiducia AI</span>'
        '<span><b>24h</b> ciclo di refresh</span>'
        '</div>\n'
        '</div>\n'
        '</section>\n'
        '<main class="section" id="events">\n'
        '<div class="container">\n'
        '<div class="events-head">\n'
        '<div data-reveal><span class="kicker">02 / Event deck</span>'
        '<h2 class="h2">Output finale, pronto da <em>scansionare</em>.</h2>'
        '<p class="lead-p" style="margin-top:16px">Gli eventi sono presentati come un deck operativo: pochi segnali forti, '
        'fonte visibile, qualita esplicita e azioni rapide per confermare o aprire dubbi.</p></div>\n'
        '<div class="stats" data-reveal data-delay="80">'
        f'<div class="stat"><strong data-count="{event_count}">{event_count}</strong><span>{evt_word}</span></div>'
        f'<div class="stat"><strong data-count="{mon_count}">{mon_count}</strong><span>{mon_word}</span></div>'
        f'<div class="stat"><strong data-count="{review_count}">{review_count}</strong><span>in review</span></div>'
        '</div>\n'
        '</div>\n'
        '<div class="toolbar" aria-label="Filtri eventi">\n'
        f'<div class="search"><label class="sr-only" for="search">Cerca eventi</label>{_SVG_SEARCH}'
        '<input type="text" id="search" placeholder="Cerca hackathon, fonte o luogo..." autocomplete="off"></div>\n'
        '<div class="pills" id="filters">'
        '<button class="pill active" data-filter="all">Tutti</button>'
        '<button class="pill" data-filter="week">Settimana</button>'
        '<button class="pill" data-filter="month">Mese</button>'
        '<button class="pill" data-filter="later">Prossimi</button></div>\n'
        '</div>\n'
        f'<div class="deck-head"><strong>Prossimi eventi verificati</strong><span id="count-label">{event_count} {evt_word}</span></div>\n'
        f'<div class="grid" id="grid">{cards_html}</div>\n'
        '<p class="no-results" id="no-results" style="display:none">Nessun risultato trovato.</p>\n'
        '</div>\n'
        '</main>\n'
        '<footer><div class="container"><div class="footer-inner">'
        '<div class="footer-brand"><b>Hackathon Milano</b>Dati raccolti automaticamente con AI</div>'
        f'<div class="footer-mid">aggiornato {_escape(last_scan)}</div>'
        '<div class="footer-links">'
        '<a href="https://github.com/federicoogallo/Hackathon-MI" target="_blank" rel="noopener">GitHub</a>'
        '<a href="review.html">Review</a><a href="#top">Top</a></div>'
        '</div></div></footer>\n'
        f'<script src="assets/site.js?v={asset_v}" defer></script>\n'
        f'<script type="module" src="assets/globe.js?v={asset_v}"></script>\n'
        '</body>\n</html>'
    )


def _build_review_html(candidates: list[dict], last_scan: str) -> str:
    cards = _build_review_cards(candidates)
    count = len(candidates)
    asset_v = _asset_version()
    return (
        _head(
            "Review queue - Hackathon Milano",
            f"{count} candidati hackathon da rivedere.",
            "elite-shell review-page",
            asset_v,
        )
        + _nav(
            "Review queue",
            "Manual confidence control",
            "index.html",
            '<a class="btn btn-primary" href="index.html">Eventi confermati</a>',
        )
        + '<header class="hero" id="top"><canvas class="hero-canvas" id="hero-canvas" aria-hidden="true"></canvas>\n'
        '<div class="container">\n'
        '<div class="hero-grid"><div class="hero-copy">\n'
        '<div class="eyebrow"><span class="dot"></span>Manual review</div>\n'
        '<h1 class="hero-title" aria-label="Review queue">'
        '<span class="line"><span class="materialize" data-materialize="Review">Review</span></span>'
        '<span class="line title-accent">queue</span></h1>\n'
        f'<p class="hero-sub">{count} eventi hanno abbastanza segnale per una revisione umana. '
        'Gli utenti possono solo aprire issue di conferma o dubbio: la rimozione resta ai maintainer.</p>\n'
        f'<div class="hero-status"><span class="ops-dot"></span><strong>{count}</strong>'
        f'<span>Aggiornato: {_escape(last_scan)}</span></div>\n'
        '</div></div>\n'
        '</div></header>\n'
        '<main class="section" id="events"><div class="container">\n'
        '<div class="deck-head" data-reveal><strong>Da rivedere</strong><span>Manual layer</span></div>\n'
        f'<div class="review-list">{cards}</div>\n'
        '</div></main>\n'
        '<footer><div class="container"><div class="footer-inner">'
        '<div class="footer-brand"><b>Hackathon Milano</b>Review queue generata dalla pipeline</div>'
        '<div class="footer-mid"></div>'
        '<div class="footer-links"><a href="index.html">Calendario</a><a href="#top">Top</a></div>'
        '</div></div></footer>\n'
        f'<script src="assets/site.js?v={asset_v}" defer></script>\n'
        '</body>\n</html>'
    )


# ---- Generator ----

def generate_html(events_path=None, output_path=None, review_output_path=None):
    """Legge events.json e scrive docs/index.html con gli hackathon futuri."""
    events_path = events_path or config.EVENTS_FILE
    output_path = output_path or (config.BASE_DIR / "docs" / "index.html")
    review_output_path = review_output_path or (config.BASE_DIR / "docs" / "review.html")

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

    now_str = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d %b %Y, %H:%M")
    last_scan = now_str
    if last_check:
        try:
            dt = datetime.fromisoformat(last_check)
            last_scan = dt.strftime("%d %b %Y alle %H:%M")
        except Exception:
            pass

    review_count = _review_count()
    scan_status, collector_failures = _scan_status(last_check)
    html = _build_html(
        upcoming,
        last_scan,
        review_count=review_count,
        scan_status=scan_status,
        collector_failures=collector_failures,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    review_candidates = _read_json(config.REVIEW_QUEUE_FILE).get("candidates", [])
    if not isinstance(review_candidates, list):
        review_candidates = []
    review_output_path.parent.mkdir(parents=True, exist_ok=True)
    review_output_path.write_text(
        _build_review_html(review_candidates, last_scan),
        encoding="utf-8",
    )
    logger.info("HTML generato: %s (%d eventi)", output_path, len(upcoming))
    return output_path
