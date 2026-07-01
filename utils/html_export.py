"""
Genera una pagina HTML statica con tutti gli hackathon futuri confermati.

Output: docs/index.html  servita via GitHub Pages.
Viene rigenerata ad ogni run della pipeline.
Design: light theme, DM Sans font, card grid responsive, search e filter JS.
"""

from __future__ import annotations

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


# ---- CSS ----

_CSS = (
    ":root{"
    "--bg:#f7f6f2;"
    "--surface:#ffffff;"
    "--surface-2:#f2f1ec;"
    "--border:#e8e5de;"
    "--border-strong:#d0ccc2;"
    "--dark:#0b0f19;"
    "--dark-2:#131929;"
    "--dark-3:#1e2d42;"
    "--accent:#2563eb;"
    "--accent-hover:#1d4ed8;"
    "--gold:#d97706;"
    "--text:#0f1318;"
    "--text-secondary:#52606d;"
    "--text-muted:#9aa5b1;"
    "--radius:8px;"
    "--shadow:0 1px 3px rgba(0,0,0,.06),0 4px 16px rgba(0,0,0,.06);"
    "--shadow-hover:0 8px 30px rgba(0,0,0,.12),0 2px 8px rgba(0,0,0,.08);"
    "--shadow-dark:0 24px 60px rgba(0,0,0,.3)}"
    "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
    "html{scroll-behavior:smooth;scrollbar-color:var(--border-strong) var(--bg);scrollbar-width:thin}"
    "::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--border-strong);border-radius:99px}"
    "::selection{background:#dbeafe;color:var(--accent)}"
    "body{background:var(--bg);color:var(--text);"
    "font-family:'DM Sans','Helvetica Neue',Arial,sans-serif;"
    "line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh}"
    ".container{max-width:1024px;margin:0 auto;padding:0 1.5rem}"
    # Hero — dark section
    ".hero{position:relative;background:var(--dark);overflow:hidden;"
    "padding:0;border-bottom:1px solid rgba(255,255,255,.06)}"
    ".hero-bg{position:absolute;inset:0;z-index:0;"
    "background:linear-gradient(135deg,#0b0f19 0%,#132033 58%,#20344f 100%)}"
    ".hero-grid{position:absolute;inset:0;z-index:0;opacity:.26;"
    "background-image:linear-gradient(rgba(255,255,255,.08) 1px,transparent 1px),"
    "linear-gradient(90deg,rgba(255,255,255,.08) 1px,transparent 1px);"
    "background-size:44px 44px;mask-image:linear-gradient(to bottom,#000,transparent 85%)}"
    ".hero-content{position:relative;z-index:1}"
    ".topbar{display:flex;align-items:center;justify-content:space-between;"
    "padding:1.25rem 0;border-bottom:1px solid rgba(255,255,255,.07)}"
    ".brand{display:flex;align-items:center;gap:.75rem}"
    ".brand-mark{width:36px;height:36px;border-radius:8px;"
    "background:linear-gradient(135deg,var(--accent),#1d4ed8);"
    "display:grid;place-items:center;flex-shrink:0}"
    ".brand-mark svg{width:18px;height:18px;fill:none;stroke:#fff;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}"
    ".brand-name{font-size:.9rem;font-weight:600;color:#fff;letter-spacing:.01em}"
    ".brand-city{font-size:.75rem;color:rgba(255,255,255,.4);margin-top:-.1rem}"
    ".topbar-link{display:inline-flex;align-items:center;gap:.4rem;color:rgba(255,255,255,.7);"
    "text-decoration:none;font-weight:500;font-size:.82rem;"
    "padding:.5rem .9rem;border-radius:8px;"
    "border:1px solid rgba(255,255,255,.12);"
    "background:rgba(255,255,255,.05);"
    "transition:all .2s;backdrop-filter:blur(4px)}"
    ".topbar-link svg{width:14px;height:14px;opacity:.7}"
    ".topbar-link:hover{color:#fff;border-color:rgba(255,255,255,.25);background:rgba(255,255,255,.1)}"
    ".hero-body{padding:4rem 0 4.5rem}"
    ".hero-eyebrow{display:inline-flex;align-items:center;gap:.5rem;"
    "font-size:.75rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;"
    "color:var(--accent);margin-bottom:1.25rem}"
    ".hero-eyebrow span{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--accent);animation:pulse 2s ease infinite}"
    "@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}"
    ".hero h1{font-family:'DM Serif Display',Georgia,serif;font-size:3.25rem;"
    "letter-spacing:-.025em;line-height:1.06;color:#fff;margin-bottom:1rem;"
    "max-width:680px}"
    ".hero h1 em{font-style:normal;display:inline-block;color:transparent;"
    "background:linear-gradient(90deg,#60a5fa,#818cf8,#c4b5fd,#60a5fa);"
    "background-size:250% auto;"
    "-webkit-background-clip:text;background-clip:text;"
    "animation:shimmer 4s linear infinite}"
    ".hero-sub{font-size:1.05rem;color:rgba(255,255,255,.55);max-width:520px;"
    "line-height:1.65;margin-bottom:2.25rem;font-weight:400}"
    ".hero-actions{display:flex;align-items:center;gap:1rem;flex-wrap:wrap}"
    ".btn-primary{display:inline-flex;align-items:center;gap:.5rem;"
    "background:var(--accent);color:#fff;text-decoration:none;font-weight:600;"
    "padding:.8rem 1.5rem;border-radius:8px;"
    "box-shadow:0 0 0 1px rgba(37,99,235,.5),0 4px 14px rgba(37,99,235,.4);"
    "transition:transform .2s,box-shadow .2s;font-size:.9rem;letter-spacing:.01em}"
    ".btn-primary:hover{transform:translateY(-1px);"
    "box-shadow:0 0 0 1px rgba(37,99,235,.6),0 8px 24px rgba(37,99,235,.5)}"
    ".btn-primary svg{width:16px;height:16px}"
    ".hero-badge{display:inline-flex;align-items:center;gap:.4rem;"
    "font-size:.8rem;color:rgba(255,255,255,.45);font-weight:400}"
    ".hero-badge::before{content:'';display:inline-block;width:8px;height:8px;"
    "border-radius:50%;background:#22c55e;box-shadow:0 0 0 2px rgba(34,197,94,.2)}"
    ".stats-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));"
    "gap:.75rem;margin-top:3rem;max-width:480px}"
    ".stat{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);"
    "padding:1rem 1.25rem;border-radius:8px;backdrop-filter:blur(8px)}"
    ".stat-num{font-size:1.6rem;font-weight:700;line-height:1.1;color:#fff;"
    "font-family:'DM Serif Display',Georgia,serif}"
    ".stat-label{font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;"
    "color:rgba(255,255,255,.35);margin-top:.15rem}"
    # Hero content stays visible at first paint; list cards keep the subtle entrance.
    # Toolbar
    ".toolbar-wrap{position:sticky;top:0;z-index:90;"
    "background:rgba(247,246,242,.88);backdrop-filter:blur(16px) saturate(180%);"
    "-webkit-backdrop-filter:blur(16px) saturate(180%);"
    "border-bottom:1px solid var(--border)}"
    ".toolbar{display:flex;align-items:center;gap:.875rem;padding:.75rem 0;flex-wrap:wrap}"
    ".search-box{position:relative;flex:1;min-width:240px}"
    ".search-icon{position:absolute;left:.85rem;top:50%;transform:translateY(-50%);"
    "width:15px;height:15px;color:var(--text-muted);pointer-events:none}"
    ".search-box input{width:100%;padding:.62rem 1rem .62rem 2.5rem;"
    "border:1.5px solid var(--border);border-radius:8px;font-family:inherit;"
    "font-size:.875rem;background:var(--surface);color:var(--text);outline:none;"
    "transition:border-color .15s,box-shadow .15s;font-weight:400}"
    ".search-box input::placeholder{color:var(--text-muted)}"
    ".search-box input:focus{border-color:var(--accent);"
    "box-shadow:0 0 0 3.5px rgba(37,99,235,.12)}"
    ".filter-pills{display:flex;gap:.4rem;flex-wrap:wrap}"
    ".pill{padding:.38rem .9rem;border-radius:8px;"
    "border:1.5px solid var(--border);"
    "background:transparent;font-family:'DM Sans',sans-serif;font-size:.78rem;font-weight:500;"
    "color:var(--text-secondary);cursor:pointer;transition:all .15s;white-space:nowrap;"
    "letter-spacing:.01em}"
    ".pill:hover{border-color:var(--accent);color:var(--accent);background:rgba(37,99,235,.04)}"
    ".pill.active{background:var(--accent);color:#fff;border-color:var(--accent);"
    "box-shadow:0 1px 4px rgba(37,99,235,.3)}"
    ".ops-band{background:var(--surface);border-bottom:1px solid var(--border)}"
    ".ops{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;"
    "background:var(--border);border-left:1px solid var(--border);border-right:1px solid var(--border)}"
    ".ops-item{background:var(--surface);padding:.85rem 1rem}"
    ".ops-label{font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);font-weight:700}"
    ".ops-value{display:flex;align-items:center;gap:.45rem;margin-top:.15rem;font-size:.92rem;font-weight:700;color:var(--text)}"
    ".ops-dot{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.12)}"
    ".ops-dot.warn{background:#d97706;box-shadow:0 0 0 3px rgba(217,119,6,.14)}"
    ".ops-link{color:inherit;text-decoration:none}.ops-link:hover{color:var(--accent)}"
    # Grid + Cards
    ".section-header{display:flex;align-items:baseline;justify-content:space-between;"
    "padding:2rem 0 1.25rem;border-bottom:1px solid var(--border);margin-bottom:1.5rem}"
    ".section-title{font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;"
    "font-weight:600;color:var(--text-muted)}"
    ".section-count{font-size:.78rem;color:var(--text-muted);font-weight:400}"
    ".grid{display:flex;flex-direction:column;gap:.75rem;padding-bottom:3rem}"
    ".card{display:flex;gap:1.15rem;background:var(--surface);"
    "border:1.5px solid var(--border);border-radius:var(--radius);"
    "padding:1.3rem 1.5rem;box-shadow:var(--shadow);"
    "transition:box-shadow .25s,border-color .25s,transform .25s;"
    "opacity:0;animation:fadeUp .5s ease forwards;"
    "position:relative;overflow:hidden}"
    ".card::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;"
    "background:var(--accent);border-radius:99px 0 0 99px;"
    "transform:scaleY(0);transform-origin:bottom;"
    "transition:transform .25s cubic-bezier(.4,0,.2,1)}"
    ".card:hover{box-shadow:var(--shadow-hover);border-color:var(--border-strong);transform:translateY(-2px)}"
    ".card:hover::before{transform:scaleY(1)}"
    "@keyframes fadeUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}"
    "@keyframes shimmer{0%{background-position:0% center}100%{background-position:200% center}}"
    ".hw{display:inline-block}"
    # Date badge
    ".date-badge{display:flex;flex-direction:column;align-items:center;"
    "justify-content:center;min-width:58px;height:64px;"
    "background:var(--dark);border-radius:8px;flex-shrink:0;"
    "box-shadow:0 2px 8px rgba(11,15,25,.35)}"
    ".date-day{font-size:1.5rem;font-weight:700;color:#fff;line-height:1.1;"
    "font-family:'DM Serif Display',Georgia,serif}"
    ".date-month{font-size:.6rem;font-weight:600;text-transform:uppercase;"
    "letter-spacing:.1em;color:rgba(255,255,255,.5);margin-top:.05rem}"
    ".date-tbd{background:var(--surface-2);box-shadow:none;border:1.5px solid var(--border)}"
    ".date-tbd .date-day{color:var(--text-muted);font-size:.82rem;font-family:inherit;font-weight:600}"
    # Card body
    ".card-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:.3rem}"
    ".card-title{font-size:1rem;font-weight:600;line-height:1.4;color:var(--text)}"
    ".card-title a{color:inherit;text-decoration:none;transition:color .15s}"
    ".card-title a:hover{color:var(--accent)}"
    ".card-meta{display:flex;flex-wrap:wrap;gap:.1rem .7rem}"
    ".meta-item{display:inline-flex;align-items:center;gap:.3rem;"
    "font-size:.78rem;color:var(--text-muted);font-weight:400}"
    ".meta-item svg{width:13px;height:13px;flex-shrink:0;opacity:.7}"
    ".card-desc{font-size:.83rem;color:var(--text-secondary);line-height:1.6;"
    "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;"
    "overflow:hidden;margin-top:.1rem}"
    ".card-footer{display:flex;align-items:center;justify-content:space-between;"
    "gap:.5rem;margin-top:.5rem;padding-top:.6rem;border-top:1px solid var(--border)}"
    ".quality-row{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.25rem}"
    ".chip{display:inline-flex;align-items:center;gap:.35rem;border:1px solid var(--border);"
    "border-radius:999px;padding:.18rem .52rem;font-size:.68rem;font-weight:700;color:var(--text-secondary);"
    "background:var(--surface-2);letter-spacing:.02em}"
    ".chip.ai{background:#eef6ff;color:#1d4ed8;border-color:#bfdbfe}"
    ".chip.manual{background:#ecfdf5;color:#047857;border-color:#a7f3d0}"
    ".chip.tbd{background:#fff7ed;color:#c2410c;border-color:#fed7aa}"
    ".source-dot{display:inline-flex;align-items:center;gap:.4rem;"
    "font-size:.7rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;"
    "color:var(--text-muted)}"
    ".source-dot::before{content:'';display:inline-block;width:6px;height:6px;"
    "border-radius:50%;background:currentColor;opacity:.7}"
    ".card-link{display:inline-flex;align-items:center;gap:.3rem;"
    "font-size:.8rem;font-weight:600;color:var(--accent);"
    "text-decoration:none;transition:gap .15s,opacity .15s}"
    ".card-link svg{width:14px;height:14px;transition:transform .15s}"
    ".card-link:hover svg{transform:translateX(2px)}"
    ".card-link:hover{opacity:.8}"
    ".issue-actions{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;justify-content:flex-end}"
    ".issue-link{display:inline-flex;align-items:center;padding:.26rem .56rem;border-radius:999px;"
    "font-size:.68rem;font-weight:700;text-decoration:none;border:1px solid var(--border);"
    "color:var(--text-secondary);background:var(--surface-2);transition:all .15s}"
    ".issue-link:hover{border-color:var(--accent);color:var(--accent);background:#eef6ff}"
    # Empty state + no-results
    ".empty-state{text-align:center;padding:5rem 1rem;color:var(--text-secondary)}"
    ".empty-icon{font-size:2.5rem;margin-bottom:1.25rem;opacity:.4}"
    ".empty-state h3{font-size:1.1rem;font-weight:600;color:var(--text);margin-bottom:.5rem}"
    ".empty-state p{font-size:.9rem;line-height:1.65;max-width:340px;margin:0 auto}"
    ".no-results{text-align:center;padding:3rem 1rem;font-size:.9rem;color:var(--text-muted)}"
    ".review-list{display:flex;flex-direction:column;gap:.75rem;padding:2rem 0 3rem}"
    ".review-card{background:var(--surface);border:1.5px solid var(--border);border-radius:8px;"
    "padding:1.15rem 1.25rem;box-shadow:var(--shadow)}"
    ".review-head{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem}"
    ".review-id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.72rem;color:var(--text-muted)}"
    ".review-title{font-size:1rem;line-height:1.4;margin:.15rem 0;color:var(--text);font-weight:700}"
    ".review-title a{color:inherit;text-decoration:none}.review-title a:hover{color:var(--accent)}"
    ".review-reason{font-size:.82rem;color:var(--text-secondary);line-height:1.55;margin-top:.5rem}"
    # Footer
    "footer{background:var(--dark);border-top:1px solid rgba(255,255,255,.06);"
    "padding:2.5rem 0}"
    ".footer-inner{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;"
    "gap:1.5rem}"
    ".footer-brand{display:flex;flex-direction:column;gap:.25rem}"
    ".footer-brand-name{color:#fff;font-weight:600;font-size:.9rem}"
    ".footer-brand-desc{color:rgba(255,255,255,.3);font-size:.75rem}"
    ".footer-center{text-align:center;font-size:.75rem;color:rgba(255,255,255,.2)}"
    ".footer-links{display:flex;justify-content:flex-end;align-items:center;gap:1.25rem}"
    ".footer-links a{color:rgba(255,255,255,.4);text-decoration:none;font-size:.78rem;"
    "font-weight:500;transition:color .15s}"
    ".footer-links a:hover{color:rgba(255,255,255,.8)}"
    # Product-dashboard polish
    "body *{letter-spacing:0}"
    ".container{max-width:1180px}"
    ".hero{background:#111827}"
    ".hero-bg{background:linear-gradient(135deg,#0b1220 0%,#172033 54%,#17365e 100%)}"
    ".hero-grid{opacity:.16;background-size:38px 38px}"
    ".topbar{padding:1rem 0}"
    ".hero-body{display:grid;grid-template-columns:minmax(0,1fr) 420px;"
    "gap:2rem;align-items:end;padding:2.35rem 0 2rem}"
    ".hero-body-single{display:block;max-width:760px}"
    ".hero-copy{min-width:0}"
    ".hero h1{font-size:3rem;letter-spacing:0;max-width:720px;margin-bottom:.8rem}"
    ".hero h1 em{animation:none;background:#a5b4fc;-webkit-background-clip:text;background-clip:text}"
    ".hero-sub{max-width:620px;margin-bottom:1.35rem;color:rgba(255,255,255,.68)}"
    ".hero-actions{gap:.75rem}"
    ".hero-panel{border:1px solid rgba(255,255,255,.12);background:rgba(15,23,42,.62);"
    "border-radius:8px;padding:1rem;box-shadow:0 20px 50px rgba(0,0,0,.2);"
    "backdrop-filter:blur(12px)}"
    ".panel-kicker{font-size:.72rem;font-weight:700;text-transform:uppercase;color:#93c5fd;margin-bottom:.55rem}"
    ".panel-status{display:flex;align-items:center;gap:.55rem;color:#fff;font-weight:700}"
    ".panel-status small{color:rgba(255,255,255,.55);font-size:.76rem;font-weight:500;margin-left:auto}"
    ".stats-row{max-width:none;margin:1rem 0 0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));"
    "gap:1px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.1);"
    "border-radius:8px;overflow:hidden}"
    ".stat{border:0;border-radius:0;background:rgba(255,255,255,.055);padding:.9rem .85rem;backdrop-filter:none}"
    ".stat-num{font-size:1.7rem}"
    ".stat-label{font-size:.72rem;color:rgba(255,255,255,.48);margin-top:.18rem}"
    ".panel-links{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem;margin-top:.75rem}"
    ".panel-link,.panel-metric{display:flex;align-items:center;justify-content:space-between;gap:.75rem;"
    "padding:.72rem .78rem;border-radius:8px;border:1px solid rgba(255,255,255,.1);"
    "background:rgba(255,255,255,.045);text-decoration:none;color:#fff}"
    ".panel-link span,.panel-metric span{font-size:.75rem;color:rgba(255,255,255,.58);font-weight:600}"
    ".panel-link strong,.panel-metric strong{font-size:1rem;color:#fff}"
    ".panel-link:hover{border-color:rgba(147,197,253,.45);background:rgba(37,99,235,.16)}"
    ".ops-band{display:none}"
    ".toolbar-wrap{position:sticky;top:0;background:rgba(247,246,242,.94);box-shadow:0 1px 0 var(--border);"
    "border-bottom:0}"
    ".toolbar{display:grid;grid-template-columns:minmax(280px,1fr) auto;gap:.8rem;padding:1rem 0}"
    ".search-box input{height:46px;border-color:#dedbd2;box-shadow:0 1px 2px rgba(15,23,42,.04)}"
    ".filter-pills{align-items:center}"
    ".pill{height:40px;background:#fff;border-color:#dedbd2;color:#475569}"
    ".pill.active{background:#1d4ed8;border-color:#1d4ed8}"
    ".section-header{padding:1.35rem 0 1rem;margin-bottom:.9rem}"
    ".grid{gap:.65rem}"
    ".card{opacity:1;animation:none;box-shadow:none;border-color:#e1ded6;padding:1.05rem 1.15rem}"
    ".card:hover{transform:none;box-shadow:0 8px 24px rgba(15,23,42,.08)}"
    ".date-badge{min-width:54px;height:58px;box-shadow:none}"
    ".card-title{font-size:1.02rem}"
    ".card-desc{font-size:.84rem;line-height:1.5}"
    # Responsive
    "@media(max-width:720px){"
    ".container{padding:0 1.1rem}"
    ".topbar{padding:1rem 0}"
    ".hero-body{padding:2.75rem 0 3.25rem}"
    ".hero h1{font-size:2.2rem}"
    ".hero-sub{font-size:.95rem}"
    ".stats-row{grid-template-columns:repeat(3,1fr);max-width:100%}"
    ".stat-num{font-size:1.3rem}"
    ".toolbar{gap:.6rem}"
    ".filter-pills{overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none;-ms-overflow-style:none}"
    ".filter-pills::-webkit-scrollbar{display:none}"
    ".card{padding:1.1rem 1.15rem;gap:.85rem}"
    ".ops{grid-template-columns:repeat(2,minmax(0,1fr))}"
    ".date-badge{min-width:50px;height:56px}"
    ".date-day{font-size:1.25rem}"
    ".card-title{font-size:.95rem}"
    ".footer-inner{grid-template-columns:1fr;text-align:center;gap:.75rem}"
    ".footer-links{justify-content:center}"
    ".footer-center{display:none}}"
    "@media(max-width:900px){"
    ".hero-body{grid-template-columns:1fr;padding:2rem 0 1.6rem}"
    ".hero-panel{max-width:100%}"
    ".toolbar{grid-template-columns:1fr}"
    ".hero h1{font-size:2.35rem}"
    ".panel-links{grid-template-columns:1fr}}"
    "@media(max-width:560px){"
    ".stats-row{grid-template-columns:1fr}"
    ".topbar-link{padding:.45rem .65rem}"
    ".hero-actions{display:none}"
    ".card{align-items:flex-start}"
    ".card-footer{flex-direction:column;align-items:flex-start}}"
)

