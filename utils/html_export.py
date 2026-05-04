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


def _scan_status() -> tuple[str, int]:
    data = _read_json(config.DATA_DIR / "last_report.json")
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
        '<title>Hackathon Milano</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Serif+Display&display=swap" rel="stylesheet">\n'
        f'<style>{_CSS}</style>\n'
        '</head>\n<body>\n\n'
        # Hero
        '<header class="hero">\n'
        '<div class="hero-bg"></div><div class="hero-grid"></div>\n'
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
        '      <div class="hero-eyebrow"><span></span>Milano &middot; Aggiornato ogni 24h</div>\n'
        '      <h1>'
        '<span class="hw" style="animation-delay:.22s">Il</span> '
        '<span class="hw" style="animation-delay:.30s">calendario</span> '
        '<span class="hw" style="animation-delay:.38s">degli</span> '
        '<em>hackathon</em> '
        '<span class="hw" style="animation-delay:.56s">milanesi.</span>'
        '</h1>\n'
        '      <p class="hero-sub">Ogni giorno raccogliamo, filtriamo e verifichiamo gli hackathon davvero rilevanti per Milano.</p>\n'
        '      <div class="hero-actions">\n'
        '        <a class="btn-primary" href="#events">'
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 7l-5 5-5-5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        'Esplora gli eventi</a>\n'
        '        <span class="hero-badge">Dati aggiornati dalla pipeline</span>\n'
        '      </div>\n'
        '    </div>\n'
        '    <aside class="hero-panel" aria-label="Stato monitor">\n'
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
        '    </aside>\n'
        '  </div>\n'
        '</div>\n'
        '</div>\n'
        '</header>\n\n'
        # Toolbar
        '<section class="toolbar-wrap"><div class="container toolbar">\n'
        f'  <div class="search-box">{_SVG_SEARCH}<input type="text" id="search" placeholder="Cerca eventi..." autocomplete="off"></div>\n'
        '  <div class="filter-pills" id="filters">\n'
        '    <button class="pill active" data-filter="all">Tutti</button>\n'
        '    <button class="pill" data-filter="week">Questa settimana</button>\n'
        '    <button class="pill" data-filter="month">Questo mese</button>\n'
        '    <button class="pill" data-filter="later">Prossimi mesi</button>\n'
        '  </div>\n'
        '</div></section>\n\n'
        # Main
        f'<main class="container" id="events"><div class="section-header">\n'
        f'  <span class="section-title">Prossimi eventi</span>\n'
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
        '<div class="empty-icon">\U0001f4c5</div>'
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
        '<title>Review queue - Hackathon Milano</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=DM+Serif+Display&display=swap" rel="stylesheet">\n'
        f'<style>{_CSS}</style>\n'
        '</head>\n<body>\n'
        '<header class="hero"><div class="hero-bg"></div><div class="hero-grid"></div>'
        '<div class="hero-content"><div class="container">'
        '<nav class="topbar"><div class="brand"><div class="brand-mark">'
        '<svg viewBox="0 0 20 20"><path d="M10 2L2 7l8 5 8-5-8-5z"/><path d="M2 13l8 5 8-5"/><path d="M2 10l8 5 8-5"/></svg>'
        '</div><div><div class="brand-name">Review queue</div>'
        '<div class="brand-city">Candidati da verificare</div></div></div>'
        '<a class="topbar-link" href="index.html">Eventi confermati</a></nav>'
        '<div class="hero-body hero-body-single"><div class="hero-copy"><div class="hero-eyebrow"><span></span>Manual review</div>'
        '<h1>Candidati <em>da valutare</em> prima della pubblicazione.</h1>'
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
    scan_status, collector_failures = _scan_status()
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
