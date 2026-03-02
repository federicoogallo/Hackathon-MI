"""
Genera una pagina HTML statica con tutti gli hackathon futuri confermati.

Output: docs/index.html — servita via GitHub Pages.
Viene rigenerata ad ogni run della pipeline.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, date
from pathlib import Path

import config
from models import HackathonEvent, _normalize_title

logger = logging.getLogger(__name__)

_MONTHS_IT = [
    "gen", "feb", "mar", "apr", "mag", "giu",
    "lug", "ago", "set", "ott", "nov", "dic",
]


def _fmt_date(date_str: str) -> str:
    """Formatta date_str in '15 mar 2026'. Ritorna stringa vuota se non parsabile."""
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


# ─── HTML template ──────────────────────────────────────────────────────────

_HTML_HEAD = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hackathon Milano</title>
<style>
  :root {{
    --bg: #0f1117;
    --card: #1a1d27;
    --border: #2a2d3e;
    --accent: #6c63ff;
    --accent2: #00d2ff;
    --text: #e0e0e0;
    --muted: #8888aa;
    --tag-bg: #23263a;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.6;
    padding: 2rem 1rem 4rem;
  }}
  header {{
    max-width: 720px;
    margin: 0 auto 2.5rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 1.5rem;
  }}
  header h1 {{
    font-size: 1.7rem;
    font-weight: 700;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: .3rem;
  }}
  header p {{ color: var(--muted); font-size: 0.9rem; }}
  .count-badge {{
    display: inline-block;
    background: var(--tag-bg);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 2px 12px;
    font-size: 0.82rem;
    color: var(--muted);
    margin-top: .6rem;
  }}
  .cards {{
    max-width: 720px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    transition: border-color .2s;
  }}
  .card:hover {{ border-color: var(--accent); }}
  .card-title {{
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: .5rem;
  }}
  .card-title a {{
    color: var(--text);
    text-decoration: none;
  }}
  .card-title a:hover {{ color: var(--accent2); }}
  .meta {{
    display: flex;
    flex-wrap: wrap;
    gap: .4rem .8rem;
    font-size: 0.82rem;
    color: var(--muted);
    margin-bottom: .6rem;
  }}
  .meta span {{ display: flex; align-items: center; gap: .25rem; }}
  .desc {{
    font-size: 0.85rem;
    color: #aaa;
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}
  .tag {{
    display: inline-block;
    background: var(--tag-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1px 8px;
    font-size: 0.75rem;
    color: var(--muted);
    margin-top: .5rem;
  }}
  .empty {{
    max-width: 720px;
    margin: 3rem auto;
    text-align: center;
    color: var(--muted);
  }}
  footer {{
    max-width: 720px;
    margin: 3rem auto 0;
    text-align: center;
    font-size: 0.78rem;
    color: var(--muted);
    border-top: 1px solid var(--border);
    padding-top: 1rem;
  }}
</style>
</head>
<body>
"""

_HTML_FOOT = """
<footer>
  Aggiornato automaticamente · <a href="https://github.com/federicoogallo/Hackathon-MI" style="color:#6c63ff">Hackathon-MI</a>
</footer>
</body>
</html>
"""


def generate_html(events_path: Path | None = None, output_path: Path | None = None) -> Path:
    """Legge events.json e scrive docs/index.html con gli hackathon futuri.

    Returns:
        Il percorso del file HTML generato.
    """
    events_path = events_path or config.EVENTS_FILE
    output_path = output_path or (config.BASE_DIR / "docs" / "index.html")

    # Carica eventi
    all_events: list[dict] = []
    if events_path.exists():
        try:
            data = json.loads(events_path.read_text(encoding="utf-8"))
            all_events = data.get("events", [])
            if isinstance(all_events, dict):
                all_events = list(all_events.values())
        except Exception as e:
            logger.warning("Impossibile leggere events.json per HTML export: %s", e)

    last_check = ""
    if events_path.exists():
        try:
            data = json.loads(events_path.read_text(encoding="utf-8"))
            last_check = data.get("last_check", "")
        except Exception:
            pass

    # Filtra: solo confermati dall'LLM e futuri
    upcoming = [e for e in all_events if e.get("is_hackathon") and _is_upcoming(e)]
    upcoming.sort(key=_sort_key)

    now_str = datetime.now().strftime("%d %b %Y, %H:%M")
    subtitle = f"Aggiornato: {now_str}"
    if last_check:
        try:
            dt = datetime.fromisoformat(last_check)
            subtitle = f"Ultima scansione: {dt.strftime('%d %b %Y alle %H:%M')}"
        except Exception:
            pass

    # Costruisci HTML
    parts = [_HTML_HEAD]
    parts.append(f"""
<header>
  <h1>🏆 Hackathon Milano</h1>
  <p>Hackathon futuri confermati a Milano e dintorni.</p>
  <span class="count-badge">{len(upcoming)} evento{'i' if len(upcoming) != 1 else ''} · {subtitle}</span>
</header>
<main class="cards">
""")

    if not upcoming:
        parts.append("""
<div class="empty">
  <p style="font-size:2rem">🔍</p>
  <p>Nessun hackathon futuro confermato al momento.</p>
  <p style="margin-top:.5rem;font-size:.85rem">La lista si aggiorna automaticamente ogni giorno.</p>
</div>
""")
    else:
        for e in upcoming:
            title = _escape((e.get("title") or "Senza titolo").strip())
            url = _escape(e.get("url") or "#")
            date_str = _fmt_date(e.get("date_str") or "")
            location = _escape((e.get("location") or "").strip())
            organizer = _escape((e.get("organizer") or "").strip())
            source = _escape((e.get("source") or "").strip())

            desc_raw = (e.get("description") or "").strip().replace("\n", " ")
            if len(desc_raw) > 300:
                desc_raw = desc_raw[:300].rsplit(" ", 1)[0] + "…"
            desc = _escape(desc_raw)

            meta_parts = []
            if date_str:
                meta_parts.append(f'<span>📅 {date_str}</span>')
            if location:
                meta_parts.append(f'<span>📍 {location}</span>')
            if organizer:
                meta_parts.append(f'<span>🏢 {organizer}</span>')

            meta_html = "\n      ".join(meta_parts)

            parts.append(f"""
<article class="card">
  <div class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
  <div class="meta">
      {meta_html}
  </div>
  {'<p class="desc">' + desc + '</p>' if desc else ''}
  <span class="tag">{source}</span>
</article>
""")

    parts.append("</main>")
    parts.append(_HTML_FOOT)

    html = "\n".join(parts)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("HTML generato: %s (%d eventi)", output_path, len(upcoming))
    return output_path