_CSS += """
:root{
--bg:#f4f0e8;--surface:#fffdf8;--surface-2:#ece7dc;--border:#ded6c8;
--border-strong:#b9ad99;--dark:#08111e;--accent:#2454ff;--accent-hover:#163bd6;
--teal:#15a996;--gold:#d88a25;--text:#101419;--text-secondary:#4b5563;
--text-muted:#7a8492;--radius:8px;--shadow:0 12px 34px rgba(24,30,42,.08);
--shadow-hover:0 18px 44px rgba(24,30,42,.13)
}
html{background:var(--bg)}
body{background:
linear-gradient(180deg,#f9f6ef 0,#f4f0e8 34rem,#ece7dc 100%);
font-family:'Inter','DM Sans','Helvetica Neue',Arial,sans-serif;color:var(--text)}
body *{letter-spacing:0!important}
a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid rgba(21,169,150,.7);outline-offset:3px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.container{max-width:1200px;padding:0 1.5rem}
.hero{min-height:620px;background:#08111e;color:#fff;isolation:isolate}
.hero::before{content:'';position:absolute;inset:0;z-index:0;background:
linear-gradient(90deg,rgba(6,10,18,.92) 0%,rgba(6,10,18,.76) 42%,rgba(6,10,18,.2) 100%),
linear-gradient(180deg,rgba(6,10,18,.18) 0%,rgba(6,10,18,.76) 100%),
url('hero-hackathon-milano.png') center/cover no-repeat;transform:scale(1.01)}
.hero::after{content:'';position:absolute;inset:auto 0 0;z-index:0;height:38%;background:linear-gradient(180deg,rgba(244,240,232,0),var(--bg))}
.hero-bg,.hero-grid{display:none}
.hero-content{position:relative;z-index:1}
.topbar{padding:1rem 0;border-bottom:1px solid rgba(255,255,255,.12)}
.brand-mark{width:40px;height:40px;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08);box-shadow:inset 0 1px 0 rgba(255,255,255,.2)}
.brand-name{font-weight:800;font-size:.95rem}
.brand-city{color:rgba(255,255,255,.58);font-size:.76rem}
.topbar-link{min-height:44px;border-color:rgba(255,255,255,.18);background:rgba(255,255,255,.08);color:#f8fafc;padding:.58rem .95rem;cursor:pointer}
.topbar-link:hover{background:rgba(255,255,255,.14);border-color:rgba(255,255,255,.32);transform:translateY(-1px)}
.hero-body{display:block;padding:4.2rem 0 2.6rem;max-width:840px}
.hero-body-single{display:block;max-width:800px}
.hero-copy{min-width:0}
.hero-eyebrow{color:#a9f7e9;margin-bottom:1rem;font-weight:800;font-size:.78rem;text-transform:none}
.hero-eyebrow span{background:var(--teal);animation:none}
.hero h1{font-family:'Space Grotesk','Inter',system-ui,sans-serif;font-size:4.9rem;line-height:.96;font-weight:700;color:#fff;max-width:760px;margin:0 0 1rem}
.hero h1 em{font-style:normal;color:#a9f7e9;background:none;-webkit-background-clip:initial;background-clip:initial}
.hero-sub{font-size:1.13rem;color:rgba(255,255,255,.8);max-width:640px;line-height:1.65;margin-bottom:1.45rem}
.hero-actions{display:flex;align-items:center;gap:.75rem;flex-wrap:wrap}
.btn-primary,.btn-secondary{min-height:44px;display:inline-flex;align-items:center;gap:.5rem;text-decoration:none;font-weight:800;border-radius:8px;transition:transform .2s,background .2s,border-color .2s,box-shadow .2s}
.btn-primary{background:#fff;color:#08111e;padding:.82rem 1.2rem;border:1px solid #fff;box-shadow:0 12px 28px rgba(0,0,0,.22)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 18px 40px rgba(0,0,0,.28)}
.btn-secondary{background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.18);padding:.82rem 1rem}
.btn-secondary:hover{background:rgba(255,255,255,.14);border-color:rgba(255,255,255,.34);transform:translateY(-2px)}
.btn-primary svg,.btn-secondary svg{width:16px;height:16px}
.hero-badge{min-height:44px;color:rgba(255,255,255,.72);padding:0 .15rem}
.hero-badge::before{background:var(--teal);box-shadow:0 0 0 4px rgba(21,169,150,.18)}
.hero-panel{margin-top:2rem;max-width:780px;border:1px solid rgba(255,255,255,.16);background:rgba(8,17,30,.62);border-radius:8px;padding:1rem;box-shadow:none;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}
.panel-kicker{color:#a9f7e9;font-size:.72rem;font-weight:800;margin-bottom:.55rem;text-transform:none}
.panel-status{display:flex;align-items:center;gap:.6rem;color:#fff;font-weight:800}
.panel-status small{margin-left:auto;color:rgba(255,255,255,.68);font-size:.78rem;font-weight:600}
.stats-row{margin:.95rem 0 0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.12);border-radius:8px;overflow:hidden;max-width:none}
.stat{border:0;border-radius:0;background:rgba(255,255,255,.08);padding:1rem .9rem;backdrop-filter:none}
.stat-num{font-family:'Space Grotesk','Inter',system-ui,sans-serif;font-size:1.9rem;color:#fff}
.stat-label{font-size:.74rem;color:rgba(255,255,255,.62);text-transform:none;font-weight:700}
.panel-links{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem;margin-top:.75rem}
.panel-link,.panel-metric{min-height:44px;display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.72rem .8rem;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);text-decoration:none;color:#fff}
.panel-link span,.panel-metric span{font-size:.8rem;color:rgba(255,255,255,.68);font-weight:700}
.panel-link strong,.panel-metric strong{font-size:1rem;color:#fff}
.panel-link:hover{border-color:rgba(169,247,233,.48);background:rgba(21,169,150,.14)}
.toolbar-wrap{top:0;background:rgba(250,247,240,.9);border-bottom:1px solid rgba(185,173,153,.42);box-shadow:0 12px 26px rgba(24,30,42,.06)}
.toolbar{display:grid;grid-template-columns:minmax(260px,1fr) auto;gap:.8rem;padding:.9rem 0}
.search-box input{height:48px;border:1px solid var(--border);border-radius:8px;background:rgba(255,253,248,.92);box-shadow:0 1px 0 rgba(255,255,255,.8);font-size:.92rem}
.search-box input:focus{border-color:var(--teal);box-shadow:0 0 0 4px rgba(21,169,150,.14)}
.search-icon{color:#5f6b7a}
.filter-pills{align-items:center;gap:.45rem}
.pill{height:44px;border-radius:8px;border:1px solid var(--border);background:rgba(255,253,248,.84);color:#4b5563;font-weight:800;padding:.42rem .9rem}
.pill:hover{border-color:var(--teal);color:#0f766e;background:#eefcf8}
.pill.active{background:#101419;border-color:#101419;color:#fff;box-shadow:none}
.section-header{padding:1.35rem 0 1rem;margin-bottom:.9rem;border-bottom:1px solid rgba(185,173,153,.42)}
.section-title{font-size:.78rem;font-weight:900;color:#101419;text-transform:none}
.section-count{font-size:.86rem;color:#667085;font-weight:700}
.grid{gap:.75rem;padding-bottom:3.4rem}
.card{display:grid;grid-template-columns:72px minmax(0,1fr);gap:1rem;background:rgba(255,253,248,.9);border:1px solid rgba(185,173,153,.46);border-radius:8px;padding:1.05rem;box-shadow:var(--shadow);opacity:1;animation:none;transition:transform .2s,box-shadow .2s,border-color .2s}
.card::before{display:none}
.card:hover{transform:translateY(-2px);box-shadow:var(--shadow-hover);border-color:#a99b84}
.date-badge{min-width:64px;width:64px;height:68px;border-radius:8px;background:#101419;box-shadow:none}
.date-day{font-family:'Space Grotesk','Inter',system-ui,sans-serif;font-size:1.55rem}
.date-month{font-size:.68rem;color:#a9f7e9;font-weight:800}
.date-tbd{background:#ede6d8;border:1px solid var(--border)}
.date-tbd .date-day{color:#5f6b7a}
.card-body{gap:.35rem}
.card-title{font-size:1.08rem;font-weight:850;line-height:1.35}
.card-title a:hover{color:#1646dc}
.card-meta{gap:.18rem .8rem}
.meta-item{font-size:.82rem;color:#5f6b7a}
.meta-item svg{width:14px;height:14px;color:#0f766e}
.quality-row{gap:.35rem}
.chip{border-radius:8px;padding:.2rem .5rem;font-size:.7rem;font-weight:850;background:#f1ecdf;color:#4b5563;border-color:#ded6c8}
.chip.ai{background:#eef4ff;color:#1646dc;border-color:#c7d7fe}
.chip.manual{background:#eefcf8;color:#0f766e;border-color:#afe9dd}
.chip.tbd{background:#fff6e6;color:#a55a00;border-color:#f0cf9b}
.card-desc{font-size:.9rem;color:#4b5563;line-height:1.58}
.card-footer{gap:.75rem;border-top:1px solid rgba(185,173,153,.34);padding-top:.72rem}
.source-dot{font-size:.72rem;color:#667085;font-weight:850;text-transform:none}
.source-dot::before{background:var(--gold);opacity:1}
.issue-actions{gap:.45rem}
.issue-link{min-height:34px;border-radius:8px;background:#f7f1e6;color:#4b5563;border-color:#ded6c8;font-size:.72rem}
.issue-link:hover{background:#eefcf8;border-color:#85dcca;color:#0f766e}
.card-link{min-height:34px;color:#1646dc;font-weight:850}
.empty-state{background:rgba(255,253,248,.82);border:1px solid rgba(185,173,153,.46);border-radius:8px;margin-bottom:3rem}
.empty-icon{width:44px;height:44px;margin:0 auto 1rem;color:#0f766e;opacity:1}
.empty-icon svg{width:44px;height:44px}
.review-list{gap:.75rem;padding:1rem 0 3.4rem}
.review-card{background:rgba(255,253,248,.9);border:1px solid rgba(185,173,153,.46);border-radius:8px;box-shadow:var(--shadow)}
.review-title{font-size:1.08rem}
footer{background:#08111e;padding:2.2rem 0}
.footer-brand-name{font-weight:800}
.footer-brand-desc,.footer-center,.footer-links a{color:rgba(255,255,255,.58)}
@media(max-width:900px){
.hero{min-height:560px}
.hero-body{max-width:720px;padding:3.1rem 0 2rem}
.hero h1{font-size:3.7rem}
.hero-sub{font-size:1.04rem}
.toolbar{grid-template-columns:1fr}
.panel-links{grid-template-columns:1fr}
}
@media(max-width:720px){
.container{padding:0 1rem}
.hero{min-height:520px}
.topbar{padding:.85rem 0}
.brand-mark{width:36px;height:36px}
.hero-body{padding:2.35rem 0 1.65rem}
.hero h1{font-size:2.85rem}
.hero-sub{font-size:.98rem;margin-bottom:1rem}
.hero-actions{gap:.6rem}
.btn-primary,.btn-secondary{width:100%;justify-content:center}
.hero-badge{width:100%;justify-content:center}
.hero-panel{padding:.85rem;margin-top:1.25rem}
.panel-status{align-items:flex-start;flex-wrap:wrap}
.panel-status small{width:100%;margin-left:1.1rem}
.stats-row{grid-template-columns:repeat(3,minmax(0,1fr))}
.stat{padding:.75rem .55rem}
.stat-num{font-size:1.35rem}
.stat-label{font-size:.68rem}
.filter-pills{overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none}
.filter-pills::-webkit-scrollbar{display:none}
.card{grid-template-columns:58px minmax(0,1fr);padding:.9rem;gap:.8rem}
.date-badge{min-width:54px;width:54px;height:58px}
.date-day{font-size:1.25rem}
.date-month{font-size:.58rem}
.card-footer{flex-direction:column;align-items:flex-start}
.issue-actions{justify-content:flex-start}
.footer-inner{grid-template-columns:1fr;text-align:center;gap:.75rem}
.footer-links{justify-content:center}
.footer-center{display:block}
}
@media(max-width:420px){
.hero h1{font-size:2.45rem}
.topbar-link{padding:.5rem .65rem}
.brand-city{display:none}
.stats-row{grid-template-columns:1fr}
.card{grid-template-columns:1fr}
.card-left{display:flex}
}
@media(prefers-reduced-motion:reduce){
*,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.001ms!important}
}
"""

_CSS += """
.hero{min-height:560px}
.hero-body{padding:2.7rem 0 1.6rem}
.hero h1{font-size:4.45rem}
.hero-sub{margin-bottom:1.15rem}
.hero-panel{display:grid;grid-template-columns:minmax(170px,.9fr) minmax(240px,1.35fr) minmax(190px,1fr);gap:.75rem;align-items:stretch;margin-top:1.35rem;padding:.85rem}
.panel-kicker{grid-column:1;grid-row:1;margin:0}
.panel-status{grid-column:1;grid-row:2;align-self:end}
.stats-row{grid-column:2;grid-row:1 / span 2;margin:0;height:100%}
.panel-links{grid-column:3;grid-row:1 / span 2;margin:0;grid-template-columns:1fr}
.panel-link,.panel-metric{min-height:42px}
@media(max-width:900px){
.hero{min-height:540px}
.hero-body{padding:2.35rem 0 1.45rem}
.hero h1{font-size:3.45rem}
.hero-panel{grid-template-columns:1fr;gap:.7rem}
.panel-kicker,.panel-status,.stats-row,.panel-links{grid-column:auto;grid-row:auto}
.panel-links{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:720px){
.hero{min-height:500px}
.hero-body{padding:2rem 0 1.2rem}
.hero h1{font-size:2.75rem}
.hero-sub{font-size:.95rem;line-height:1.55}
.btn-primary,.btn-secondary{width:auto}
.hero-badge{display:none}
.hero-panel{margin-top:1rem}
.panel-kicker,.panel-links{display:none}
.panel-status small{display:none}
.panel-links{grid-template-columns:1fr}
}
@media(max-width:420px){
.hero h1{font-size:2.35rem}
.stats-row{grid-template-columns:repeat(3,minmax(0,1fr))}
.panel-links{grid-template-columns:1fr}
}
"""

# ---- JS ----

