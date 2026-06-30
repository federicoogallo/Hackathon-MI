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

_JS += """
(function(){
var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
var canvas=document.getElementById('signal-canvas');
if(canvas&&canvas.getContext){
var ctx=canvas.getContext('2d'),dpr=1,pts=[],mouse={x:0,y:0,active:false};
function build(){
  dpr=Math.min(window.devicePixelRatio||1,2);
  var r=canvas.getBoundingClientRect();
  canvas.width=Math.max(1,Math.floor(r.width*dpr));
  canvas.height=Math.max(1,Math.floor(r.height*dpr));
  ctx.setTransform(dpr,0,0,dpr,0,0);
  var w=r.width,h=r.height,count=w<700?150:260;
  pts=[];
  for(var i=0;i<count;i++){
    var t=i/count,band=i%5,angle=t*Math.PI*10+band*.35;
    var radius=(.16+.26*Math.sin(t*Math.PI))*Math.min(w,h);
    var stream=Math.max(0,t-.58)*w*.58;
    var tx=w*(.56+.05*Math.sin(t*11))+Math.cos(angle)*radius*.62+stream;
    var ty=h*(.43+.08*Math.cos(t*7))+Math.sin(angle)*radius*.44+(band-2)*10;
    pts.push({x:tx+(Math.random()-.5)*42,y:ty+(Math.random()-.5)*42,tx:tx,ty:ty,s:.8+Math.random()*1.8,p:Math.random()*6.28});
  }
}
function frame(now){
  var r=canvas.getBoundingClientRect(),w=r.width,h=r.height,t=now*.001;
  ctx.clearRect(0,0,w,h);
  ctx.globalCompositeOperation='lighter';
  var mx=mouse.active?(mouse.x/w-.5)*28:0,my=mouse.active?(mouse.y/h-.5)*20:0;
  for(var i=0;i<pts.length;i++){
    var p=pts[i];
    p.x+=(p.tx+Math.sin(t+p.p)*10+mx-p.x)*.035;
    p.y+=(p.ty+Math.cos(t*.8+p.p)*8+my-p.y)*.035;
  }
  for(var a=0;a<pts.length;a+=2){
    for(var b=a+1;b<Math.min(pts.length,a+18);b+=3){
      var pa=pts[a],pb=pts[b],dx=pa.x-pb.x,dy=pa.y-pb.y,dist=Math.sqrt(dx*dx+dy*dy);
      if(dist<92){ctx.strokeStyle='rgba(69,105,255,'+(1-dist/92)*.13+')';ctx.lineWidth=.8;ctx.beginPath();ctx.moveTo(pa.x,pa.y);ctx.lineTo(pb.x,pb.y);ctx.stroke();}
    }
  }
  for(var j=0;j<pts.length;j++){
    var q=pts[j],glow=.35+.35*Math.sin(t*2+q.p);
    ctx.fillStyle=j%9===0?'rgba(69,240,209,.86)':'rgba(229,235,255,'+(.35+glow*.4)+')';
    ctx.fillRect(q.x,q.y,q.s,q.s);
  }
  ctx.globalCompositeOperation='source-over';
  ctx.strokeStyle='rgba(255,255,255,.08)';ctx.lineWidth=1;ctx.beginPath();ctx.ellipse(w*.66,h*.43,Math.min(w,h)*.27,Math.min(w,h)*.18,0,0,Math.PI*2);ctx.stroke();
  if(!reduce)requestAnimationFrame(frame);
}
build();requestAnimationFrame(frame);
window.addEventListener('resize',build,{passive:true});
window.addEventListener('pointermove',function(e){var r=canvas.getBoundingClientRect();mouse.x=e.clientX-r.left;mouse.y=e.clientY-r.top;mouse.active=true;},{passive:true});
window.addEventListener('pointerleave',function(){mouse.active=false},{passive:true});
}
var reveal=document.querySelectorAll('[data-reveal]');
if('IntersectionObserver'in window){var io=new IntersectionObserver(function(entries){entries.forEach(function(e){if(e.isIntersecting){e.target.classList.add('is-visible');io.unobserve(e.target)}})},{threshold:.18});reveal.forEach(function(el){io.observe(el)})}else{reveal.forEach(function(el){el.classList.add('is-visible')})}
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
        '      <h1>Hackathon <em>Milano</em></h1>\n'
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
        '<div class="pipe-node"><small>01</small><b>Collect</b><em>Fonti pubbliche e community events</em></div>\n'
        '<div class="pipe-node"><small>02</small><b>Dedupe</b><em>Cluster di record simili e duplicati</em></div>\n'
        '<div class="pipe-node"><small>03</small><b>AI score</b><em>Luogo, data, formato e attendibilita</em></div>\n'
        '<div class="pipe-node"><small>04</small><b>Review</b><em>Candidati incerti verso controllo umano</em></div>\n'
        '<div class="pipe-node"><small>05</small><b>Publish</b><em>Output verificato su GitHub Pages</em></div>\n'
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
