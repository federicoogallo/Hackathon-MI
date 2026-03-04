"""
Genera la sezione tabella del README.md con gli hackathon futuri confermati.

Stile ispirato a https://github.com/LorenzoLaCorte/european-tech-internships-2026
La tabella viene inserita tra due marker nel README.md per preservare il resto del file.

Marker:
  <!-- HACKATHON_TABLE_START -->
  <!-- HACKATHON_TABLE_END -->
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, date, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from models import HackathonEvent

logger = logging.getLogger(__name__)

_MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

TABLE_START = "<!-- HACKATHON_TABLE_START -->"
TABLE_END = "<!-- HACKATHON_TABLE_END -->"


def _fmt_date(date_str: str) -> str:
    """Formatta data in 'DD Mon YYYY'. Ritorna 'TBD' se non parsabile."""
    if not (date_str or "").strip():
        return "TBD"
    try:
        ev = HackathonEvent(title="", url="", source="", date_str=date_str)
        d = ev.parsed_date()
        if d:
            return f"{d.day} {_MONTHS_EN[d.month - 1]} {d.year}"
    except Exception:
        pass
    cleaned = date_str.strip()[:25]
    return cleaned if cleaned else "TBD"


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
        return (0, d) if d is not None else (1, date(9999, 12, 31))
    except Exception:
        return (1, date(9999, 12, 31))


def _escape_md(s: str) -> str:
    """Escape pipe e newline per celle di tabella Markdown."""
    return s.replace("|", "\\|").replace("\n", " ").strip()


def _build_table(upcoming: list[dict]) -> str:
    """Costruisce la tabella Markdown degli hackathon."""
    lines: list[str] = []

    # Header
    lines.append("| Name | Date | Location | Source |")
    lines.append("| --- | --- | --- | --- |")

    for e in upcoming:
        title = _escape_md((e.get("title") or "Untitled").strip())
        url = (e.get("url") or "").strip()
        date_str = _fmt_date(e.get("date_str", ""))
        location = _escape_md((e.get("location") or "Milano").strip())
        source = _escape_md((e.get("source") or "").strip())

        # Nome con link
        if url:
            name_cell = f"[{title}]({url})"
        else:
            name_cell = title

        lines.append(f"| {name_cell} | {date_str} | {location} | {source} |")

    return "\n".join(lines)


def generate_readme_table(events_path=None, readme_path=None) -> Path:
    """Aggiorna la tabella hackathon nel README.md tra i marker.

    Se il README non esiste o non contiene i marker, ne crea uno con la struttura base.
    """
    events_path = events_path or config.EVENTS_FILE
    readme_path = readme_path or (config.BASE_DIR / "README.md")

    # Carica eventi
    all_events: list[dict] = []
    if Path(events_path).exists():
        try:
            data = json.loads(Path(events_path).read_text(encoding="utf-8"))
            raw = data.get("events", [])
            all_events = list(raw.values()) if isinstance(raw, dict) else raw
        except Exception as exc:
            logger.warning("Impossibile leggere events.json per README: %s", exc)

    confirmed = [e for e in all_events if e.get("is_hackathon")]
    upcoming = [e for e in confirmed if _is_upcoming(e)]
    upcoming.sort(key=_sort_key)

    # Costruisci tabella
    now_str = datetime.now(ZoneInfo("Europe/Rome")).strftime("%b %d, %Y %H:%M")
    table_section = _build_table(upcoming) if upcoming else "_No upcoming hackathons at this time._"

    new_content = f"""{TABLE_START}

> **{len(upcoming)} hackathon{'s' if len(upcoming) != 1 else ''}** coming up in Milan \u00b7 Last updated: {now_str}
>
> \U0001f310 **[View the full website](https://federicoogallo.github.io/Hackathon-MI/)** for search, filters & details.

{table_section}

{TABLE_END}"""

    # Leggi README esistente
    readme = Path(readme_path)
    if readme.exists():
        old_text = readme.read_text(encoding="utf-8")
        # Cerca e sostituisci tra i marker
        pattern = re.compile(
            re.escape(TABLE_START) + r".*?" + re.escape(TABLE_END),
            re.DOTALL,
        )
        if pattern.search(old_text):
            updated = pattern.sub(new_content, old_text)
        else:
            # Marker non trovati: aggiungi dopo il primo heading
            updated = old_text + "\n\n" + new_content + "\n"
    else:
        # No existing README: create a minimal one
        updated = f"""# \U0001f3c6 Hackathon Milan

Hackathons, coding challenges & tech competitions in Milan \u2014 updated daily with AI.

**Full website \u2192 [federicoogallo.github.io/Hackathon-MI](https://federicoogallo.github.io/Hackathon-MI/)**

{new_content}
"""

    readme.write_text(updated, encoding="utf-8")
    logger.info("README aggiornato: %s (%d hackathon)", readme, len(upcoming))
    return readme