_JS = (
    "(function(){"
    "var input=document.getElementById('search');"
    "var grid=document.getElementById('grid');"
    "var cards=Array.from(grid.querySelectorAll('.card'));"
    "var pills=document.querySelectorAll('.pill');"
    "var noResults=document.getElementById('no-results');"
    "var countLabel=document.getElementById('count-label');"
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
    "if(countLabel)countLabel.textContent=visible+' event'+(visible===1?'o':'i');"
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

_CSS += """
body{background:#02030a;color:#f6f4ef;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;z-index:-2;background:
radial-gradient(circle at 72% 18%,rgba(53,96,255,.28),transparent 28rem),
radial-gradient(circle at 16% 30%,rgba(24,194,165,.16),transparent 24rem),
linear-gradient(180deg,#02030a 0%,#050814 42%,#e8e5dc 42.2%,#f5f1e9 100%)}
.hero{min-height:clamp(600px,88dvh,780px);background:#02030a;border:0;overflow:hidden}
.hero::before{background:
linear-gradient(90deg,rgba(2,3,10,.98) 0%,rgba(2,3,10,.84) 42%,rgba(2,3,10,.28) 100%),
linear-gradient(180deg,rgba(2,3,10,.08),rgba(2,3,10,.92)),
url('hero-hackathon-milano.png') center/cover no-repeat;opacity:.44;filter:saturate(1.1) contrast(1.2)}
.hero::after{height:32%;background:linear-gradient(180deg,rgba(2,3,10,0),#02030a 82%,#070914)}
.signal-canvas{position:absolute;inset:0;z-index:0;width:100%;height:100%;opacity:.95;mix-blend-mode:screen}
.hero-scanline{position:absolute;left:0;right:0;bottom:4.4rem;z-index:1;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.2),rgba(69,105,255,.9),transparent)}
.hero-scanline::after{content:'Live data. Every scan.';position:absolute;right:11%;top:.9rem;color:#f6f4ef;font-size:.8rem;font-weight:800}
.topbar{border-color:rgba(255,255,255,.08)}
.brand-mark{background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.16)}
.brand-name{font-size:1rem}
.topbar-link{background:#4569ff;border-color:#4569ff;box-shadow:0 0 30px rgba(69,105,255,.28);text-transform:uppercase;font-size:.72rem;letter-spacing:.12em!important}
.topbar-link:hover{background:#5d7bff;border-color:#5d7bff}
.hero-body{max-width:760px;padding:clamp(4.2rem,9vh,6.1rem) 0 1.4rem}
.hero-eyebrow{font-family:'JetBrains Mono','Inter',monospace;color:#cdd6ff;text-transform:uppercase!important;letter-spacing:.14em!important}
.hero-eyebrow span{background:#45f0d1;box-shadow:0 0 20px rgba(69,240,209,.8)}
.hero h1{font-size:clamp(4.1rem,8.2vw,7.1rem);letter-spacing:-.06em!important;line-height:.86;max-width:820px;text-wrap:balance}
.hero h1 em{color:#eef2ff;text-shadow:0 0 34px rgba(69,105,255,.46)}
.hero-sub{font-size:1.02rem;color:rgba(246,244,239,.72);max-width:620px}
.btn-primary{background:#4569ff;color:#fff;border-color:#4569ff;text-transform:uppercase;font-size:.75rem;letter-spacing:.1em!important;box-shadow:0 0 40px rgba(69,105,255,.36)}
.btn-secondary{border-color:rgba(255,255,255,.16);background:rgba(255,255,255,.04);text-transform:uppercase;font-size:.75rem;letter-spacing:.1em!important}
.hero-panel{max-width:820px;background:rgba(7,10,22,.58);border-color:rgba(255,255,255,.12);box-shadow:0 0 0 1px rgba(255,255,255,.02),0 30px 90px rgba(0,0,0,.34)}
.panel-kicker,.stat-label,.panel-link span,.panel-metric span{font-family:'JetBrains Mono','Inter',monospace;text-transform:uppercase!important;letter-spacing:.08em!important}
.stats-row,.panel-link,.panel-metric{background:rgba(255,255,255,.045);border-color:rgba(255,255,255,.1)}
.stat{background:rgba(255,255,255,.055)}
.stat-num{color:#f6f4ef}
.signal-strip{position:relative;background:#070914;color:#f6f4ef;border-top:1px solid rgba(255,255,255,.08);border-bottom:1px solid rgba(255,255,255,.08);overflow:hidden}
.signal-strip::before{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(69,105,255,.08),transparent);animation:hmSweep 7s ease-in-out infinite}
.signal-inner{position:relative;max-width:1200px;margin:0 auto;padding:.95rem 1.5rem;display:grid;grid-template-columns:auto 1fr auto;gap:1rem;align-items:center;font-family:'JetBrains Mono','Inter',monospace;font-size:.74rem;text-transform:uppercase;letter-spacing:.12em;color:rgba(246,244,239,.72)}
.signal-inner strong{color:#fff}
.signal-feed{overflow:hidden;white-space:nowrap}
.signal-feed span{display:inline-block;min-width:100%;animation:hmTicker 24s linear infinite}
.intel-section{position:relative;background:#f2eee5;color:#070914;padding:5rem 0 4.6rem;border-top:1px solid #050814;overflow:hidden}
.intel-section::before{content:'';position:absolute;inset:0;background:linear-gradient(90deg,rgba(7,9,20,.06) 1px,transparent 1px),linear-gradient(rgba(7,9,20,.045) 1px,transparent 1px);background-size:54px 54px;mask-image:linear-gradient(180deg,#000 0%,transparent 86%);pointer-events:none}
.intel-grid{position:relative;max-width:1200px;margin:0 auto;padding:0 1.5rem;display:grid;grid-template-columns:minmax(0,1.08fr) minmax(0,.92fr);gap:1rem;align-items:start}
.intel-visual,.intel-copy,.intel-card{border:1px solid rgba(7,9,20,.22);border-radius:8px}
.intel-copy{position:relative;z-index:1;padding:clamp(1.6rem,4vw,3rem);display:flex;flex-direction:column;gap:1.15rem;background:rgba(255,255,255,.46);box-shadow:0 24px 70px rgba(7,9,20,.08);overflow:hidden}
.intel-copy::before{content:'';position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,#4569ff,#18c2a5,#d97706);opacity:.9}
.section-code{font-family:'JetBrains Mono','Inter',monospace;font-size:.76rem;text-transform:uppercase;letter-spacing:.12em;color:#4569ff;font-weight:800}
.intel-copy h2{font-family:'Space Grotesk','Inter',sans-serif;font-size:clamp(2.15rem,4vw,3.55rem);line-height:.96;letter-spacing:-.05em;margin:0;text-wrap:balance;max-width:720px}
.intel-copy p{font-size:1rem;line-height:1.72;color:#3e4451;max-width:650px}
.intel-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;border:1px solid rgba(7,9,20,.18);border-radius:8px;overflow:hidden;margin-top:auto;background:rgba(7,9,20,.12)}
.intel-card{border:0;border-radius:0;padding:1.15rem;background:rgba(255,255,255,.52);min-height:132px}
.intel-card+.intel-card{border-left:0}
.intel-card b{display:block;font-family:'JetBrains Mono','Inter',monospace;font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.75rem;color:#070914}
.intel-card span{display:block;color:#4d5360;font-size:.85rem;line-height:1.55}
.intel-visual{position:relative;min-height:560px;overflow:hidden;background:radial-gradient(circle at 46% 40%,rgba(69,105,255,.24),transparent 16rem),radial-gradient(circle at 72% 72%,rgba(24,194,165,.16),transparent 18rem),#080b16;box-shadow:inset 0 0 0 1px rgba(255,255,255,.04),0 28px 90px rgba(7,9,20,.18)}
.intel-visual::before{content:'';position:absolute;inset:7%;border:1px solid rgba(255,255,255,.1);background-image:radial-gradient(rgba(255,255,255,.72) 1px,transparent 1.6px);background-size:18px 18px;mask-image:radial-gradient(ellipse at 50% 50%,#000 0 42%,transparent 74%);animation:hmFloat 8s ease-in-out infinite}
.intel-visual::after{content:'';position:absolute;left:-30%;right:-30%;top:48%;height:2px;background:linear-gradient(90deg,transparent,#4569ff,#18c2a5,transparent);box-shadow:0 0 32px rgba(69,105,255,.75);animation:hmTrace 5.8s ease-in-out infinite}
.intel-orbit{position:absolute;inset:16%;border:1px solid rgba(255,255,255,.11);border-radius:50%;transform:rotate(-10deg)}
.intel-orbit.two{inset:25% 11%;border-color:rgba(69,105,255,.25);transform:rotate(16deg)}
.radar-core{position:absolute;left:50%;top:48%;width:120px;height:120px;transform:translate(-50%,-50%);border:1px solid rgba(69,240,209,.5);border-radius:50%;box-shadow:0 0 44px rgba(69,240,209,.18),inset 0 0 30px rgba(69,105,255,.18)}
.radar-core::before{content:'';position:absolute;inset:18px;border-radius:50%;background:radial-gradient(circle,#45f0d1 0 4px,rgba(69,240,209,.18) 5px,transparent 26px)}
.intel-node{position:absolute;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.08);color:#f6f4ef;border-radius:8px;padding:.78rem .95rem;font-family:'JetBrains Mono','Inter',monospace;font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;backdrop-filter:blur(14px);box-shadow:0 22px 60px rgba(0,0,0,.24)}
.intel-node.one{left:7%;top:10%}.intel-node.two{right:7%;top:26%}.intel-node.three{left:13%;bottom:18%}.intel-node.four{right:11%;bottom:12%}
.radar-metrics{position:absolute;left:1rem;right:1rem;bottom:1rem;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.12);border-radius:8px;overflow:hidden}
.radar-metric{background:rgba(2,3,10,.62);padding:.9rem;color:#f6f4ef}
.radar-metric span{display:block;font-family:'JetBrains Mono','Inter',monospace;font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:rgba(246,244,239,.48);margin-bottom:.2rem}
.radar-metric strong{font-size:1rem}
.toolbar-wrap{background:rgba(2,3,10,.88);border-color:rgba(255,255,255,.08);box-shadow:0 18px 60px rgba(2,3,10,.2);backdrop-filter:blur(20px) saturate(140%)}
.search-box input{min-height:44px;background:rgba(255,255,255,.07);border-color:rgba(255,255,255,.14);color:#fff}
.search-box input::placeholder{color:rgba(255,255,255,.54)}
.pill{min-height:40px;background:rgba(255,255,255,.065);border-color:rgba(255,255,255,.12);color:rgba(255,255,255,.78)}
.pill:hover{background:rgba(69,105,255,.14);border-color:rgba(69,105,255,.52);color:#fff}
.pill.active{background:#4569ff;border-color:#4569ff;color:#fff;box-shadow:0 0 24px rgba(69,105,255,.28)}
main.container{background:#f5f1e9;color:#070914;max-width:none;padding-left:max(1.5rem,calc((100vw - 1200px)/2));padding-right:max(1.5rem,calc((100vw - 1200px)/2))}
.event-deck{position:relative;padding-bottom:5.2rem;background:linear-gradient(180deg,#f5f1e9 0%,#ebe6dc 100%)}
.event-deck::before{content:'';position:absolute;inset:0;background:radial-gradient(circle at 14% 10%,rgba(24,194,165,.14),transparent 18rem),radial-gradient(circle at 86% 2%,rgba(69,105,255,.18),transparent 22rem);pointer-events:none}
.event-intro{position:relative;z-index:1;display:grid;grid-template-columns:minmax(0,1.08fr) minmax(300px,.92fr);gap:1rem;padding:4.4rem 0 2rem;align-items:stretch}
.event-intro-copy{border-left:3px solid #070914;padding-left:1.35rem}
.event-intro h2{font-family:'Space Grotesk','Inter',sans-serif;font-size:clamp(2.2rem,4.8vw,4.2rem);line-height:.96;letter-spacing:-.05em;margin:.65rem 0 .9rem;text-wrap:balance}
.event-intro p{max-width:640px;color:#515866;font-size:1rem;line-height:1.72}
.event-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;border:1px solid rgba(7,9,20,.2);border-radius:8px;overflow:hidden;background:rgba(7,9,20,.16);box-shadow:0 26px 70px rgba(7,9,20,.08)}
.event-metric{position:relative;min-height:170px;padding:1.15rem;background:rgba(255,255,255,.54);overflow:hidden}
.event-metric::after{content:'';position:absolute;right:-18px;bottom:-28px;width:86px;height:86px;border:1px solid rgba(69,105,255,.22);border-radius:50%}
.event-metric span,.event-metric small{display:block;font-family:'JetBrains Mono','Inter',monospace;text-transform:uppercase;letter-spacing:.08em;color:#6b7280}
.event-metric span{font-size:.68rem;font-weight:800}
.event-metric strong{display:block;margin:.9rem 0 .35rem;font-family:'Space Grotesk','Inter',sans-serif;font-size:clamp(2.2rem,5vw,3.4rem);line-height:.9;letter-spacing:-.04em;color:#070914}
.event-metric small{font-size:.62rem;line-height:1.45}
.section-header{position:relative;z-index:1;border-color:rgba(7,9,20,.18);padding:1.45rem 0 1rem;margin-bottom:1rem}
.section-title{font-family:'JetBrains Mono','Inter',monospace;text-transform:uppercase!important;letter-spacing:.12em!important;color:#070914}
.section-count{font-family:'JetBrains Mono','Inter',monospace;color:#5a6270}
.grid{position:relative;z-index:1;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem;padding-bottom:0}
.card{position:relative;display:grid;grid-template-columns:1fr;gap:1rem;min-height:360px;overflow:hidden;background:rgba(255,255,255,.74);border-color:rgba(7,9,20,.18);box-shadow:0 26px 70px rgba(7,9,20,.08);transform:perspective(900px) rotateX(var(--tilt-y,0deg)) rotateY(var(--tilt-x,0deg));will-change:transform}
.card::before{inset:auto 1.1rem 1rem 1.1rem;width:auto;height:3px;border-radius:99px;background:linear-gradient(90deg,#4569ff,#18c2a5,#d97706);transform:scaleX(0);transform-origin:left}
.card::after{content:'';position:absolute;inset:0;background:radial-gradient(circle at var(--mx,50%) var(--my,50%),rgba(69,105,255,.18),transparent 16rem);opacity:0;transition:opacity .2s;pointer-events:none}
.card:hover::before{transform:scaleX(1)}
.card:hover::after{opacity:1}
.card-left{display:flex;align-items:flex-start}
.date-badge{min-width:72px;width:72px;height:72px;background:#070914}
.date-day{font-size:1.9rem}
.date-month{color:#45f0d1}
.card-body{gap:.55rem}
.card-title{font-family:'Space Grotesk','Inter',sans-serif;font-size:1.2rem;line-height:1.18;letter-spacing:-.02em}
.card-meta{gap:.35rem .85rem}
.card-desc{font-size:.9rem;color:#444b58;-webkit-line-clamp:4}
.card-footer{margin-top:auto;align-items:flex-start;flex-direction:column;border-color:rgba(7,9,20,.13);gap:.7rem}
.source-dot{font-family:'JetBrains Mono','Inter',monospace}
.issue-actions{justify-content:flex-start}
.issue-link{min-height:32px}
.no-results{position:relative;z-index:1}
footer{background:#02030a}
@keyframes hmTicker{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@keyframes hmSweep{0%,100%{transform:translateX(-45%);opacity:.25}50%{transform:translateX(45%);opacity:1}}
@keyframes hmFloat{0%,100%{transform:translate3d(0,0,0) rotate(-2deg)}50%{transform:translate3d(0,-14px,0) rotate(2deg)}}
@keyframes hmTrace{0%,100%{transform:translateX(-18%);opacity:.35}50%{transform:translateX(18%);opacity:1}}
[data-reveal]{opacity:0;transform:translateY(28px);transition:opacity .7s ease,transform .7s ease}
[data-reveal].is-visible{opacity:1;transform:translateY(0)}
@media(max-width:900px){
.hero{min-height:clamp(600px,86dvh,720px)}
.hero-body{padding:3.6rem 0 1.2rem}
.hero h1{font-size:clamp(3.3rem,13vw,5rem)}
.signal-canvas{opacity:.55}
.signal-inner{grid-template-columns:1fr;gap:.45rem}
.signal-feed span{animation-duration:18s}
.intel-grid{grid-template-columns:1fr}
.intel-visual{min-height:360px}
.intel-cards{grid-template-columns:repeat(2,minmax(0,1fr))}
.intel-card:nth-child(odd){border-left:0}
.event-intro{grid-template-columns:1fr;padding-top:3.2rem}
.event-metrics{grid-template-columns:1fr}
.event-metric{min-height:130px}
}
@media(max-width:560px){
.hero{min-height:640px}
.hero-scanline{display:none}
.hero-body{padding:2.4rem 0 1rem}
.hero h1{font-size:3.25rem}
.hero-actions{display:flex}
.hero-panel{display:block}
.stats-row{grid-template-columns:repeat(3,minmax(0,1fr));margin-top:.7rem}
.stat{padding:.7rem .45rem}
.toolbar{display:grid;grid-template-columns:1fr;align-items:stretch}
.search-box{min-width:0;width:100%}
.filter-pills{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));width:100%;gap:.45rem}
.pill{display:flex;align-items:center;justify-content:center;white-space:normal;text-align:center;padding:.42rem .5rem}
.intel-section{padding:3.4rem 0}
.intel-copy{padding:1.4rem}
.intel-visual{min-height:280px}
.intel-node{font-size:.62rem;padding:.55rem .65rem}
.intel-node.four{display:none}
.intel-cards{grid-template-columns:1fr}
.intel-card+.intel-card{border-left:0;border-top:1px solid rgba(7,9,20,.14)}
.radar-metrics{grid-template-columns:1fr}
.event-intro-copy{padding-left:1rem}
.grid{grid-template-columns:1fr}
.card{min-height:0}
}
@media(prefers-reduced-motion:reduce){
.signal-feed span,.signal-strip::before,.intel-visual::before,.intel-visual::after{animation:none!important}
[data-reveal]{opacity:1!important;transform:none!important}
}
"""

_CSS += """
.hero{min-height:clamp(720px,94dvh,920px)}
.hero-body{max-width:min(900px,60vw);padding:clamp(5.2rem,10vh,7.4rem) 0 2.8rem}
.hero h1{font-size:clamp(3.9rem,7.4vw,6.65rem);line-height:.9}
.hero-sub{max-width:680px;margin-top:1.35rem;margin-bottom:2.05rem}
.hero-actions{gap:1rem}
.hero-panel{margin-top:2.35rem;max-width:900px;padding:1.05rem;display:grid;grid-template-columns:minmax(180px,.95fr) minmax(280px,1.35fr) minmax(210px,1fr);gap:1rem;align-items:stretch}
.panel-kicker{grid-column:1/-1;margin-bottom:-.35rem}
.panel-status{align-self:stretch;min-height:96px;padding:.8rem;border:1px solid rgba(255,255,255,.1);border-radius:8px;background:rgba(255,255,255,.035)}
.panel-status small{display:block;margin:.45rem 0 0;color:rgba(255,255,255,.54);line-height:1.35}
.stats-row{margin:0;height:100%;grid-template-columns:repeat(3,minmax(0,1fr))}
.stat{display:flex;flex-direction:column;justify-content:center;min-height:96px}
.panel-links{margin:0;grid-template-columns:1fr}
.panel-link,.panel-metric{min-height:44px}
.flow-bridge{position:relative;background:linear-gradient(180deg,#070914 0%,#0a0e1a 48%,#f2eee5 48.2%,#f2eee5 100%);overflow:hidden}
.flow-bridge::before{content:'';position:absolute;left:50%;top:0;bottom:0;width:1px;background:linear-gradient(180deg,rgba(69,105,255,.1),rgba(69,240,209,.75),rgba(7,9,20,.12));box-shadow:0 0 28px rgba(69,240,209,.24)}
.flow-inner{position:relative;max-width:1200px;margin:0 auto;padding:3.2rem 1.5rem 3.6rem;display:grid;grid-template-columns:1fr auto 1fr;gap:1rem;align-items:center}
.flow-line{height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.18))}
.flow-line:last-child{background:linear-gradient(90deg,rgba(7,9,20,.18),transparent)}
.flow-card{min-width:min(420px,80vw);padding:1rem 1.15rem;border:1px solid rgba(255,255,255,.14);border-radius:8px;background:rgba(7,10,22,.74);box-shadow:0 28px 80px rgba(2,3,10,.34);color:#f6f4ef}
.flow-card span{display:block;font-family:'JetBrains Mono','Inter',monospace;font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:.12em;color:#45f0d1}
.flow-card strong{display:block;margin-top:.35rem;font-family:'Space Grotesk','Inter',sans-serif;font-size:1.15rem;letter-spacing:-.02em}
.intel-section{padding:5.8rem 0 6.4rem;border-top:0}
.intel-grid{gap:clamp(1.8rem,4vw,4rem);align-items:center}
.intel-copy{background:rgba(255,255,255,.56);box-shadow:0 30px 90px rgba(7,9,20,.06)}
.intel-visual{min-height:520px;padding:1.15rem;display:flex;flex-direction:column;gap:1rem;background:linear-gradient(135deg,#050814 0%,#0b1020 55%,#071a23 100%);border-color:rgba(255,255,255,.12)}
.intel-visual::before{inset:0;border:0;background:linear-gradient(90deg,rgba(255,255,255,.06) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.045) 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(180deg,#000,transparent 92%);opacity:.44;animation:none}
.intel-visual::after{display:none}
.intel-orbit,.radar-core,.radar-metrics{display:none}
.pipe-topline{position:relative;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.85rem .9rem;border:1px solid rgba(255,255,255,.12);border-radius:8px;background:rgba(255,255,255,.045);font-family:'JetBrains Mono','Inter',monospace;text-transform:uppercase;letter-spacing:.08em}
.pipe-topline span{font-size:.66rem;color:#45f0d1;font-weight:800}
.pipe-topline strong{font-size:.68rem;color:rgba(246,244,239,.72)}
.pipe-map{position:relative;z-index:1;flex:1;display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.65rem;align-items:center;padding:1.2rem .25rem}
.pipe-map::before{content:'';position:absolute;left:7%;right:7%;top:50%;height:2px;background:linear-gradient(90deg,rgba(69,105,255,.18),rgba(69,240,209,.9),rgba(217,119,6,.58));box-shadow:0 0 26px rgba(69,240,209,.22)}
.pipe-node{position:relative;z-index:1;min-height:142px;padding:.95rem;border:1px solid rgba(255,255,255,.14);border-radius:8px;background:rgba(255,255,255,.07);box-shadow:0 20px 60px rgba(0,0,0,.22);backdrop-filter:blur(14px)}
.pipe-node:nth-child(even){transform:translateY(28px)}
.pipe-node:nth-child(3){transform:translateY(-22px);border-color:rgba(69,240,209,.48);box-shadow:0 0 0 1px rgba(69,240,209,.12),0 24px 70px rgba(69,240,209,.08)}
.pipe-node small,.pipe-console span{display:block;font-family:'JetBrains Mono','Inter',monospace;font-size:.62rem;text-transform:uppercase;letter-spacing:.1em;color:rgba(246,244,239,.44);font-weight:800}
.pipe-node b{display:block;margin:.7rem 0 .55rem;font-family:'JetBrains Mono','Inter',monospace;font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:#f6f4ef}
.pipe-node em{display:block;font-style:normal;color:rgba(246,244,239,.62);font-size:.78rem;line-height:1.45}
.pipe-node::after{content:'';position:absolute;left:50%;top:50%;width:9px;height:9px;transform:translate(-50%,-50%);border-radius:50%;background:#45f0d1;box-shadow:0 0 24px rgba(69,240,209,.72)}
.pipe-console{position:relative;z-index:1;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;border:1px solid rgba(255,255,255,.12);border-radius:8px;overflow:hidden;background:rgba(255,255,255,.12)}
.pipe-console div{background:rgba(2,3,10,.58);padding:.85rem .9rem;color:#f6f4ef}
.pipe-console strong{display:block;margin-top:.25rem;font-size:.92rem}
.event-deck{padding-top:1rem}
.event-intro{padding:5.4rem 0 3rem;gap:clamp(1.4rem,4vw,4rem);align-items:center}
.event-intro-copy{padding-left:1.6rem}
.event-metric::after{right:1rem;left:1rem;bottom:1rem;width:auto;height:3px;border:0;border-radius:99px;background:linear-gradient(90deg,#4569ff,#18c2a5,#d97706)}
@media(max-width:1100px){
.hero-body{max-width:760px}
.hero-panel{grid-template-columns:1fr}
.panel-kicker{margin-bottom:0}
.panel-links{grid-template-columns:repeat(2,minmax(0,1fr))}
.pipe-map{grid-template-columns:1fr;gap:.55rem;padding:.4rem 0}
.pipe-map::before{left:50%;right:auto;top:5%;bottom:5%;height:auto;width:2px}
.pipe-node,.pipe-node:nth-child(even),.pipe-node:nth-child(3){transform:none;min-height:0}
}
@media(max-width:900px){
.flow-inner{grid-template-columns:1fr;padding:2.6rem 1.5rem}
.flow-line{display:none}
.intel-section{padding:4.2rem 0 4.8rem}
.intel-visual{min-height:0}
.pipe-console{grid-template-columns:1fr}
}
@media(max-width:560px){
.hero{min-height:760px}
.hero-body{max-width:100%;padding:3rem 0 1.35rem}
.hero h1{font-size:3.05rem;line-height:.94}
.hero-sub{margin-top:1rem;margin-bottom:1.45rem}
.hero-panel{margin-top:1.55rem;padding:.85rem}
.panel-status{min-height:0}
.panel-links{grid-template-columns:1fr}
.flow-card{min-width:0;width:100%}
.intel-cards{grid-template-columns:1fr}
.event-intro{padding:3.5rem 0 2.2rem}
}
@media(prefers-reduced-motion:reduce){
.pipe-node{transform:none!important}
}
"""

_CSS += """
.pipe-map{grid-template-columns:1fr;gap:.55rem;align-items:stretch;padding:.35rem 0}
.pipe-map::before{left:1.35rem;right:auto;top:.75rem;bottom:.75rem;width:2px;height:auto;background:linear-gradient(180deg,rgba(69,105,255,.22),rgba(69,240,209,.95),rgba(217,119,6,.56))}
.pipe-node,.pipe-node:nth-child(even),.pipe-node:nth-child(3){display:grid;grid-template-columns:3.5rem minmax(5.5rem,.35fr) minmax(0,1fr);gap:.8rem;align-items:start;min-height:0;padding:.8rem .95rem .8rem 3.25rem;transform:none}
.pipe-node small{position:absolute;left:.9rem;top:.92rem}
.pipe-node b{margin:.05rem 0 0}
.pipe-node em{font-size:.8rem}
.pipe-node::after{left:1.35rem}
.review-page .hero{min-height:clamp(480px,62dvh,620px)}
.review-page .hero-body{padding:clamp(4rem,8vh,5.2rem) 0 2.4rem}
@media(max-width:560px){
.pipe-node,.pipe-node:nth-child(even),.pipe-node:nth-child(3){grid-template-columns:1fr;padding:2.2rem .9rem .9rem 2.7rem;gap:.35rem}
.review-page .hero{min-height:520px}
}
"""

_CSS += """
body{background:#02030a;color:#f6f4ef}
body::before{background:
radial-gradient(circle at 76% 10%,rgba(69,105,255,.28),transparent 31rem),
radial-gradient(circle at 18% 22%,rgba(69,240,209,.16),transparent 24rem),
linear-gradient(180deg,#02030a 0%,#030610 38%,#07101c 66%,#02030a 100%)}
.hero{background:#02030a}
.hero-bg{background:transparent!important}
.hero::before{background:
radial-gradient(circle at 66% 36%,rgba(69,105,255,.24),transparent 24rem),
radial-gradient(circle at 82% 64%,rgba(69,240,209,.13),transparent 18rem),
linear-gradient(90deg,rgba(2,3,10,.98) 0%,rgba(2,3,10,.8) 38%,rgba(2,3,10,.38) 100%)!important;opacity:1!important;filter:none!important}
.hero::after{height:30%;background:linear-gradient(180deg,rgba(2,3,10,0),#02030a 88%)}
.signal-canvas{opacity:1;mix-blend-mode:screen}
.hero-grid{opacity:.1}
.hero-panel,.stat,.panel-link,.panel-metric,.panel-status{background:rgba(255,255,255,.045);border-color:rgba(255,255,255,.12)}
.flow-bridge{background:#02030a;border-top:1px solid rgba(255,255,255,.08);border-bottom:1px solid rgba(255,255,255,.08)}
.flow-bridge::before{background:linear-gradient(180deg,rgba(69,105,255,.1),rgba(69,240,209,.75),rgba(69,105,255,.1))}
.flow-line,.flow-line:last-child{background:linear-gradient(90deg,transparent,rgba(69,240,209,.28),transparent)}
.flow-card{background:rgba(7,10,22,.86);border-color:rgba(255,255,255,.14)}
.intel-section,.event-deck,main.container{background:#02030a;color:#f6f4ef}
.intel-section::before,.event-deck::before{background:
linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px),
linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),
radial-gradient(circle at 72% 18%,rgba(69,105,255,.18),transparent 24rem),
radial-gradient(circle at 20% 72%,rgba(69,240,209,.09),transparent 22rem);background-size:56px 56px,56px 56px,auto,auto;mask-image:linear-gradient(180deg,#000 0%,#000 72%,transparent 100%)}
.intel-copy{background:rgba(7,10,22,.68);border-color:rgba(255,255,255,.13);box-shadow:0 28px 90px rgba(0,0,0,.24);backdrop-filter:blur(18px)}
.intel-copy h2,.event-intro h2,.section-title,.card-title{color:#f6f4ef}
.intel-copy p,.event-intro p,.card-desc{color:rgba(246,244,239,.68)}
.intel-card{background:rgba(255,255,255,.055);border-color:rgba(255,255,255,.1)}
.intel-card b{color:#f6f4ef}
.intel-card span{color:rgba(246,244,239,.62)}
.intel-cards{background:rgba(255,255,255,.1);border-color:rgba(255,255,255,.13)}
.intel-visual{box-shadow:0 28px 90px rgba(0,0,0,.34),inset 0 0 0 1px rgba(255,255,255,.04)}
.event-intro-copy{border-left-color:#45f0d1}
.event-metrics{background:rgba(255,255,255,.1);border-color:rgba(255,255,255,.14);box-shadow:0 28px 90px rgba(0,0,0,.24)}
.event-metric{background:rgba(255,255,255,.055)}
.event-metric span,.event-metric small,.section-count{color:rgba(246,244,239,.5)}
.event-metric strong{color:#f6f4ef}
.section-header{border-color:rgba(255,255,255,.14)}
.grid{gap:1rem}
.card{background:rgba(255,255,255,.065);border-color:rgba(255,255,255,.13);box-shadow:0 28px 90px rgba(0,0,0,.22)}
.card:hover{border-color:rgba(69,240,209,.38)}
.card-footer{border-color:rgba(255,255,255,.12)}
.card-title a{color:#f6f4ef}
.meta-item,.source-dot{color:rgba(246,244,239,.55)}
.issue-link{background:rgba(255,255,255,.07);border-color:rgba(255,255,255,.13);color:rgba(246,244,239,.74)}
.issue-link:hover{background:rgba(69,105,255,.16);border-color:rgba(69,105,255,.5);color:#fff}
.date-badge{background:#050814;border:1px solid rgba(255,255,255,.1)}
.toolbar-wrap{background:rgba(2,3,10,.92)}
.empty-state{color:rgba(246,244,239,.62)}
.empty-state h3{color:#f6f4ef}
.review-list,.review-card{color:#f6f4ef}
.review-card{background:rgba(255,255,255,.065);border-color:rgba(255,255,255,.13)}
.review-title{color:#f6f4ef}
.review-reason{color:rgba(246,244,239,.68)}
@media(max-width:560px){
.hero::before{background:
radial-gradient(circle at 66% 34%,rgba(69,105,255,.26),transparent 16rem),
radial-gradient(circle at 88% 58%,rgba(69,240,209,.14),transparent 14rem),
linear-gradient(90deg,rgba(2,3,10,.98),rgba(2,3,10,.68))!important}
}
"""

_CSS += """
.flow-bridge{border:0;background:linear-gradient(180deg,rgba(2,3,10,.08),rgba(4,8,18,.86) 52%,rgba(2,3,10,.08));margin-top:-1px}
.flow-bridge::before{left:50%;width:1px;background:linear-gradient(180deg,transparent,rgba(69,240,209,.9),transparent);box-shadow:0 0 42px rgba(69,240,209,.32)}
.flow-inner{min-height:156px;padding:2.1rem 1.5rem 2.3rem}
.flow-line,.flow-line:last-child{opacity:.42;background:linear-gradient(90deg,transparent,rgba(69,240,209,.28),transparent)}
.flow-card{min-width:0;width:min(410px,82vw);background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(69,105,255,.055));border-color:rgba(255,255,255,.12);box-shadow:0 18px 70px rgba(0,0,0,.2);backdrop-filter:blur(18px)}
.intel-section{margin-top:-1px;padding-top:4.7rem}
.intel-section::before,.event-deck::before{opacity:.82;mask-image:linear-gradient(180deg,transparent 0%,#000 15%,#000 78%,transparent 100%)}
.intel-grid,.event-intro,.section-header,.grid{max-width:1200px;margin-left:auto;margin-right:auto}
.intel-copy,.intel-visual,.event-metrics,.card{background:linear-gradient(135deg,rgba(255,255,255,.075),rgba(255,255,255,.04));border-color:rgba(255,255,255,.115)}
.intel-visual{background:radial-gradient(circle at 54% 28%,rgba(69,105,255,.2),transparent 18rem),radial-gradient(circle at 72% 78%,rgba(69,240,209,.1),transparent 16rem),linear-gradient(135deg,#050814,#08111e 68%,#06151a)}
.pipe-node{background:rgba(255,255,255,.055);border-color:rgba(255,255,255,.11)}
.event-deck{padding-top:0}
.event-intro{padding-top:4.7rem}
.section-header{background:linear-gradient(90deg,rgba(255,255,255,.055),rgba(255,255,255,.02));border:1px solid rgba(255,255,255,.11);border-radius:8px;padding:1rem 1.1rem;margin-bottom:1rem}
.card{min-height:340px}
@media(max-width:900px){
.flow-inner{min-height:124px;padding:1.8rem 1.5rem}
.intel-section{padding-top:3.6rem}
.event-intro{padding-top:3.7rem}
}
@media(max-width:560px){
.flow-card{width:100%}
.section-header{padding:.9rem}
}
"""

_CSS += """
html{background:#02030a;scroll-behavior:smooth}
body{background:#02030a!important;color:#f6f4ef;overflow-x:hidden}
body::before{background:
radial-gradient(circle at 70% 12%,rgba(69,105,255,.22),transparent 30rem),
radial-gradient(circle at 20% 36%,rgba(69,240,209,.13),transparent 24rem),
linear-gradient(180deg,#02030a 0%,#030713 38%,#050b17 68%,#02030a 100%)!important}
.hero{min-height:100dvh;background:#02030a!important}
.hero::before{background:
radial-gradient(circle at 66% 36%,rgba(69,105,255,.24),transparent 25rem),
radial-gradient(circle at 84% 62%,rgba(69,240,209,.12),transparent 20rem),
linear-gradient(90deg,rgba(2,3,10,.98) 0%,rgba(2,3,10,.82) 38%,rgba(2,3,10,.34) 100%)!important}
.hero-body{max-width:min(980px,72vw)}
.kinetic-title{position:relative;display:flex;flex-wrap:wrap;align-items:flex-start;gap:0 .12em;max-width:980px;perspective:900px;isolation:isolate}
.kinetic-title .title-network{position:absolute;inset:-.1em -.06em;z-index:-1;width:100%;height:100%;pointer-events:none;opacity:.9;mix-blend-mode:screen}
.kinetic-title .title-word{display:inline-flex;white-space:nowrap}
.kinetic-title .title-char{display:inline-block;transform:translate3d(var(--tx,0),var(--ty,0),0) scale(var(--s,1));transform-origin:50% 64%;opacity:var(--o,1);color:var(--c,#fff);text-shadow:0 0 var(--glow,16px) rgba(69,105,255,.42);will-change:transform,opacity,text-shadow}
.kinetic-title .title-char:nth-child(3n){--c:#eef2ff}
.kinetic-title .title-char:nth-child(5n){--c:#dce6ff}
.flow-bridge{min-height:32dvh;border:0!important;background:linear-gradient(180deg,#02030a 0%,#030713 48%,#02030a 100%)!important}
.flow-inner{min-height:32dvh;padding:3.4rem 1.5rem;align-items:center}
.flow-card{position:relative;overflow:hidden}
.flow-card::after{content:'';position:absolute;inset:auto 0 0;height:2px;background:linear-gradient(90deg,transparent,#45f0d1,#4569ff,transparent);animation:hmFlowPulse 2.8s ease-in-out infinite}
.intel-section,.event-deck,main.container{background:#02030a!important;color:#f6f4ef!important}
.intel-section{min-height:100dvh;display:flex;align-items:center;margin-top:-1px;padding:6rem 0}
.intel-section::before,.event-deck::before{opacity:.78;background:
linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px),
linear-gradient(rgba(255,255,255,.028) 1px,transparent 1px),
radial-gradient(circle at 70% 18%,rgba(69,105,255,.18),transparent 24rem),
radial-gradient(circle at 24% 70%,rgba(69,240,209,.09),transparent 22rem)!important;background-size:56px 56px,56px 56px,auto,auto}
.intel-grid{width:100%;align-items:center}
.intel-copy,.intel-visual,.event-metrics,.card,.section-header{background:linear-gradient(135deg,rgba(255,255,255,.075),rgba(255,255,255,.035))!important;border-color:rgba(255,255,255,.12)!important}
.intel-copy{box-shadow:0 30px 110px rgba(0,0,0,.28)!important}
.intel-copy h2,.event-intro h2,.section-title,.card-title,.card-title a{color:#f6f4ef!important}
.intel-copy p,.event-intro p,.card-desc,.meta-item,.source-dot{color:rgba(246,244,239,.68)!important}
.intel-card{background:rgba(255,255,255,.055)!important}
.intel-card b{color:#f6f4ef!important}
.intel-card span{color:rgba(246,244,239,.64)!important}
.intel-visual{box-shadow:0 30px 120px rgba(0,0,0,.36),inset 0 0 0 1px rgba(255,255,255,.04)!important}
.pipe-map{--pipe-progress:0%;position:relative}
.pipe-map::before{opacity:.36}
.pipe-map::after{content:'';position:absolute;left:1.35rem;top:.75rem;width:2px;height:var(--pipe-progress);max-height:calc(100% - 1.5rem);border-radius:99px;background:linear-gradient(180deg,#4569ff,#45f0d1,#d97706);box-shadow:0 0 32px rgba(69,240,209,.42);transition:height .18s ease-out;z-index:1}
.pipe-node,.pipe-node:nth-child(even),.pipe-node:nth-child(3){opacity:.48;transform:translate3d(-10px,12px,0) scale(.985)!important;transition:opacity .42s ease,transform .42s ease,border-color .42s ease,box-shadow .42s ease,background .42s ease}
.pipe-node.is-active{opacity:1;transform:translate3d(0,0,0) scale(1)!important;border-color:rgba(69,240,209,.48)!important;background:linear-gradient(135deg,rgba(69,240,209,.12),rgba(255,255,255,.07))!important;box-shadow:0 20px 70px rgba(69,240,209,.1)!important}
.pipe-node.is-active::after{background:#45f0d1;box-shadow:0 0 30px rgba(69,240,209,.92)}
.event-deck{min-height:100dvh;padding-bottom:5.6rem}
.event-intro{min-height:72dvh;align-items:center;padding-top:5.2rem}
.toolbar-wrap{background:rgba(2,3,10,.88)!important;border-top:1px solid rgba(255,255,255,.08);border-bottom:1px solid rgba(255,255,255,.08)}
.search-box input{background:rgba(255,255,255,.07)!important;color:#fff!important;border-color:rgba(255,255,255,.14)!important}
.search-box input::placeholder{color:rgba(246,244,239,.52)!important}
.pill{background:rgba(255,255,255,.065)!important;color:rgba(246,244,239,.78)!important;border-color:rgba(255,255,255,.12)!important}
.pill.active{background:#4569ff!important;color:#fff!important;border-color:#4569ff!important}
@keyframes hmFlowPulse{0%,100%{transform:translateX(-35%);opacity:.35}50%{transform:translateX(35%);opacity:1}}
@media(max-width:900px){
.hero-body{max-width:760px}
.kinetic-title{max-width:100%}
.intel-section{padding:4.2rem 0;min-height:auto}
.event-intro{min-height:auto}
}
@media(max-width:560px){
.hero{min-height:100dvh}
.hero-body{max-width:100%}
.kinetic-title .title-network{opacity:.58}
.signal-canvas{opacity:.82}
.flow-bridge,.flow-inner{min-height:24dvh}
.intel-section{padding:3.4rem 0}
}
@media(prefers-reduced-motion:reduce){
.kinetic-title .title-char{transform:none!important}
.kinetic-title .title-network{display:none}
.flow-card::after{animation:none}
.pipe-map::after{transition:none}
.pipe-node,.pipe-node:nth-child(even),.pipe-node:nth-child(3){opacity:1;transform:none!important}
}
"""

_CSS += """
html{scroll-snap-type:y proximity}
.hero,.intel-section,.event-deck{scroll-snap-align:start;scroll-snap-stop:normal}
.hero{--hero-morph:.5}
.hero::after{height:38%;background:linear-gradient(180deg,rgba(2,3,10,0),rgba(2,3,10,.9) 72%,#02030a)}
.hero-scanline{transform:translateY(calc(var(--hero-morph, .5) * -18px));opacity:calc(.55 + var(--hero-morph, .5) * .45);transition:opacity .2s linear,transform .2s linear}
.hero-panel{transform:translateY(calc(var(--hero-morph, .5) * -8px));transition:transform .18s linear}
.signal-canvas{filter:saturate(calc(1.05 + var(--hero-morph, .5) * .45)) contrast(calc(1.02 + var(--hero-morph, .5) * .18))}
.flow-bridge{min-height:44dvh}
.flow-inner{min-height:44dvh}
.flow-card{transform:translateY(calc((1 - var(--story-progress, 0)) * 20px)) scale(calc(.96 + var(--story-progress, 0) * .04));opacity:calc(.56 + var(--story-progress, 0) * .44);transition:none}
.intel-section{min-height:176dvh;align-items:flex-start;padding:0}
.intel-grid{position:sticky;top:0;min-height:100dvh;padding-top:clamp(2.2rem,6vh,4.6rem);padding-bottom:clamp(2.2rem,6vh,4.6rem);align-items:center}
.intel-copy{transform:translate3d(calc((.5 - var(--scene01-progress, 0)) * 28px),calc((.35 - var(--scene01-progress, 0)) * 20px),0);transition:none}
.intel-visual{transform:translate3d(0,calc((.5 - var(--scene01-progress, 0)) * -22px),0) scale(calc(.97 + var(--scene01-progress, 0) * .03));transition:none}
.pipe-topline{box-shadow:inset 0 -1px 0 rgba(69,240,209,calc(.15 + var(--scene01-progress, 0) * .35))}
.pipe-node{--node-lift:0px}
.pipe-node.is-active{--node-lift:-4px}
.pipe-node,.pipe-node:nth-child(even),.pipe-node:nth-child(3){transform:translate3d(calc((1 - var(--scene01-progress, 0)) * -16px),calc(12px + var(--node-lift)),0) scale(calc(.982 + var(--scene01-progress, 0) * .018))!important}
.pipe-node.is-active b{color:#fff}
.pipe-node.is-active em{color:rgba(246,244,239,.82)}
.event-deck{--scene02-progress:0;min-height:142dvh;padding-top:0}
.event-intro{position:relative;min-height:88dvh;transform:translateY(calc((1 - var(--scene02-progress, 0)) * 28px));opacity:calc(.72 + var(--scene02-progress, 0) * .28);transition:none}
.event-metric{transform:translateY(calc((1 - var(--scene02-progress, 0)) * 22px));transition:transform .18s linear,opacity .18s linear}
.event-metric:nth-child(2){transition-delay:.04s}
.event-metric:nth-child(3){transition-delay:.08s}
.grid .card{opacity:0;transform:translateY(34px) scale(.985);transition:opacity .48s ease,transform .48s ease,border-color .25s ease,box-shadow .25s ease}
.grid .card.is-visible-card{opacity:1;transform:translateY(0) scale(1)}
.grid .card.is-visible-card:nth-child(2){transition-delay:.06s}
.grid .card.is-visible-card:nth-child(3){transition-delay:.12s}
@media(max-width:900px){
html{scroll-snap-type:none}
.intel-section{min-height:auto;padding:4rem 0}
.intel-grid{position:relative;min-height:auto;padding-top:0;padding-bottom:0}
.intel-copy,.intel-visual,.event-intro{transform:none}
.event-deck{min-height:auto}
.grid .card{opacity:1;transform:none}
}
@media(prefers-reduced-motion:reduce){
html{scroll-snap-type:none}
.hero-scanline,.hero-panel,.signal-canvas,.flow-card,.intel-copy,.intel-visual,.pipe-node,.event-intro,.event-metric,.grid .card{transform:none!important;transition:none!important;opacity:1!important;filter:none!important}
}
"""

_JS += """
(function(){
var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if('scrollRestoration'in history){history.scrollRestoration='manual'}
if(!location.hash){
  window.scrollTo(0,0);
  window.addEventListener('pageshow',function(){requestAnimationFrame(function(){window.scrollTo(0,0)})});
}
var title=document.getElementById('hero-title');
if(title){
  var label=title.getAttribute('aria-label')||title.textContent.trim();
  title.textContent='';
  title.setAttribute('aria-label',label);
  var titleCanvas=document.createElement('canvas');
  titleCanvas.className='title-network';
  titleCanvas.setAttribute('aria-hidden','true');
  title.appendChild(titleCanvas);
  var charList=[],words=label.split(' ');
  words.forEach(function(word,wi){
    var wordEl=document.createElement('span');
    wordEl.className='title-word';
    word.split('').forEach(function(ch){
      var c=document.createElement('span');
      c.className='title-char';
      c.setAttribute('aria-hidden','true');
      c.textContent=ch;
      wordEl.appendChild(c);
      charList.push(c);
    });
    title.appendChild(wordEl);
    if(wi<words.length-1){
      var spacer=document.createElement('span');
      spacer.className='title-space';
      spacer.setAttribute('aria-hidden','true');
      spacer.textContent=' ';
      title.appendChild(spacer);
    }
  });
  var titleCtx=titleCanvas.getContext('2d');
  function drawTitle(now){
    var rect=title.getBoundingClientRect(),dpr=Math.min(window.devicePixelRatio||1,2);
    if(rect.width>0&&rect.height>0){
      titleCanvas.width=Math.floor(rect.width*dpr);
      titleCanvas.height=Math.floor(rect.height*dpr);
      titleCtx.setTransform(dpr,0,0,dpr,0,0);
      titleCtx.clearRect(0,0,rect.width,rect.height);
      titleCtx.globalCompositeOperation='lighter';
      var t=now*.001,breath=Math.sin(t*1.05),centers=[];
      charList.forEach(function(ch,i){
        var phase=i*.47;
        var wave=Math.sin(t*1.8+phase);
        var drift=Math.cos(t*1.15+phase*.7);
        var tx=(wave*2.4)+(breath*(i%2===0?1.35:-1.35));
        var ty=(drift*3.1)+(Math.sin(t*.8+i*.21)*1.15);
        var scale=1+Math.sin(t*1.55+phase)*.024+breath*.008;
        ch.style.setProperty('--tx',tx.toFixed(2)+'px');
        ch.style.setProperty('--ty',ty.toFixed(2)+'px');
        ch.style.setProperty('--s',scale.toFixed(3));
        ch.style.setProperty('--o',(0.88+Math.max(0,wave)*.12).toFixed(2));
        ch.style.setProperty('--glow',(14+Math.max(0,wave)*24).toFixed(1)+'px');
        var cr=ch.getBoundingClientRect();
        centers.push({x:cr.left-rect.left+cr.width/2+tx,y:cr.top-rect.top+cr.height*.58+ty,p:phase});
      });
      for(var a=0;a<centers.length;a++){
        for(var b=a+1;b<centers.length;b++){
          var ca=centers[a],cb=centers[b],dx=ca.x-cb.x,dy=ca.y-cb.y,dist=Math.sqrt(dx*dx+dy*dy);
          if(dist<92&&((b-a)%3===1||dist<48)){
            var alpha=(1-dist/92)*(.22+.12*Math.sin(t*2+ca.p));
            titleCtx.strokeStyle='rgba(69,240,209,'+Math.max(0,alpha).toFixed(3)+')';
            titleCtx.lineWidth=.8;
            titleCtx.beginPath();
            titleCtx.moveTo(ca.x,ca.y);
            titleCtx.lineTo(cb.x,cb.y);
            titleCtx.stroke();
          }
        }
      }
      centers.forEach(function(c,i){
        titleCtx.fillStyle=i%5===0?'rgba(69,240,209,.85)':'rgba(229,235,255,.45)';
        titleCtx.beginPath();
        titleCtx.arc(c.x,c.y,1.4+(i%3)*.45,0,Math.PI*2);
        titleCtx.fill();
      });
    }
    if(!reduce)requestAnimationFrame(drawTitle);
  }
  drawTitle(0);
}
var sceneState={hero:0,story:0,one:0,two:0};
var canvas=document.getElementById('signal-canvas');
if(canvas&&canvas.getContext){
var ctx=canvas.getContext('2d'),dpr=1,pts=[],mouse={x:0,y:0,active:false},lastMorph=.5;
function humanTarget(i,count,w,h){
  var cx=w*(w<700?.76:.72),base=Math.min(w,h),headR=base*.075,headY=h*(w<700?.33:.27),shoulderY=h*(w<700?.45:.39),hipY=h*(w<700?.65:.59),footY=h*(w<700?.82:.78);
  var headCount=Math.floor(count*.22),torsoCount=Math.floor(count*.24),armCount=Math.floor(count*.24),legCount=Math.floor(count*.22);
  var local=i;
  if(local<headCount){
    var a=local/headCount*Math.PI*2;
    return {x:cx+Math.cos(a)*headR*(.82+Math.sin(a*3)*.08),y:headY+Math.sin(a)*headR};
  }
  local-=headCount;
  if(local<torsoCount){
    var u=local/Math.max(1,torsoCount-1),side=local%2===0?-1:1,width=base*(.105-.038*u);
    return {x:cx+side*width+Math.sin(u*Math.PI*2)*5,y:shoulderY+(hipY-shoulderY)*u};
  }
  local-=torsoCount;
  if(local<armCount){
    var au=local/Math.max(1,armCount-1),left=local%2===0,dir=left?-1:1;
    return {x:cx+dir*(base*.1+base*.18*au),y:shoulderY+base*.13*au+Math.sin(au*Math.PI)*base*.035};
  }
  local-=armCount;
  if(local<legCount){
    var lu=local/Math.max(1,legCount-1),lleft=local%2===0,ldir=lleft?-1:1;
    return {x:cx+ldir*(base*.035+base*.11*lu),y:hipY+(footY-hipY)*lu};
  }
  var p=(local/(count-headCount-torsoCount-armCount-legCount||1))*Math.PI*2;
  return {x:cx+Math.cos(p)*base*.055,y:h*.49+Math.sin(p*1.7)*base*.12};
}
function graphTarget(i,count,w,h){
  var t=i/count,band=i%5,angle=t*Math.PI*10+band*.35;
  var radius=(.16+.26*Math.sin(t*Math.PI))*Math.min(w,h);
  var stream=Math.max(0,t-.58)*w*.58;
  return {
    x:w*(.56+.05*Math.sin(t*11))+Math.cos(angle)*radius*.62+stream,
    y:h*(.43+.08*Math.cos(t*7))+Math.sin(angle)*radius*.44+(band-2)*10
  };
}
function build(){
  dpr=Math.min(window.devicePixelRatio||1,2);
  var r=canvas.getBoundingClientRect();
  canvas.width=Math.max(1,Math.floor(r.width*dpr));
  canvas.height=Math.max(1,Math.floor(r.height*dpr));
  ctx.setTransform(dpr,0,0,dpr,0,0);
  var w=r.width,h=r.height,count=w<700?170:310;
  pts=[];
  for(var i=0;i<count;i++){
    var g=graphTarget(i,count,w,h),human=humanTarget(i,count,w,h);
    pts.push({x:g.x+(Math.random()-.5)*58,y:g.y+(Math.random()-.5)*58,gx:g.x,gy:g.y,hx:human.x,hy:human.y,s:.8+Math.random()*1.9,p:Math.random()*6.28});
  }
}
function drawHumanGuide(w,h,morph){
  var cx=w*(w<700?.76:.72),base=Math.min(w,h),alpha=Math.max(0,(morph-.25)/.75);
  if(alpha<=0)return;
  ctx.save();
  ctx.globalCompositeOperation='lighter';
  ctx.strokeStyle='rgba(69,240,209,'+(.08+alpha*.22)+')';
  ctx.lineWidth=1.2;
  ctx.shadowColor='rgba(69,240,209,.5)';
  ctx.shadowBlur=18*alpha;
  ctx.beginPath();
  var headY=h*(w<700?.33:.27),shoulderY=h*(w<700?.45:.39),hipY=h*(w<700?.65:.61),footY=h*(w<700?.82:.78);
  ctx.arc(cx,headY,base*.085,0,Math.PI*2);
  ctx.moveTo(cx-base*.09,shoulderY);
  ctx.bezierCurveTo(cx-base*.16,h*.48,cx-base*.09,hipY,cx,hipY);
  ctx.bezierCurveTo(cx+base*.09,hipY,cx+base*.16,h*.48,cx+base*.09,shoulderY);
  ctx.moveTo(cx-base*.1,shoulderY);ctx.lineTo(cx-base*.31,h*(w<700?.61:.55));
  ctx.moveTo(cx+base*.1,shoulderY);ctx.lineTo(cx+base*.31,h*(w<700?.61:.55));
  ctx.moveTo(cx-base*.035,hipY);ctx.lineTo(cx-base*.16,footY);
  ctx.moveTo(cx+base*.035,hipY);ctx.lineTo(cx+base*.16,footY);
  ctx.stroke();
  ctx.restore();
}
function frame(now){
  var r=canvas.getBoundingClientRect(),w=r.width,h=r.height,t=now*.001;
  ctx.clearRect(0,0,w,h);
  var cycle=(Math.sin(t*.62)+1)/2,scrollMorph=Math.max(0,Math.min(1,1-sceneState.hero));
  var morph=reduce?.45:(cycle*.72+scrollMorph*.28);
  lastMorph=morph;
  var mx=mouse.active?(mouse.x/w-.5)*34:0,my=mouse.active?(mouse.y/h-.5)*24:0;
  for(var i=0;i<pts.length;i++){
    var p=pts[i],breath=Math.sin(t*1.4+p.p);
    var tx=p.gx*(1-morph)+p.hx*morph+Math.sin(t+p.p)*8+mx*(1-morph*.5);
    var ty=p.gy*(1-morph)+p.hy*morph+Math.cos(t*.84+p.p)*7+my*(1-morph*.5);
    if(morph>.4){tx+=Math.sin(t*2.2+p.p)*morph*3;ty+=breath*morph*2.4}
    p.x+=(tx-p.x)*(.032+morph*.02);
    p.y+=(ty-p.y)*(.032+morph*.02);
  }
  ctx.globalCompositeOperation='lighter';
  for(var a=0;a<pts.length;a+=2){
    for(var b=a+1;b<Math.min(pts.length,a+(morph>.45?24:18));b+=3){
      var pa=pts[a],pb=pts[b],dx=pa.x-pb.x,dy=pa.y-pb.y,dist=Math.sqrt(dx*dx+dy*dy),limit=82+morph*34;
      if(dist<limit){
        var c=morph>.55?'69,240,209':'69,105,255';
        ctx.strokeStyle='rgba('+c+','+((1-dist/limit)*(.13+morph*.09)).toFixed(3)+')';
        ctx.lineWidth=.7+morph*.25;
        ctx.beginPath();ctx.moveTo(pa.x,pa.y);ctx.lineTo(pb.x,pb.y);ctx.stroke();
      }
    }
  }
  drawHumanGuide(w,h,morph);
  for(var j=0;j<pts.length;j++){
    var q=pts[j],glow=.35+.35*Math.sin(t*2+q.p),size=q.s*(1+morph*.28);
    ctx.fillStyle=j%9===0||morph>.62?'rgba(69,240,209,'+(.62+glow*.3)+')':'rgba(229,235,255,'+(.32+glow*.36)+')';
    if(morph>.55){ctx.beginPath();ctx.arc(q.x,q.y,size*1.05,0,Math.PI*2);ctx.fill()}else{ctx.fillRect(q.x,q.y,size,size)}
  }
  ctx.globalCompositeOperation='source-over';
  ctx.strokeStyle='rgba(255,255,255,'+(.06+(1-morph)*.05)+')';
  ctx.lineWidth=1;ctx.beginPath();
  ctx.ellipse(w*.66,h*.43,Math.min(w,h)*(.24+morph*.05),Math.min(w,h)*(.16+morph*.03),0,0,Math.PI*2);
  ctx.stroke();
  document.querySelector('.hero')?.style.setProperty('--hero-morph',morph.toFixed(3));
  if(!reduce)requestAnimationFrame(frame);
}
build();requestAnimationFrame(frame);
window.addEventListener('resize',build,{passive:true});
window.addEventListener('pointermove',function(e){var r=canvas.getBoundingClientRect();mouse.x=e.clientX-r.left;mouse.y=e.clientY-r.top;mouse.active=true;},{passive:true});
window.addEventListener('pointerleave',function(){mouse.active=false},{passive:true});
}
var reveal=document.querySelectorAll('[data-reveal]');
if('IntersectionObserver'in window){var io=new IntersectionObserver(function(entries){entries.forEach(function(e){if(e.isIntersecting){e.target.classList.add('is-visible');io.unobserve(e.target)}})},{threshold:.18});reveal.forEach(function(el){io.observe(el)})}else{reveal.forEach(function(el){el.classList.add('is-visible')})}
var flowBridge=document.querySelector('.flow-bridge'),intelSection=document.querySelector('.intel-section'),eventDeck=document.querySelector('.event-deck');
var pipeMap=document.querySelector('.pipe-map'),pipeSteps=Array.from(document.querySelectorAll('[data-pipe-step]')),eventCards=Array.from(document.querySelectorAll('.grid .card'));
function clamp(n){return Math.max(0,Math.min(1,n))}
function progressFor(el,bias){
  if(!el)return 0;
  var r=el.getBoundingClientRect(),vh=window.innerHeight||1;
  return clamp((vh*(bias||.72)-r.top)/(r.height-vh*.18));
}
function updateScenes(){
  var hero=document.querySelector('.hero');
  sceneState.hero=progressFor(hero,.55);
  sceneState.story=progressFor(flowBridge,.76);
  sceneState.one=progressFor(intelSection,.82);
  sceneState.two=progressFor(eventDeck,.78);
  document.body.style.setProperty('--story-progress',sceneState.story.toFixed(3));
  if(intelSection)intelSection.style.setProperty('--scene01-progress',sceneState.one.toFixed(3));
  if(eventDeck)eventDeck.style.setProperty('--scene02-progress',sceneState.two.toFixed(3));
  eventCards.forEach(function(card,i){
    var r=card.getBoundingClientRect();
    card.classList.toggle('is-visible-card',r.top<(window.innerHeight*.86+i*18));
  });
}
function updatePipe(){
  updateScenes();
  if(!pipeMap||!pipeSteps.length)return;
  var r=pipeMap.getBoundingClientRect();
  var p=Math.max(0,Math.min(1,(window.innerHeight*.78-r.top)/(r.height+window.innerHeight*.18)));
  pipeMap.style.setProperty('--pipe-progress',(p*100).toFixed(1)+'%');
  pipeSteps.forEach(function(step,i){step.classList.toggle('is-active',p>=(i+.22)/pipeSteps.length)});
}
var ticking=false;
function requestPipe(){if(!ticking){ticking=true;requestAnimationFrame(function(){ticking=false;updatePipe()})}}
updatePipe();
window.addEventListener('scroll',requestPipe,{passive:true});
window.addEventListener('resize',requestPipe,{passive:true});
document.querySelectorAll('.card').forEach(function(card){
  card.addEventListener('pointermove',function(e){var r=card.getBoundingClientRect(),x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;card.style.setProperty('--mx',(x*100).toFixed(1)+'%');card.style.setProperty('--my',(y*100).toFixed(1)+'%');card.style.setProperty('--tilt-x',((x-.5)*3).toFixed(2)+'deg');card.style.setProperty('--tilt-y',((.5-y)*3).toFixed(2)+'deg')},{passive:true});
  card.addEventListener('pointerleave',function(){card.style.setProperty('--tilt-x','0deg');card.style.setProperty('--tilt-y','0deg')},{passive:true});
});
})();
"""


# ---- SVG icons ----

_SVG_SEARCH = '<svg class="search-icon" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clip-rule="evenodd"/></svg>'
_SVG_PIN = '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"/></svg>'
_SVG_CAL = '<svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd"/></svg>'


# ---- HTML builder ----

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

    cards_html = _build_cards(upcoming) if upcoming else _build_empty()
    evt_word = "eventi" if event_count != 1 else "evento"
    mon_word = "mesi" if len(months_set) != 1 else "mese"
    mon_count = str(len(months_set)) if months_set else "\u2014"
    status_label = _scan_status_label(scan_status, collector_failures)
    status_dot = "ops-dot" if status_label == "OK" else "ops-dot warn"

    html = (
        '<!DOCTYPE html>\n<html lang="it">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<meta name="description" content="{event_count} hackathon in programma a Milano e dintorni.">\n'
        '<meta property="og:title" content="Hackathon Milano">\n'
        f'<meta property="og:description" content="{event_count} hackathon in programma a Milano">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:image" content="hero-hackathon-milano.png">\n'
        '<title>Hackathon Milano</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">\n'
        f'<style>{_CSS}</style>\n'
        '</head>\n<body>\n\n'
        # Hero
        '<header class="hero">\n'
        '<div class="hero-bg"></div><div class="hero-grid"></div><canvas class="signal-canvas" id="signal-canvas" aria-hidden="true"></canvas><div class="hero-scanline" aria-hidden="true"></div>\n'
        '<div class="hero-content">\n'
        '<div class="container">\n'
        '  <nav class="topbar">\n'
        '    <div class="brand">\n'
        '      <div class="brand-mark">'
        '<svg viewBox="0 0 20 20"><path d="M10 2L2 7l8 5 8-5-8-5z"/><path d="M2 13l8 5 8-5"/><path d="M2 10l8 5 8-5"/></svg>'
        '</div>\n'
        '      <div>\n'
        '        <div class="brand-name">Hackathon Milano</div>\n'
        '        <div class="brand-city">Milano &amp; dintorni</div>\n'
        '      </div>\n'
        '    </div>\n'
        '    <a class="topbar-link" href="https://github.com/federicoogallo/Hackathon-MI" target="_blank" rel="noopener">'
        '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'
        'GitHub</a>\n'
        '  </nav>\n'
        '  <div class="hero-body">\n'
        '    <div class="hero-copy">\n'
        '      <div class="hero-eyebrow"><span></span>Live intelligence layer &middot; Milano</div>\n'
        '      <h1 id="hero-title" class="kinetic-title" aria-label="Hackathon Milano">Hackathon <em>Milano</em></h1>\n'
        '      <p class="hero-sub">Ogni fonte, segnale e candidato converge in un unico radar dinamico: la pipeline legge la scena, filtra il rumore e porta in superficie gli hackathon che contano.</p>\n'
        '      <div class="hero-actions">\n'
        '        <a class="btn-primary" href="#events">'
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 7l-5 5-5-5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        'Esplora gli eventi</a>\n'
        '        <a class="btn-secondary" href="review.html">Review queue</a>\n'
        '        <span class="hero-badge">Dati aggiornati dalla pipeline</span>\n'
        '      </div>\n'
        '      <div class="hero-panel" aria-label="Stato monitor">\n'
        '      <div class="panel-kicker">Stato monitor</div>\n'
        f'      <div class="panel-status"><span class="{status_dot}"></span><strong>{_escape(status_label)}</strong><small>{_escape(last_scan)}</small></div>\n'
        '      <div class="stats-row">\n'
        f'      <div class="stat"><div class="stat-num">{event_count}</div><div class="stat-label">{evt_word}</div></div>\n'
        + (f'      <div class="stat"><div class="stat-num">{len(months_set)}</div><div class="stat-label">{mon_word}</div></div>\n' if months_set else f'      <div class="stat"><div class="stat-num">{mon_count}</div><div class="stat-label">{mon_word}</div></div>\n')
        + '      <div class="stat"><div class="stat-num">24h</div><div class="stat-label">refresh</div></div>\n'
        '      </div>\n'
        '      <div class="panel-links">\n'
        f'        <a class="panel-link" href="review.html"><span>Candidati in review</span><strong>{review_count}</strong></a>\n'
        f'        <div class="panel-metric"><span>Errori collector</span><strong>{collector_failures}</strong></div>\n'
        '      </div>\n'
        '      </div>\n'
        '    </div>\n'
        '  </div>\n'
        '</div>\n'
        '</div>\n'
        '</header>\n\n'
        '<section class="signal-strip" aria-label="Stato del radar">\n'
        '<div class="signal-inner">\n'
        f'<strong>{event_count} eventi verificati</strong>\n'
        '<div class="signal-feed"><span>Collecting public sources / dedupe graph / AI filter / manual review / GitHub Pages output / Collecting public sources / dedupe graph / AI filter / manual review / GitHub Pages output / </span></div>\n'
        f'<strong>{review_count} in review</strong>\n'
        '</div>\n'
        '</section>\n\n'
        '<section class="flow-bridge" aria-label="Passaggio alla sezione successiva">\n'
        '<div class="flow-inner">\n'
        '<div class="flow-line"></div>\n'
        '<div class="flow-card"><span>Scroll sequence</span><strong>01 / Signal architecture</strong></div>\n'
        '<div class="flow-line"></div>\n'
        '</div>\n'
        '</section>\n\n'
        '<section class="intel-section" aria-label="Come funziona il radar">\n'
        '<div class="intel-grid">\n'
        '<div class="intel-copy" data-reveal>\n'
        '<div class="section-code">01 / Signal architecture</div>\n'
        '<h2>Dal rumore pubblico a un calendario ad alta fiducia.</h2>\n'
        '<p>Ogni evento passa dentro un flusso operativo: sorgenti pubbliche, deduplica, scoring AI e review umana convergono in un output leggibile, stabile e pronto per chi deve scegliere dove candidarsi.</p>\n'
        '<div class="intel-cards">\n'
        '<div class="intel-card"><b>Collect</b><span>Community, piattaforme eventi e ricerca web entrano in un unico flusso.</span></div>\n'
        '<div class="intel-card"><b>Dedupe</b><span>Record simili vengono compressi prima che diventino rumore visivo.</span></div>\n'
        '<div class="intel-card"><b>Reason</b><span>Il filtro AI pesa contesto, luogo, data, formato e affidabilità.</span></div>\n'
        '<div class="intel-card"><b>Publish</b><span>Solo gli eventi utili arrivano nella pagina pubblica e cercabile.</span></div>\n'
        '</div>\n'
        '</div>\n'
        '<div class="intel-visual" data-reveal aria-hidden="true">\n'
        '<div class="pipe-topline"><span>Pipeline view</span><strong>Live confidence routing</strong></div>\n'
        '<div class="pipe-map">\n'
        '<div class="pipe-node" data-pipe-step><small>01</small><b>Collect</b><em>Fonti pubbliche e community events</em></div>\n'
        '<div class="pipe-node" data-pipe-step><small>02</small><b>Dedupe</b><em>Cluster di record simili e duplicati</em></div>\n'
        '<div class="pipe-node" data-pipe-step><small>03</small><b>AI score</b><em>Luogo, data, formato e attendibilita</em></div>\n'
        '<div class="pipe-node" data-pipe-step><small>04</small><b>Review</b><em>Candidati incerti verso controllo umano</em></div>\n'
        '<div class="pipe-node" data-pipe-step><small>05</small><b>Publish</b><em>Output verificato su GitHub Pages</em></div>\n'
        '</div>\n'
        '<div class="pipe-console"><div><span>Refresh</span><strong>24h</strong></div><div><span>Scope</span><strong>Milano</strong></div><div><span>Output</span><strong>verified</strong></div></div>\n'
        '</div>\n'
        '</div>\n'
        '</section>\n\n'
        # Toolbar
        '<section class="toolbar-wrap"><div class="container toolbar">\n'
        f'  <div class="search-box"><label class="sr-only" for="search">Cerca eventi</label>{_SVG_SEARCH}<input type="text" id="search" placeholder="Cerca eventi..." autocomplete="off" aria-label="Cerca eventi"></div>\n'
        '  <div class="filter-pills" id="filters">\n'
        '    <button class="pill active" data-filter="all">Tutti</button>\n'
        '    <button class="pill" data-filter="week">Questa settimana</button>\n'
        '    <button class="pill" data-filter="month">Questo mese</button>\n'
        '    <button class="pill" data-filter="later">Prossimi mesi</button>\n'
        '  </div>\n'
        '</div></section>\n\n'
        # Main
        f'<main class="container event-deck" id="events">\n'
        '<section class="event-intro" aria-label="Eventi verificati" data-reveal>\n'
        '<div class="event-intro-copy">\n'
        '<div class="section-code">02 / Event deck</div>\n'
        '<h2>Eventi pronti da scansionare, senza attrito.</h2>\n'
        '<p>La lista sotto resta essenziale, ma ora si comporta come una console: filtri immediati, segnali di qualità, fonte visibile e azioni rapide per confermare o segnalare dubbi.</p>\n'
        '</div>\n'
        '<div class="event-metrics" aria-label="Metriche calendario">\n'
        f'<div class="event-metric"><span>Attivi</span><strong>{event_count}</strong><small>{evt_word} confermati</small></div>\n'
        f'<div class="event-metric"><span>Periodo</span><strong>{len(months_set) if months_set else mon_count}</strong><small>{mon_word} coperti dal radar</small></div>\n'
        f'<div class="event-metric"><span>Review</span><strong>{review_count}</strong><small>candidati in coda</small></div>\n'
        '</div>\n'
        '</section>\n'
        f'<div class="section-header">\n'
        f'  <span class="section-title">Prossimi eventi verificati</span>\n'
        f'  <span class="section-count" id="count-label">{event_count} eventi</span>\n'
        '</div>\n'
        '<div class="grid" id="grid">\n'
        f'{cards_html}\n'
        '</div>\n'
        '<p class="no-results" id="no-results" style="display:none">Nessun risultato trovato.</p>\n'
        '</main>\n\n'
        # Footer
        '<footer>\n<div class="container"><div class="footer-inner">\n'
        '  <div class="footer-brand">\n'
        '    <div class="footer-brand-name">Hackathon Milano</div>\n'
        '    <div class="footer-brand-desc">Dati raccolti automaticamente con AI</div>\n'
        '  </div>\n'
        f'  <div class="footer-center">Aggiornato: {_escape(last_scan)}</div>\n'
        '  <div class="footer-links">\n'
        '    <a href="https://github.com/federicoogallo/Hackathon-MI" target="_blank" rel="noopener">GitHub</a>\n'
        '  </div>\n'
        '</div></div>\n'
        '</footer>\n\n'
        f'<script>{_JS}</script>\n'
        '</body>\n</html>'
    )
    return html


def _build_cards(events: list[dict]) -> str:
    parts: list[str] = []
    arrow = (
        '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 8h10M9 4l4 4-4 4"/></svg>'
    )
    for idx, e in enumerate(events):
        title = _escape((e.get("title") or "Senza titolo").strip())
        url = _escape(e.get("url") or "#")
        location = _escape((e.get("location") or "Milano").strip())
        source = (e.get("source") or "").strip()
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
        if len(desc_raw) > 200:
            desc_raw = desc_raw[:200].rsplit(" ", 1)[0] + "..."
        desc = _escape(desc_raw)

        source_esc = _escape(source)
        issue_ok_url = _escape(_issue_url(e, "confirmed_ok"))
        issue_doubt_url = _escape(_issue_url(e, "confirmed_doubt"))

        if day and month:
            badge = (
                f'<div class="date-badge">'
                f'<span class="date-day">{day}</span>'
                f'<span class="date-month">{month}</span>'
                f'</div>'
            )
        else:
            badge = '<div class="date-badge date-tbd"><span class="date-day">TBD</span></div>'

        meta = []
        if location:
            meta.append(f'<span class="meta-item">{_SVG_PIN}{location}</span>')
        if date_compact:
            meta.append(f'<span class="meta-item">{_SVG_CAL}{_escape(date_compact)}</span>')
        meta_html = "".join(meta)

        chips = []
        if review_status == "manual_approved":
            chips.append('<span class="chip manual">Manuale</span>')
        elif confidence > 0:
            chips.append(f'<span class="chip ai">AI {int(round(confidence * 100))}%</span>')
        if not date_iso:
            chips.append('<span class="chip tbd">Data TBD</span>')
        quality_html = f'<div class="quality-row">{"".join(chips)}</div>' if chips else ""

        desc_html = f'<p class="card-desc">{desc}</p>' if desc else ""
        search_blob = _escape(f"{title} {desc} {location} {source_esc}".lower())
        delay = f"animation-delay:{idx * 0.06:.2f}s"

        parts.append(
            f'<article class="card" data-date="{date_iso}" data-search="{search_blob}" style="{delay}">'
            f'<div class="card-left">{badge}</div>'
            f'<div class="card-body">'
            f'<h2 class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>'
            f'<div class="card-meta">{meta_html}</div>'
            f'{quality_html}'
            f'{desc_html}'
            f'<div class="card-footer">'
            f'<span class="source-dot">{source_esc}</span>'
            '<div class="issue-actions">'
            f'<a href="{issue_ok_url}" class="issue-link" target="_blank" rel="noopener">Valuta OK</a>'
            f'<a href="{issue_doubt_url}" class="issue-link" target="_blank" rel="noopener">Segnala dubbio</a>'
            f'<a href="{url}" class="card-link" target="_blank" rel="noopener">Vedi evento{arrow}</a>'
            '</div>'
            f'</div></div></article>'
        )
    return "\n".join(parts)


def _build_empty() -> str:
    return (
        '<div class="empty-state">'
        '<div class="empty-icon" aria-hidden="true">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M7 3v3M17 3v3M4.5 9h15M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/>'
        '<path d="m9 14 2 2 4-4"/>'
        '</svg></div>'
        '<h3>Nessun hackathon in programma</h3>'
        '<p>Non ci sono hackathon futuri confermati a Milano al momento.<br>'
        'La lista si aggiorna ogni giorno automaticamente.</p>'
        '</div>'
    )


def _build_review_cards(candidates: list[dict]) -> str:
    if not candidates:
        return (
            '<div class="empty-state">'
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
            '<article class="review-card">'
            '<div class="review-head">'
            '<div>'
            f'<div class="review-id">{candidate_id}</div>'
            f'<h2 class="review-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>'
            f'<div class="card-meta"><span class="meta-item">{source}</span>'
            f'<span class="meta-item">{location}</span><span class="meta-item">{date_str}</span></div>'
            '</div>'
            f'<span class="chip ai">AI {confidence}%</span>'
            '</div>'
            f'<p class="review-reason">{reason}</p>'
            '<div class="issue-actions">'
            f'<a href="{issue_ok_url}" class="issue-link" target="_blank" rel="noopener">Valuta OK</a>'
            f'<a href="{issue_doubt_url}" class="issue-link" target="_blank" rel="noopener">Segnala dubbio</a>'
            f'<a href="{url}" class="card-link" target="_blank" rel="noopener">Vedi evento</a>'
            '</div>'
            '</article>'
        )
    return "\n".join(parts)


def _build_review_html(candidates: list[dict], last_scan: str) -> str:
    cards = _build_review_cards(candidates)
    count = len(candidates)
    return (
        '<!DOCTYPE html>\n<html lang="it">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<meta name="description" content="{count} candidati hackathon da rivedere.">\n'
        '<meta property="og:image" content="hero-hackathon-milano.png">\n'
        '<title>Review queue - Hackathon Milano</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">\n'
        f'<style>{_CSS}</style>\n'
        '</head>\n<body class="review-page">\n'
        '<header class="hero"><div class="hero-bg"></div><div class="hero-grid"></div>'
        '<div class="hero-content"><div class="container">'
        '<nav class="topbar"><div class="brand"><div class="brand-mark">'
        '<svg viewBox="0 0 20 20"><path d="M10 2L2 7l8 5 8-5-8-5z"/><path d="M2 13l8 5 8-5"/><path d="M2 10l8 5 8-5"/></svg>'
        '</div><div><div class="brand-name">Review queue</div>'
        '<div class="brand-city">Candidati da verificare</div></div></div>'
        '<a class="topbar-link" href="index.html">Eventi confermati</a></nav>'
        '<div class="hero-body hero-body-single"><div class="hero-copy"><div class="hero-eyebrow"><span></span>Manual review</div>'
        '<h1>Review <em>queue</em></h1>'
        f'<p class="hero-sub">{count} eventi hanno abbastanza segnale per una revisione umana. Gli utenti possono solo aprire issue di conferma/dubbio: l\'eliminazione resta ai maintainer.</p>'
        '</div></div></div></div></header>'
        '<main class="container"><div class="section-header">'
        '<span class="section-title">Da rivedere</span>'
        f'<span class="section-count">Aggiornato: {_escape(last_scan)}</span>'
        '</div><div class="review-list">'
        f'{cards}'
        '</div></main>'
        '<footer><div class="container"><div class="footer-inner">'
        '<div class="footer-brand"><div class="footer-brand-name">Hackathon Milano</div>'
        '<div class="footer-brand-desc">Review queue generata dalla pipeline</div></div>'
        '<div class="footer-center"></div><div class="footer-links">'
        '<a href="index.html">Calendario</a></div></div></div></footer>'
        '</body>\n</html>'
    )


_ELITE_CSS = """
:root{
--bg:#02040a;--bg-2:#070a13;--ink:#f7f8fb;--muted:#9aa3b8;--soft:#cfd6e8;
--line:rgba(255,255,255,.13);--line-2:rgba(255,255,255,.22);
--panel:rgba(255,255,255,.07);--panel-2:rgba(255,255,255,.11);
--blue:#6b8cff;--cyan:#42f0dd;--violet:#a58bff;--amber:#e0a84f;--green:#58e69b;
--danger:#ff6f80;--radius:8px;--z-base:0;--z-ui:10;--z-nav:30
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
[hidden]{display:none!important}
html{background:var(--bg);scroll-behavior:smooth;scrollbar-color:rgba(255,255,255,.22) var(--bg);scrollbar-width:thin}
body{min-height:100dvh;background:
linear-gradient(180deg,#02040a 0%,#050713 38%,#080c18 70%,#02040a 100%);
color:var(--ink);font-family:'Inter','Helvetica Neue',Arial,sans-serif;line-height:1.55;-webkit-font-smoothing:antialiased;overflow-x:hidden}
body *{letter-spacing:0}
a{color:inherit}
button,a,input{touch-action:manipulation}
a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid rgba(66,240,221,.7);outline-offset:3px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.elite-container{width:min(1200px,calc(100% - 48px));margin:0 auto}
.elite-shell{background:#02040a}
.elite-hero{position:relative;min-height:100dvh;overflow:hidden;isolation:isolate;border-bottom:1px solid var(--line)}
.elite-hero::before{content:'';position:absolute;inset:0;z-index:0;background:
linear-gradient(90deg,rgba(2,4,10,1) 0%,rgba(2,4,10,.88) 42%,rgba(2,4,10,.36) 100%),
linear-gradient(180deg,rgba(255,255,255,.045) 1px,transparent 1px),
linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px);
background-size:auto,72px 72px,72px 72px;mask-image:linear-gradient(180deg,#000 0%,#000 76%,transparent 100%)}
.elite-hero::after{content:'';position:absolute;inset:auto 0 0;height:28%;z-index:0;background:linear-gradient(180deg,rgba(2,4,10,0),#02040a)}
.elite-canvas,.story-canvas{position:absolute;inset:0;width:100%;height:100%;z-index:1;pointer-events:none}
.elite-nav{position:relative;z-index:var(--z-nav);display:flex;align-items:center;justify-content:space-between;min-height:92px;border-bottom:1px solid var(--line)}
.elite-brand{display:flex;align-items:center;gap:14px;text-decoration:none}
.elite-logo{width:44px;height:44px;border:1px solid var(--line-2);border-radius:8px;display:grid;place-items:center;background:linear-gradient(145deg,rgba(255,255,255,.16),rgba(255,255,255,.045));box-shadow:inset 0 1px 0 rgba(255,255,255,.14)}
.elite-logo svg{width:21px;height:21px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.elite-brand strong{display:block;font-size:1rem;font-weight:800}
.elite-brand span{display:block;color:var(--muted);font-size:.86rem}
.elite-nav-actions{display:flex;align-items:center;gap:10px}
.elite-link,.elite-button{min-height:44px;display:inline-flex;align-items:center;justify-content:center;gap:9px;border-radius:8px;border:1px solid var(--line);padding:0 16px;text-decoration:none;font-weight:800;background:rgba(255,255,255,.055);color:var(--soft);transition:background .2s ease,border-color .2s ease,transform .2s ease}
.elite-link:hover,.elite-button:hover{background:rgba(255,255,255,.1);border-color:var(--line-2);transform:translateY(-1px)}
.elite-button{background:#f7f8fb;color:#03050c;border-color:#f7f8fb}
.elite-button:hover{background:#dfe6ff;border-color:#dfe6ff}
.elite-link svg,.elite-button svg{width:17px;height:17px}
.hero-layout{position:relative;z-index:2;display:grid;grid-template-columns:minmax(0,1fr) minmax(390px,520px);gap:56px;align-items:center;min-height:calc(100dvh - 92px);padding:72px 0 80px}
.hero-kicker,.section-kicker,.micro-label{font-family:'JetBrains Mono','Inter',monospace;color:var(--cyan);font-weight:800;font-size:.86rem}
.hero-kicker{display:inline-flex;align-items:center;gap:10px;margin-bottom:24px;color:#dbe5ff}
.live-dot{width:9px;height:9px;border-radius:50%;background:var(--cyan);box-shadow:0 0 24px rgba(66,240,221,.8)}
.hero-title{font-family:'Space Grotesk','Inter',sans-serif;font-weight:700;font-size:5.8rem;line-height:.88;max-width:780px;text-wrap:balance}
.hero-title .accent{display:block;color:#dfe6ff;text-shadow:0 0 48px rgba(107,140,255,.36)}
.hero-sub{max-width:680px;margin-top:26px;color:rgba(247,248,251,.68);font-size:1.18rem;line-height:1.72}
.hero-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:32px}
.hero-status{margin-top:34px;display:flex;align-items:center;gap:12px;color:var(--soft)}
.hero-status strong{color:#fff;font-size:1rem}
.hero-status small{color:var(--muted)}
.hero-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin-top:30px;width:min(620px,100%);border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--line)}
.hero-metric{min-height:108px;background:rgba(255,255,255,.055);padding:18px 20px;display:flex;flex-direction:column;justify-content:center}
.hero-metric strong{font-family:'Space Grotesk','Inter',sans-serif;font-size:2.3rem;line-height:1}
.hero-metric span{margin-top:8px;color:var(--muted);font-weight:800}
.product-stage{position:relative;min-height:650px;border-left:1px solid rgba(255,255,255,.1)}
.product-stage::before{content:'';position:absolute;left:0;top:0;bottom:0;width:1px;background:linear-gradient(180deg,transparent,var(--cyan),transparent);box-shadow:0 0 42px rgba(66,240,221,.42)}
.product-viewport{position:sticky;top:110px;min-height:590px;padding:30px 0 0 36px}
.lens-system{position:relative;height:430px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:linear-gradient(145deg,rgba(255,255,255,.12),rgba(255,255,255,.035));box-shadow:0 34px 120px rgba(0,0,0,.38),inset 0 1px 0 rgba(255,255,255,.12)}
.lens-system::before{content:'';position:absolute;inset:0;background:
linear-gradient(180deg,rgba(255,255,255,.055) 1px,transparent 1px),
linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px);
background-size:42px 42px;opacity:.64;mask-image:linear-gradient(180deg,#000,transparent 92%)}
.lens-ring{position:absolute;inset:66px;border:1px solid rgba(66,240,221,.38);border-radius:50%;transform:scale(calc(.78 + var(--hero-p,0) * .22));opacity:calc(.5 + var(--hero-p,0) * .4);box-shadow:0 0 58px rgba(66,240,221,.14)}
.lens-ring.two{inset:112px;border-color:rgba(107,140,255,.42);transform:scale(calc(1.08 - var(--hero-p,0) * .18))}
.signal-chip{position:absolute;left:28px;right:28px;display:flex;align-items:center;justify-content:space-between;gap:18px;min-height:58px;padding:0 18px;border:1px solid var(--line);border-radius:8px;background:rgba(2,4,10,.56);backdrop-filter:blur(18px);font-family:'JetBrains Mono','Inter',monospace;color:var(--soft);font-size:.82rem;font-weight:800}
.signal-chip.a{top:28px}.signal-chip.b{top:114px}.signal-chip.c{bottom:114px}.signal-chip.d{bottom:28px}
.signal-chip span{color:var(--muted);font-weight:700}.signal-chip strong{color:#fff}
.hero-terminal{margin-top:16px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:rgba(2,4,10,.68);backdrop-filter:blur(18px)}
.terminal-row{display:grid;grid-template-columns:1fr auto;gap:14px;padding:13px 16px;border-bottom:1px solid rgba(255,255,255,.08);font-family:'JetBrains Mono','Inter',monospace;font-size:.82rem;color:var(--muted)}
.terminal-row:last-child{border-bottom:0}.terminal-row strong{color:#fff}
.signal-strip{position:relative;z-index:2;border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:rgba(2,4,10,.92);overflow:hidden}
.strip-track{display:flex;gap:34px;white-space:nowrap;padding:18px 0;font-family:'JetBrains Mono','Inter',monospace;color:rgba(247,248,251,.66);font-size:.88rem;font-weight:800;animation:eliteMarquee 26s linear infinite}
.strip-track span{color:#fff}.strip-track b{color:var(--cyan)}
@keyframes eliteMarquee{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.elite-story{position:relative;min-height:220dvh;background:#02040a;border-bottom:1px solid var(--line)}
.story-sticky{position:sticky;top:0;min-height:100dvh;display:grid;grid-template-columns:minmax(0,.9fr) minmax(440px,1.1fr);gap:56px;align-items:center;padding:76px 0;overflow:hidden}
.story-copy{position:relative;z-index:2}
.section-kicker{display:block;margin-bottom:18px}
.story-copy h2,.events-head h2{font-family:'Space Grotesk','Inter',sans-serif;font-size:4.3rem;line-height:.96;font-weight:700;text-wrap:balance}
.story-copy p,.events-head p{max-width:620px;margin-top:22px;color:rgba(247,248,251,.66);font-size:1.08rem;line-height:1.75}
.story-steps{display:grid;gap:10px;margin-top:34px;list-style:none}
.story-step{display:grid;grid-template-columns:42px 1fr;gap:16px;align-items:start;padding:16px;border:1px solid rgba(255,255,255,.1);border-radius:8px;background:rgba(255,255,255,.04);transition:border-color .24s ease,background .24s ease,transform .24s ease,opacity .24s ease;opacity:.48}
.story-step.is-active{opacity:1;border-color:rgba(66,240,221,.45);background:linear-gradient(145deg,rgba(66,240,221,.13),rgba(255,255,255,.055));transform:translateX(8px)}
.story-step code{font-family:'JetBrains Mono','Inter',monospace;color:var(--cyan);font-weight:800}.story-step b{display:block;color:#fff}.story-step span{display:block;color:var(--muted);margin-top:4px}
.story-stage{position:relative;z-index:1;min-height:620px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:linear-gradient(145deg,rgba(255,255,255,.09),rgba(255,255,255,.025));box-shadow:0 34px 130px rgba(0,0,0,.42)}
.story-stage::before{content:'';position:absolute;inset:0;background:
linear-gradient(180deg,rgba(255,255,255,.052) 1px,transparent 1px),
linear-gradient(90deg,rgba(255,255,255,.044) 1px,transparent 1px);
background-size:56px 56px;opacity:.7;mask-image:linear-gradient(180deg,#000,transparent 92%)}
.stage-caption{position:absolute;left:24px;right:24px;top:24px;z-index:2;display:flex;align-items:center;justify-content:space-between;min-height:54px;padding:0 16px;border:1px solid var(--line);border-radius:8px;background:rgba(2,4,10,.62);backdrop-filter:blur(18px);font-family:'JetBrains Mono','Inter',monospace;color:var(--soft);font-weight:800}
.stage-caption span{color:var(--cyan)}
.stage-dashboard{position:absolute;left:24px;right:24px;bottom:24px;z-index:2;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:rgba(255,255,255,.12)}
.stage-dashboard div{min-height:92px;padding:18px;background:rgba(2,4,10,.72)}.stage-dashboard span{display:block;color:var(--muted);font-size:.82rem;font-weight:800}.stage-dashboard strong{display:block;margin-top:8px;font-size:1.18rem}
.elite-events{position:relative;background:linear-gradient(180deg,#02040a,#070a13 42%,#02040a);padding:92px 0 88px}
.events-head{display:grid;grid-template-columns:minmax(0,.95fr) minmax(320px,.75fr);gap:48px;align-items:end;margin-bottom:36px}
.events-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:rgba(255,255,255,.1)}
.events-stat{min-height:120px;background:rgba(255,255,255,.055);padding:18px;display:flex;flex-direction:column;justify-content:center}.events-stat strong{font-size:2rem;font-family:'Space Grotesk','Inter',sans-serif}.events-stat span{color:var(--muted);font-weight:800}
.elite-toolbar{position:sticky;top:0;z-index:var(--z-nav);display:grid;grid-template-columns:minmax(260px,1fr) auto;gap:12px;align-items:center;padding:14px;margin:0 0 18px;border:1px solid var(--line);border-radius:8px;background:rgba(2,4,10,.82);backdrop-filter:blur(22px);box-shadow:0 18px 70px rgba(0,0,0,.28)}
.search-box{position:relative}.search-icon{position:absolute;left:16px;top:50%;width:17px;height:17px;transform:translateY(-50%);color:var(--muted);pointer-events:none}
.search-box input{width:100%;min-height:48px;border:1px solid rgba(255,255,255,.12);border-radius:8px;background:rgba(255,255,255,.07);color:#fff;padding:0 16px 0 46px;font:inherit;font-size:1rem;outline:0}
.search-box input::placeholder{color:rgba(247,248,251,.46)}.search-box input:focus{border-color:rgba(66,240,221,.55);box-shadow:0 0 0 4px rgba(66,240,221,.12)}
.filter-pills{display:flex;gap:8px;flex-wrap:wrap}.pill{min-height:44px;border:1px solid rgba(255,255,255,.12);border-radius:8px;background:rgba(255,255,255,.06);color:var(--soft);padding:0 14px;font:inherit;font-weight:800;cursor:pointer;transition:background .2s ease,border-color .2s ease,color .2s ease}
.pill:hover{background:rgba(255,255,255,.11);border-color:var(--line-2)}.pill.active{background:#f7f8fb;color:#03050c;border-color:#f7f8fb}
.deck-header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:26px 0 16px;color:var(--muted);font-weight:800}.deck-header strong{color:#fff}
.event-grid{display:grid;gap:12px}.event-card{position:relative;display:grid;grid-template-columns:88px minmax(0,1fr);gap:18px;min-height:156px;padding:18px;border:1px solid rgba(255,255,255,.11);border-radius:8px;background:linear-gradient(145deg,rgba(255,255,255,.087),rgba(255,255,255,.04));box-shadow:0 20px 70px rgba(0,0,0,.18);transition:transform .22s ease,border-color .22s ease,background .22s ease}
.event-card:hover{transform:translateY(-2px);border-color:rgba(66,240,221,.35);background:linear-gradient(145deg,rgba(255,255,255,.11),rgba(255,255,255,.05))}
.event-date{height:88px;border:1px solid rgba(255,255,255,.13);border-radius:8px;display:grid;place-items:center;background:rgba(2,4,10,.56)}
.event-date strong{display:block;text-align:center;font-family:'Space Grotesk','Inter',sans-serif;font-size:2rem;line-height:1}.event-date span{display:block;text-align:center;color:var(--muted);font-weight:800}
.event-body{min-width:0}.event-title{font-size:1.2rem;line-height:1.32;font-weight:800}.event-title a{text-decoration:none}.event-title a:hover{color:var(--cyan)}
.event-meta{display:flex;flex-wrap:wrap;gap:8px 14px;margin-top:9px;color:var(--muted);font-size:.92rem}.event-meta svg{width:15px;height:15px;vertical-align:-2px;margin-right:4px}
.quality-row{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}.chip{display:inline-flex;align-items:center;min-height:28px;border-radius:8px;padding:0 9px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);color:var(--soft);font-weight:800;font-size:.82rem}.chip.ai{border-color:rgba(107,140,255,.34);color:#dce4ff}.chip.manual{border-color:rgba(88,230,155,.34);color:#ccffe1}.chip.tbd{border-color:rgba(224,168,79,.38);color:#ffe1a6}
.event-desc{margin-top:12px;color:rgba(247,248,251,.62);font-size:.94rem;line-height:1.62}.event-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,.09)}
.source-dot{display:inline-flex;align-items:center;gap:8px;color:var(--muted);font-weight:800;font-size:.86rem}.source-dot::before{content:'';width:8px;height:8px;border-radius:50%;background:var(--amber);box-shadow:0 0 18px rgba(224,168,79,.5)}
.issue-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px}.issue-link,.card-link{min-height:36px;display:inline-flex;align-items:center;justify-content:center;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.055);padding:0 10px;text-decoration:none;color:var(--soft);font-weight:800;font-size:.85rem;transition:background .2s ease,border-color .2s ease}.issue-link:hover,.card-link:hover{border-color:rgba(66,240,221,.45);background:rgba(66,240,221,.12);color:#fff}.card-link svg{width:15px;height:15px;margin-left:5px}
.empty-state,.no-results{padding:64px 20px;text-align:center;color:var(--muted);border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.045)}.empty-state h3{color:#fff;font-size:1.3rem;margin-bottom:8px}.empty-icon svg{width:46px;height:46px;margin-bottom:18px;color:var(--cyan)}
.review-page .elite-hero{min-height:64dvh}.review-page .hero-layout{grid-template-columns:1fr;min-height:calc(64dvh - 92px);padding:56px 0}.review-list{display:grid;gap:12px;padding:24px 0 88px}.review-card{border:1px solid rgba(255,255,255,.11);border-radius:8px;background:rgba(255,255,255,.06);padding:18px}.review-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.review-id{font-family:'JetBrains Mono','Inter',monospace;color:var(--muted);font-size:.82rem}.review-title{margin-top:6px;font-size:1.12rem}.review-title a{text-decoration:none}.review-title a:hover{color:var(--cyan)}.review-reason{margin-top:14px;color:rgba(247,248,251,.64)}
footer{border-top:1px solid var(--line);background:#02040a;padding:38px 0}.footer-inner{display:grid;grid-template-columns:1fr auto 1fr;gap:20px;align-items:center;color:var(--muted);font-size:.92rem}.footer-brand-name{color:#fff;font-weight:800}.footer-links{display:flex;justify-content:flex-end;gap:18px}.footer-links a{text-decoration:none;color:var(--muted);font-weight:800}.footer-links a:hover{color:#fff}
@media(max-width:980px){
.hero-layout,.story-sticky,.events-head{grid-template-columns:1fr;gap:34px}.product-stage{border-left:0}.product-viewport{position:relative;top:auto;padding:0;min-height:0}.story-sticky{position:relative;min-height:auto;padding:72px 0}.elite-story{min-height:auto}.story-stage{min-height:560px}.hero-title{font-size:4.2rem}.story-copy h2,.events-head h2{font-size:3.4rem}.elite-toolbar{grid-template-columns:1fr}.events-stats{grid-template-columns:1fr}.footer-inner{grid-template-columns:1fr;text-align:center}.footer-links{justify-content:center}}
@media(max-width:620px){
.elite-container{width:min(100% - 32px,1200px)}.elite-nav{min-height:78px}.elite-brand>span:not(.elite-logo),.elite-link{display:none}.elite-logo{display:grid!important}.elite-button{padding:0 12px}.hero-layout{min-height:calc(100dvh - 78px);padding:48px 0 56px}.hero-title{font-size:3.15rem}.hero-sub{font-size:1rem}.hero-metrics{grid-template-columns:1fr}.lens-system{height:360px}.signal-chip{left:16px;right:16px;font-size:.76rem}.story-copy h2,.events-head h2{font-size:2.65rem}.story-stage{min-height:520px}.stage-dashboard{grid-template-columns:1fr}.event-card{grid-template-columns:1fr}.event-date{width:88px}.event-footer{align-items:flex-start;flex-direction:column}.issue-actions{justify-content:flex-start}.filter-pills{display:grid;grid-template-columns:1fr 1fr}.pill{padding:0 10px}}
@media(prefers-reduced-motion:reduce){
html{scroll-behavior:auto}.strip-track{animation:none}.event-card,.story-step,.elite-link,.elite-button,.pill,.issue-link,.card-link{transition:none!important}.elite-canvas,.story-canvas{opacity:.28!important}
}
"""

_ELITE_JS = """
(function(){
var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if('scrollRestoration'in history){history.scrollRestoration='manual'}
if(!location.hash){window.scrollTo(0,0);window.addEventListener('pageshow',function(){requestAnimationFrame(function(){window.scrollTo(0,0)})})}
var root=document.documentElement,body=document.body;
var hero=document.querySelector('.elite-hero'),story=document.querySelector('.elite-story'),heroCanvas=document.getElementById('elite-hero-canvas'),storyCanvas=document.getElementById('elite-story-canvas');
var mouse={x:.5,y:.5,active:false},state={hero:0,story:0};
function clamp(n){return Math.max(0,Math.min(1,n))}
function progress(el,bias){if(!el)return 0;var r=el.getBoundingClientRect(),vh=window.innerHeight||1;return clamp((vh*(bias||.72)-r.top)/(r.height-vh*.18))}
function setupCanvas(canvas){if(!canvas||!canvas.getContext)return null;var ctx=canvas.getContext('2d');function size(){var r=canvas.getBoundingClientRect(),d=Math.min(window.devicePixelRatio||1,2);canvas.width=Math.max(1,Math.floor(r.width*d));canvas.height=Math.max(1,Math.floor(r.height*d));ctx.setTransform(d,0,0,d,0,0);return r}return{canvas:canvas,ctx:ctx,size:size}}
var hc=setupCanvas(heroCanvas),sc=setupCanvas(storyCanvas);
function drawHero(now){if(!hc)return;var r=hc.size(),ctx=hc.ctx,w=r.width,h=r.height,t=now*.001;ctx.clearRect(0,0,w,h);ctx.globalCompositeOperation='lighter';var count=w<700?90:150;for(var i=0;i<count;i++){var a=i*.71+t*.08,rad=(Math.sin(i*2.1+t*.3)+1)*.5;var x=w*(.56+.28*Math.cos(a)*(.35+rad*.65))+((mouse.x-.5)*42);var y=h*(.48+.36*Math.sin(a*1.34)*(.35+rad*.65))+((mouse.y-.5)*30);var s=i%9===0?2.6:1.35;ctx.fillStyle=i%7===0?'rgba(66,240,221,.76)':'rgba(210,220,255,.34)';ctx.beginPath();ctx.arc(x,y,s,0,Math.PI*2);ctx.fill();if(i%3===0){var x2=w*(.56+.28*Math.cos(a+.42)*(.35+rad*.65)),y2=h*(.48+.36*Math.sin((a+.42)*1.34)*(.35+rad*.65));ctx.strokeStyle='rgba(107,140,255,.12)';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x2,y2);ctx.stroke()}}ctx.globalCompositeOperation='source-over';if(!reduce)requestAnimationFrame(drawHero)}
function drawStory(now){if(!sc)return;var r=sc.size(),ctx=sc.ctx,w=r.width,h=r.height,t=now*.001,p=state.story;ctx.clearRect(0,0,w,h);ctx.globalCompositeOperation='lighter';var cx=w*.52,cy=h*.49;for(var ring=0;ring<5;ring++){ctx.strokeStyle='rgba(66,240,221,'+(0.13-ring*.018)+')';ctx.lineWidth=1;ctx.beginPath();ctx.ellipse(cx,cy,70+ring*48+p*38,42+ring*35+p*18,ring*.2+t*.04,0,Math.PI*2);ctx.stroke()}var steps=[[w*.18,h*.33],[w*.42,h*.22],[w*.68,h*.39],[w*.48,h*.57],[w*.76,h*.70]];ctx.lineWidth=2.4;ctx.lineCap='round';for(var i=0;i<steps.length-1;i++){var a=steps[i],b=steps[i+1],seg=clamp(p*4-i);ctx.strokeStyle='rgba(66,240,221,'+(seg*.72)+')';ctx.beginPath();ctx.moveTo(a[0],a[1]);var mx=(a[0]+b[0])*.5,my=(a[1]+b[1])*.5+(i%2?-60:58);ctx.quadraticCurveTo(mx,my,a[0]+(b[0]-a[0])*seg,a[1]+(b[1]-a[1])*seg);ctx.stroke()}steps.forEach(function(pt,i){var active=p>i/5-.04;ctx.fillStyle=active?'rgba(255,255,255,.95)':'rgba(170,185,220,.28)';ctx.beginPath();ctx.arc(pt[0],pt[1],active?6:4,0,Math.PI*2);ctx.fill();if(active){ctx.strokeStyle='rgba(66,240,221,.36)';ctx.lineWidth=1;ctx.beginPath();ctx.arc(pt[0],pt[1],24+Math.sin(t*2+i)*5,0,Math.PI*2);ctx.stroke()}});ctx.globalCompositeOperation='source-over';if(!reduce)requestAnimationFrame(drawStory)}
function update(){state.hero=progress(hero,.58);state.story=progress(story,.78);body.style.setProperty('--hero-p',state.hero.toFixed(3));body.style.setProperty('--story-p',state.story.toFixed(3));var idx=Math.min(4,Math.max(0,Math.floor(state.story*5)));document.querySelectorAll('[data-story-step]').forEach(function(el,i){el.classList.toggle('is-active',i===idx||state.story>i/5+.12)})}
var ticking=false;function request(){if(!ticking){ticking=true;requestAnimationFrame(function(){ticking=false;update()})}}
update();if(hc)requestAnimationFrame(drawHero);if(sc)requestAnimationFrame(drawStory);
window.addEventListener('scroll',request,{passive:true});window.addEventListener('resize',function(){request()},{passive:true});
window.addEventListener('pointermove',function(e){mouse.x=e.clientX/(window.innerWidth||1);mouse.y=e.clientY/(window.innerHeight||1);mouse.active=true},{passive:true});
var search=document.getElementById('search'),filters=Array.from(document.querySelectorAll('[data-filter]')),cards=Array.from(document.querySelectorAll('.card')),countLabel=document.getElementById('count-label'),noResults=document.getElementById('no-results'),activeFilter='all';
function inFilter(card){var iso=card.getAttribute('data-date');if(activeFilter==='all')return true;if(!iso)return activeFilter==='later';var d=new Date(iso+'T12:00:00'),now=new Date(),diff=(d-now)/86400000;if(activeFilter==='week')return diff>=0&&diff<=7;if(activeFilter==='month')return d.getMonth()===now.getMonth()&&d.getFullYear()===now.getFullYear();return diff>31}
function apply(){var q=(search&&search.value||'').trim().toLowerCase(),shown=0;cards.forEach(function(card){var hay=card.getAttribute('data-search')||'',ok=hay.indexOf(q)>-1&&inFilter(card);card.hidden=!ok;if(ok)shown++});if(countLabel)countLabel.textContent=shown+' '+(shown===1?'evento':'eventi');if(noResults)noResults.style.display=shown?'none':'block'}
if(search)search.addEventListener('input',apply);filters.forEach(function(btn){btn.addEventListener('click',function(){filters.forEach(function(b){b.classList.remove('active')});btn.classList.add('active');activeFilter=btn.getAttribute('data-filter')||'all';apply()})});apply();
cards.forEach(function(card){card.addEventListener('pointermove',function(e){var r=card.getBoundingClientRect(),x=(e.clientX-r.left)/Math.max(1,r.width),y=(e.clientY-r.top)/Math.max(1,r.height);card.style.setProperty('--mx',(x*100).toFixed(1)+'%');card.style.setProperty('--my',(y*100).toFixed(1)+'%')},{passive:true})});
})();
"""

def _build_elite_cards(events: list[dict]) -> str:
    parts: list[str] = []
    arrow = (
        '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"'
        ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 8h10M9 4l4 4-4 4"/></svg>'
    )
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
            f'<div class="event-date"><div><strong>{day}</strong><span>{month}</span></div></div>'
            if day and month
            else '<div class="event-date"><div><strong>TBD</strong><span>data</span></div></div>'
        )
        chips = []
        if review_status == "manual_approved":
            chips.append('<span class="chip manual">Manuale</span>')
        elif confidence > 0:
            chips.append(f'<span class="chip ai">AI {int(round(confidence * 100))}%</span>')
        if not date_iso:
            chips.append('<span class="chip tbd">Data TBD</span>')
        quality_html = f'<div class="quality-row">{"".join(chips)}</div>' if chips else ""
        desc_html = f'<p class="event-desc">{desc}</p>' if desc else ""
        search_blob = _escape(f"{title} {desc} {location} {source}".lower())
        parts.append(
            f'<article class="event-card card" data-date="{date_iso}" data-search="{search_blob}">'
            f'{date_badge}'
            '<div class="event-body">'
            f'<h2 class="event-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>'
            '<div class="event-meta">'
            f'<span>{_SVG_PIN}{location}</span>'
            + (f'<span>{_SVG_CAL}{_escape(date_compact)}</span>' if date_compact else '')
            + '</div>'
            f'{quality_html}'
            f'{desc_html}'
            '<div class="event-footer">'
            f'<span class="source-dot">{source}</span>'
            '<div class="issue-actions">'
            f'<a href="{issue_ok_url}" class="issue-link" target="_blank" rel="noopener">Valuta OK</a>'
            f'<a href="{issue_doubt_url}" class="issue-link" target="_blank" rel="noopener">Segnala dubbio</a>'
            f'<a href="{url}" class="card-link" target="_blank" rel="noopener">Vedi evento{arrow}</a>'
            '</div></div></div></article>'
        )
    return "\n".join(parts)


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
    mon_count = str(len(months_set)) if months_set else "0"
    status_label = _scan_status_label(scan_status, collector_failures)
    status_dot = "ops-dot" if status_label == "OK" else "ops-dot warn"

    return (
        '<!DOCTYPE html>\n<html lang="it">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<meta name="description" content="{event_count} hackathon in programma a Milano e dintorni.">\n'
        '<meta property="og:title" content="Hackathon Milano">\n'
        f'<meta property="og:description" content="{event_count} hackathon in programma a Milano">\n'
        '<meta property="og:type" content="website">\n'
        '<meta property="og:image" content="hero-hackathon-milano.png">\n'
        '<title>Hackathon Milano</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">\n'
        f'<style>{_ELITE_CSS}</style>\n'
        '</head>\n<body class="elite-shell">\n'
        '<header class="elite-hero" id="top">\n'
        '<canvas class="elite-canvas" id="elite-hero-canvas" aria-hidden="true"></canvas>\n'
        '<div class="elite-container">\n'
        '<nav class="elite-nav" aria-label="Navigazione principale">\n'
        '<a class="elite-brand" href="#top"><span class="elite-logo"><svg viewBox="0 0 24 24"><path d="M12 3 3.8 8.2 12 13.4l8.2-5.2L12 3Z"/><path d="m3.8 12.2 8.2 5.2 8.2-5.2"/><path d="m3.8 16.2 8.2 5.2 8.2-5.2"/></svg></span><span><strong>Hackathon Milano</strong><span>Milano intelligence layer</span></span></a>\n'
        '<div class="elite-nav-actions"><a class="elite-link" href="review.html">Candidati in review</a><a class="elite-button" href="#events"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 10h10M11 6l4 4-4 4" stroke-linecap="round" stroke-linejoin="round"/></svg>Eventi</a></div>\n'
        '</nav>\n'
        '<div class="hero-layout">\n'
        '<div class="hero-copy">\n'
        '<div class="hero-kicker"><span class="live-dot"></span>Live AI scouting system</div>\n'
        '<h1 class="hero-title">Hackathon <span class="accent">Milano</span></h1>\n'
        '<p class="hero-sub">Un prodotto editoriale e operativo per leggere il territorio: raccoglie segnali pubblici, comprime duplicati, assegna fiducia e pubblica solo opportunita verificabili.</p>\n'
        '<div class="hero-actions"><a class="elite-button" href="#events">Apri il deck eventi</a><a class="elite-link" href="https://github.com/federicoogallo/Hackathon-MI" target="_blank" rel="noopener">GitHub</a></div>\n'
        f'<div class="hero-status"><span class="{status_dot}"></span><strong>{_escape(status_label)}</strong><small>{_escape(last_scan)}</small></div>\n'
        '<div class="hero-metrics" aria-label="Metriche monitor">\n'
        f'<div class="hero-metric"><strong>{event_count}</strong><span>{evt_word} verificati</span></div>\n'
        f'<div class="hero-metric"><strong>{mon_count}</strong><span>{mon_word} coperti</span></div>\n'
        '<div class="hero-metric"><strong>24h</strong><span>refresh</span></div>\n'
        '</div>\n'
        '</div>\n'
        '<aside class="product-stage" aria-hidden="true">\n'
        '<div class="product-viewport">\n'
        '<div class="lens-system"><div class="lens-ring"></div><div class="lens-ring two"></div>'
        '<div class="signal-chip a"><strong>Collect</strong><span>fonti pubbliche</span></div>'
        '<div class="signal-chip b"><strong>Dedupe</strong><span>cluster simili</span></div>'
        '<div class="signal-chip c"><strong>AI score</strong><span>fiducia e contesto</span></div>'
        '<div class="signal-chip d"><strong>Publish</strong><span>output verificato</span></div>'
        '</div>\n'
        '<div class="hero-terminal"><div class="terminal-row"><span>scope</span><strong>Milano</strong></div><div class="terminal-row"><span>Candidati in review</span><strong>'
        f'{review_count}</strong></div><div class="terminal-row"><span>collector errors</span><strong>{collector_failures}</strong></div></div>\n'
        '</div>\n'
        '</aside>\n'
        '</div>\n'
        '</div>\n'
        '</header>\n'
        '<section class="signal-strip" aria-label="Pipeline status"><div class="strip-track">'
        '<span>PUBLIC SOURCES</span><b>/</b><span>DEDUPLICATION</span><b>/</b><span>AI CONFIDENCE</span><b>/</b><span>MANUAL REVIEW</span><b>/</b><span>GITHUB PAGES OUTPUT</span><b>/</b>'
        '<span>PUBLIC SOURCES</span><b>/</b><span>DEDUPLICATION</span><b>/</b><span>AI CONFIDENCE</span><b>/</b><span>MANUAL REVIEW</span><b>/</b><span>GITHUB PAGES OUTPUT</span><b>/</b>'
        '</div></section>\n'
        '<section class="elite-story" id="system">\n'
        '<canvas class="story-canvas" id="elite-story-canvas" aria-hidden="true"></canvas>\n'
        '<div class="elite-container story-sticky">\n'
        '<div class="story-copy">\n'
        '<span class="section-kicker">01 / Intelligence system</span>\n'
        '<h2>Dal rumore pubblico a un calendario ad alta fiducia.</h2>\n'
        '<p>La pagina non deve sembrare una lista: deve far percepire il sistema che lavora sotto. Ogni scroll rivela una fase del motore, dal segnale grezzo all output pronto per essere usato.</p>\n'
        '<ol class="story-steps">\n'
        '<li class="story-step" data-story-step><code>01</code><div><b>Collect</b><span>Community, piattaforme eventi e ricerca web entrano nel radar.</span></div></li>\n'
        '<li class="story-step" data-story-step><code>02</code><div><b>Dedupe</b><span>I record sovrapposti diventano un solo candidato leggibile.</span></div></li>\n'
        '<li class="story-step" data-story-step><code>03</code><div><b>AI score</b><span>Luogo, data, formato, descrizione e fonte generano fiducia.</span></div></li>\n'
        '<li class="story-step" data-story-step><code>04</code><div><b>Review</b><span>I casi incerti passano a controllo umano senza sporcare la pagina pubblica.</span></div></li>\n'
        '<li class="story-step" data-story-step><code>05</code><div><b>Publish</b><span>Gli eventi verificati diventano output stabile su GitHub Pages.</span></div></li>\n'
        '</ol>\n'
        '</div>\n'
        '<div class="story-stage" aria-hidden="true"><div class="stage-caption"><span>Signal routing</span><strong>Confidence graph</strong></div><div class="stage-dashboard"><div><span>Refresh</span><strong>24h</strong></div><div><span>Scope</span><strong>Milano</strong></div><div><span>Output</span><strong>verified</strong></div></div></div>\n'
        '</div>\n'
        '</section>\n'
        '<main class="elite-events" id="events">\n'
        '<div class="elite-container">\n'
        '<section class="events-head" aria-label="Eventi verificati">\n'
        '<div><span class="section-kicker">02 / Event deck</span><h2>Output finale, pronto da scansionare.</h2><p>Gli eventi sono presentati come un deck operativo: pochi segnali forti, fonte visibile, qualita esplicita e azioni rapide per confermare o aprire dubbi.</p></div>\n'
        '<div class="events-stats"><div class="events-stat"><strong>'
        f'{event_count}</strong><span>{evt_word}</span></div><div class="events-stat"><strong>{mon_count}</strong><span>{mon_word}</span></div><div class="events-stat"><strong>{review_count}</strong><span>Candidati in review</span></div></div>\n'
        '</section>\n'
        '<section class="elite-toolbar" aria-label="Filtri eventi">\n'
        f'<div class="search-box"><label class="sr-only" for="search">Cerca eventi</label>{_SVG_SEARCH}<input type="text" id="search" placeholder="Cerca hackathon, fonte o luogo..." autocomplete="off"></div>\n'
        '<div class="filter-pills" id="filters"><button class="pill active" data-filter="all">Tutti</button><button class="pill" data-filter="week">Settimana</button><button class="pill" data-filter="month">Mese</button><button class="pill" data-filter="later">Prossimi</button></div>\n'
        '</section>\n'
        f'<div class="deck-header"><strong>Prossimi eventi verificati</strong><span id="count-label">{event_count} eventi</span></div>\n'
        f'<div class="event-grid" id="grid">{cards_html}</div>\n'
        '<p class="no-results" id="no-results" style="display:none">Nessun risultato trovato.</p>\n'
        '</div>\n'
        '</main>\n'
        '<footer><div class="elite-container"><div class="footer-inner"><div><div class="footer-brand-name">Hackathon Milano</div><div>Dati raccolti automaticamente con AI</div></div><div>Aggiornato: '
        f'{_escape(last_scan)}</div><div class="footer-links"><a href="https://github.com/federicoogallo/Hackathon-MI" target="_blank" rel="noopener">GitHub</a><a href="#top">Top</a></div></div></div></footer>\n'
        f'<script>{_ELITE_JS}</script>\n'
        '</body>\n</html>'
    )


