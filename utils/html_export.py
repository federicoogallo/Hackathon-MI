"""
Genera una pagina HTML statica con tutti gli hackathon futuri confermati.

Output: docs/index.html  servita via GitHub Pages.
Viene rigenerata ad ogni run della pipeline.
Design: light theme, Inter font, card grid responsive, search e filter JS.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, date, timezone
from pathlib import Path
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
    "--radius:16px;"
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
    "background:"
    "radial-gradient(ellipse 130% 120% at 100% -20%,rgba(37,99,235,.28),transparent 55%),"
    "radial-gradient(ellipse 80% 80% at -10% 110%,rgba(217,119,6,.18),transparent 50%),"
    "radial-gradient(ellipse 60% 60% at 50% 50%,rgba(30,45,66,.9),transparent 100%),"
    "var(--dark)}"
    ".hero-grid{display:none}"
    ".hero-content{position:relative;z-index:1}"
    ".topbar{display:flex;align-items:center;justify-content:space-between;"
    "padding:1.25rem 0;border-bottom:1px solid rgba(255,255,255,.07)}"
    ".brand{display:flex;align-items:center;gap:.75rem}"
    ".brand-mark{width:36px;height:36px;border-radius:10px;"
    "background:linear-gradient(135deg,var(--accent),#1d4ed8);"
    "display:grid;place-items:center;flex-shrink:0}"
    ".brand-mark svg{width:18px;height:18px;fill:none;stroke:#fff;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}"
    ".brand-name{font-size:.9rem;font-weight:600;color:#fff;letter-spacing:.01em}"
    ".brand-city{font-size:.75rem;color:rgba(255,255,255,.4);margin-top:-.1rem}"
    ".topbar-link{display:inline-flex;align-items:center;gap:.4rem;color:rgba(255,255,255,.7);"
    "text-decoration:none;font-weight:500;font-size:.82rem;"
    "padding:.5rem .9rem;border-radius:999px;"
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
    "animation:wordReveal .7s cubic-bezier(.22,1,.36,1) .47s both,shimmer 4s linear .47s infinite}"
    ".hero-sub{font-size:1.05rem;color:rgba(255,255,255,.55);max-width:520px;"
    "line-height:1.65;margin-bottom:2.25rem;font-weight:400}"
    ".hero-actions{display:flex;align-items:center;gap:1rem;flex-wrap:wrap}"
    ".btn-primary{display:inline-flex;align-items:center;gap:.5rem;"
    "background:var(--accent);color:#fff;text-decoration:none;font-weight:600;"
    "padding:.8rem 1.5rem;border-radius:10px;"
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
    "padding:1rem 1.25rem;border-radius:12px;backdrop-filter:blur(8px)}"
    ".stat-num{font-size:1.6rem;font-weight:700;line-height:1.1;color:#fff;"
    "font-family:'DM Serif Display',Georgia,serif}"
    ".stat-label{font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;"
    "color:rgba(255,255,255,.35);margin-top:.15rem}"
    # Hero entrance stagger
    ".hero-eyebrow{animation:fadeUp .55s ease .05s both}"
    ".hero-sub{animation:fadeUp .6s ease .64s both}"
    ".hero-actions{animation:fadeUp .6s ease .8s both}"
    ".stats-row{animation:fadeUp .65s ease .95s both}"
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
    "border:1.5px solid var(--border);border-radius:10px;font-family:inherit;"
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
    "@keyframes wordReveal{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}"
    "@keyframes shimmer{0%{background-position:0% center}100%{background-position:200% center}}"
    ".hw{display:inline-block;opacity:0;animation:wordReveal .7s cubic-bezier(.22,1,.36,1) both}"
    # Date badge
    ".date-badge{display:flex;flex-direction:column;align-items:center;"
    "justify-content:center;min-width:58px;height:64px;"
    "background:var(--dark);border-radius:12px;flex-shrink:0;"
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
    # Empty state + no-results
    ".empty-state{text-align:center;padding:5rem 1rem;color:var(--text-secondary)}"
    ".empty-icon{font-size:2.5rem;margin-bottom:1.25rem;opacity:.4}"
    ".empty-state h3{font-size:1.1rem;font-weight:600;color:var(--text);margin-bottom:.5rem}"
    ".empty-state p{font-size:.9rem;line-height:1.65;max-width:340px;margin:0 auto}"
    ".no-results{text-align:center;padding:3rem 1rem;font-size:.9rem;color:var(--text-muted)}"
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
    ".date-badge{min-width:50px;height:56px}"
    ".date-day{font-size:1.25rem}"
    ".card-title{font-size:.95rem}"
    ".footer-inner{grid-template-columns:1fr;text-align:center;gap:.75rem}"
    ".footer-links{justify-content:center}"
    ".footer-center{display:none}}"
)

# ---- JS ----

_JS = (
    "(function(){"
    # Count-up animation for stat numbers
    "var stNums=document.querySelectorAll('.stat-num[data-target]');"
    "stNums.forEach(function(el){"
    "var target=parseInt(el.dataset.target,10);"
    "if(isNaN(target))return;"
    "var start=null,dur=1100;"
    "function step(ts){if(!start)start=ts;"
    "var p=Math.min((ts-start)/dur,1);"
    "var e=1-Math.pow(1-p,3);"
    "el.textContent=Math.round(e*target);"
    "if(p<1)requestAnimationFrame(step)}"
    "setTimeout(function(){requestAnimationFrame(step)},900)});"
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
        '    <div class="hero-eyebrow"><span></span>Milano &middot; Aggiornato ogni 24h</div>\n'
        '    <h1>'
        '<span class="hw" style="animation-delay:.22s">Il</span> '
        '<span class="hw" style="animation-delay:.30s">calendario</span> '
        '<span class="hw" style="animation-delay:.38s">degli</span> '
        '<em>hackathon</em> '
        '<span class="hw" style="animation-delay:.56s">milanesi.</span>'
        '</h1>\n'
        '    <p class="hero-sub">Ogni giorno raccogliamo e verifichiamo con AI tutti gli hackathon, coding challenge e competizioni tech a Milano.</p>\n'
        '    <div class="hero-actions">\n'
        '      <a class="btn-primary" href="#events">'
        '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 7l-5 5-5-5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        'Esplora gli eventi</a>\n'
        '      <span class="hero-badge">Dati in tempo reale</span>\n'
        '    </div>\n'
        '    <div class="stats-row">\n'
        f'      <div class="stat"><div class="stat-num" data-target="{event_count}">0</div><div class="stat-label">{evt_word}</div></div>\n'
        + (f'      <div class="stat"><div class="stat-num" data-target="{len(months_set)}">0</div><div class="stat-label">{mon_word}</div></div>\n' if months_set else f'      <div class="stat"><div class="stat-num">{mon_count}</div><div class="stat-label">{mon_word}</div></div>\n')
        + '      <div class="stat"><div class="stat-num">24h</div><div class="stat-label">refresh</div></div>\n'
        '    </div>\n'
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

        desc_html = f'<p class="card-desc">{desc}</p>' if desc else ""
        search_blob = _escape(f"{title} {desc} {location} {source_esc}".lower())
        delay = f"animation-delay:{idx * 0.06:.2f}s"

        parts.append(
            f'<article class="card" data-date="{date_iso}" data-search="{search_blob}" style="{delay}">'
            f'<div class="card-left">{badge}</div>'
            f'<div class="card-body">'
            f'<h2 class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>'
            f'<div class="card-meta">{meta_html}</div>'
            f'{desc_html}'
            f'<div class="card-footer">'
            f'<span class="source-dot">{source_esc}</span>'
            f'<a href="{url}" class="card-link" target="_blank" rel="noopener">Vedi evento{arrow}</a>'
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

    now_str = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d %b %Y, %H:%M")
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
