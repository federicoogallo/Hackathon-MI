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
import os
import re
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import config

logger = logging.getLogger(__name__)

_MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
_MONTHS_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]

# Host canonico del sito, condiviso con il sito Next (lib/data.ts) e con il
# generatore del mirror (html_export.py): per cambiare dominio basta impostare
# NEXT_PUBLIC_SITE_URL.
SITE_URL = (
    os.environ.get("NEXT_PUBLIC_SITE_URL", "").strip()
    or "https://hackathon-milano.vercel.app"
).rstrip("/")

TABLE_START = "<!-- HACKATHON_TABLE_START -->"
TABLE_END = "<!-- HACKATHON_TABLE_END -->"


def _calendar_date(value: str) -> date | None:
    """Stessi formati di calendarDate in lib/event-facts.ts, senza inferire giorni."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    italian = re.fullmatch(r"(\d{1,2})\s*([a-z]+)\s*(\d{4})", value.lower())
    if italian and italian[2] in _MONTHS_IT:
        value = f"{italian[3]}-{_MONTHS_IT.index(italian[2]) + 1:02d}-{int(italian[1]):02d}"
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:$|T\d{2}:\d{2})", value)
    if not match:
        return None
    try:
        return date.fromisoformat(match[1])
    except ValueError:
        return None


def _fmt_date(value: str) -> str:
    """Formatta soltanto date verificate preparate dal registro editoriale."""
    parsed = _calendar_date(value)
    return f"{parsed.day} {_MONTHS_EN[parsed.month - 1]} {parsed.year}" if parsed else "To verify"


def _today_rome() -> date:
    return datetime.now(ZoneInfo("Europe/Rome")).date()


def _safe_source_url(value: str) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
            return value.strip()
    except ValueError:
        pass
    return ""


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise ValueError(f"Invalid event registry: {path}")
    return records


def _prepare_events(all_events: list[dict], details: list[dict], exclusions: list[dict]) -> list[dict]:
    """Applica le stesse selezioni del calendario senza attestare dati storici."""
    reviewed = {record["id"]: record for record in details}
    excluded = {record["id"] for record in exclusions}
    today = _today_rome()
    upcoming = []
    for event in all_events:
        if not isinstance(event, dict) or not event.get("is_hackathon"):
            continue
        if not _safe_source_url(event.get("url")) or event.get("id") in excluded:
            continue
        if event.get("review_status") in {"manual_rejected", "rejected"}:
            continue

        facts = reviewed.get(event.get("id"))
        end = _calendar_date(facts["endDate"] if facts else event.get("date_str", ""))
        if end and end < today:
            continue

        upcoming.append({
            **event,
            "title": facts["title"] if facts else event.get("title", ""),
            "url": facts["url"] if facts else event["url"],
            "date_str": facts["startDate"] if facts else "",
            "end_date": facts["endDate"] if facts else "",
            "location": facts["location"] if facts else event.get("location", ""),
            "source_label": facts["sourceLabel"] if facts else _source_label(event.get("source") or ""),
        })

    return sorted(upcoming, key=lambda event: _calendar_date(event["date_str"]) or date.max)


def _escape_md(s: str) -> str:
    """Escape pipe e newline per celle di tabella Markdown."""
    return s.replace("|", "\\|").replace("\n", " ").strip()


def _source_label(source: str) -> str:
    """Keep provenance readable without exposing internal identifier formatting."""
    labels = {
        "web_search": "Web search",
        "eventbrite_web": "Eventbrite",
        "manual_approved": "Manual review",
        "gdg": "GDG",
        "mlh": "MLH",
    }
    return labels.get(source, source.replace("_", " ").strip().title())


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
        if e.get("end_date") and e["end_date"] != e.get("date_str"):
            date_str += f" – {_fmt_date(e['end_date'])}"
        location = _escape_md((e.get("location") or "To verify").strip())
        source = _escape_md(e.get("source_label") or _source_label((e.get("source") or "").strip()))

        # Nome con link
        if url:
            name_cell = f"[{title}]({url})"
        else:
            name_cell = title

        lines.append(f"| {name_cell} | {date_str} | {location} | {source} |")

    return "\n".join(lines)


def generate_readme_table(events_path=None, readme_path=None, *, details_path=None, exclusions_path=None) -> Path:
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

    details = _load_records(Path(details_path or config.BASE_DIR / "data" / "event_details.json"))
    exclusions = _load_records(Path(exclusions_path or config.BASE_DIR / "data" / "event_exclusions.json"))
    upcoming = _prepare_events(all_events, details, exclusions)

    # Costruisci tabella
    now_str = datetime.now(ZoneInfo("Europe/Rome")).strftime("%b %d, %Y %H:%M %Z")
    table_section = _build_table(upcoming) if upcoming else "_No upcoming hackathons at this time._"

    new_content = f"""{TABLE_START}

> **{len(upcoming)} hackathon{'s' if len(upcoming) != 1 else ''}** coming up in Milan \u00b7 Last updated: {now_str}
>
> **[View the full website]({SITE_URL}/)** for search, filters and details.

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
            updated = pattern.sub(lambda _match: new_content, old_text)
        else:
            # Marker non trovati: aggiungi dopo il primo heading
            updated = old_text + "\n\n" + new_content + "\n"
    else:
        # No existing README: create a minimal one
        updated = f"""# Hackathon Milano

Find upcoming hackathons in Milan and verify details with their original sources.

**[Explore the website]({SITE_URL}/)**

{new_content}
"""

    readme.write_text(updated, encoding="utf-8")
    logger.info("README aggiornato: %s (%d hackathon)", readme, len(upcoming))
    return readme