def _build_review_html(candidates: list[dict], last_scan: str) -> str:
    cards = _build_review_cards(candidates)
    count = len(candidates)
    return (
        '<!DOCTYPE html>\n<html lang="it">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<meta name="description" content="{count} candidati hackathon da rivedere.">\n'
        '<meta property="og:image" content="hero-hackathon-milano.png">\n'
        '<title>Review queue - Hackathon Milano</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700;800&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">\n'
        f'<style>{_ELITE_CSS}</style>\n'
        '</head>\n<body class="elite-shell review-page">\n'
        '<header class="elite-hero"><canvas class="elite-canvas" id="elite-hero-canvas" aria-hidden="true"></canvas><div class="elite-container">'
        '<nav class="elite-nav"><a class="elite-brand" href="index.html"><span class="elite-logo"><svg viewBox="0 0 24 24"><path d="M12 3 3.8 8.2 12 13.4l8.2-5.2L12 3Z"/><path d="m3.8 12.2 8.2 5.2 8.2-5.2"/><path d="m3.8 16.2 8.2 5.2 8.2-5.2"/></svg></span><span><strong>Review queue</strong><span>Manual confidence control</span></span></a><div class="elite-nav-actions"><a class="elite-button" href="index.html">Eventi confermati</a></div></nav>'
        '<div class="hero-layout"><div class="hero-copy"><div class="hero-kicker"><span class="live-dot"></span>Manual review</div><h1 class="hero-title">Review <span class="accent">queue</span></h1>'
        f'<p class="hero-sub">{count} eventi hanno abbastanza segnale per una revisione umana. Gli utenti possono solo aprire issue di conferma o dubbio: l eliminazione resta ai maintainer.</p>'
        f'<div class="hero-status"><span class="ops-dot"></span><strong>{count}</strong><small>Aggiornato: {_escape(last_scan)}</small></div></div></div>'
        '</div></header>'
        '<main class="elite-events"><div class="elite-container"><div class="deck-header"><strong>Da rivedere</strong><span>Manual layer</span></div><div class="review-list">'
        f'{cards}'
        '</div></div></main>'
        '<footer><div class="elite-container"><div class="footer-inner"><div><div class="footer-brand-name">Hackathon Milano</div><div>Review queue generata dalla pipeline</div></div><div></div><div class="footer-links"><a href="index.html">Calendario</a></div></div></div></footer>'
        f'<script>{_ELITE_JS}</script>\n'
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
