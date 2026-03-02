#!/usr/bin/env python3
"""
Estrae le date degli eventi già confermati in events.json usando il LLM.
Non riclassifica (mantiene is_hackathon=true), solo estrae le date mancanti.

Usage:
    python scripts/extract_dates.py
    python scripts/extract_dates.py --dry-run  # mostra senza salvare
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from models import HackathonEvent
from utils.html_export import generate_html
from groq import Groq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("extract-dates")

# Usa il modello 8B (131K TPM) per evitare rate limit
MODEL = "llama-3.1-8b-instant"

DATE_EXTRACTION_PROMPT = """Sei un estrattore di date per eventi hackathon. Per ogni evento, estrai la data di inizio in formato YYYY-MM-DD.

DATA ODIERNA: {current_date}

REGOLE:
- Cerca la data nel titolo, descrizione, URL
- Se ci sono più giorni (es. "26-27 febbraio 2026"), usa il PRIMO giorno → "2026-02-26"
- Se trovi solo mese/anno senza giorno, usa il primo del mese → "maggio 2026" → "2026-05-01"
- Se la data è PASSATA (precedente a {current_date}), restituiscila comunque (verrà usata per filtrare)
- Se non riesci a determinare la data → null

Rispondi SOLO con JSON: {{"results": [{{"index": 0, "event_date": "YYYY-MM-DD o null"}}]}}"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    events_path = config.EVENTS_FILE
    if not events_path.exists():
        logger.error("events.json non trovato")
        return

    data = json.loads(events_path.read_text(encoding="utf-8"))
    events = data.get("events", [])
    logger.info("Caricati %d eventi", len(events))

    # Filtra quelli senza data
    needs_date = [e for e in events if not (e.get("date_str") or "").strip()]
    has_date = [e for e in events if (e.get("date_str") or "").strip()]
    logger.info("  Con data: %d | Senza data: %d", len(has_date), len(needs_date))

    if not needs_date:
        logger.info("Tutti gli eventi hanno già una data!")
        return

    # Costruisci prompt
    items = []
    for i, e in enumerate(needs_date):
        desc = (e.get("description") or "")[:300]
        items.append(
            f'{i}. Titolo: "{e["title"]}"\n'
            f'   URL: {e["url"]}\n'
            f'   Descrizione: "{desc}"'
        )
    user_prompt = "Estrai le date di questi eventi:\n\n" + "\n\n".join(items)

    now = datetime.now()
    system_prompt = DATE_EXTRACTION_PROMPT.format(
        current_date=now.strftime("%d %B %Y"),
    )

    logger.info("Chiamata LLM per %d eventi...", len(needs_date))
    try:
        client = Groq(api_key=config.GROQ_API_KEY, max_retries=0)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
    except Exception as e:
        logger.error("Errore Groq: %s", e)
        return

    # Parse risposta
    try:
        result_data = json.loads(content)
        results = result_data.get("results", [])
    except json.JSONDecodeError:
        logger.error("JSON non valido: %s", content[:200])
        return

    # Applica date
    updated = 0
    for r in results:
        idx = r.get("index")
        date_val = r.get("event_date")
        if idx is None or idx >= len(needs_date):
            continue
        if date_val and str(date_val).lower() not in ("null", "none"):
            event = needs_date[idx]
            old = event.get("date_str", "")
            event["date_str"] = str(date_val)
            updated += 1
            logger.info("  📅 '%s' → %s", event["title"][:50], date_val)
        else:
            logger.info("  ❓ '%s' → nessuna data trovata", needs_date[idx]["title"][:50])

    logger.info("Date estratte: %d/%d", updated, len(needs_date))

    if args.dry_run:
        logger.info("[DRY RUN] Nessun file modificato")
        return

    # Filtra eventi passati
    updated_events = []
    removed = 0
    for e in events:
        ev = HackathonEvent(
            title=e.get("title", ""),
            url=e.get("url", ""),
            source=e.get("source", ""),
            date_str=e.get("date_str", ""),
        )
        if ev.is_past():
            logger.info("  🗑️  Rimosso (passato): '%s' [%s]", e["title"][:50], e.get("date_str"))
            removed += 1
        else:
            updated_events.append(e)

    if removed:
        logger.info("Rimossi %d eventi passati", removed)

    # Ordina: eventi con data prima (per data), poi senza data
    def sort_key(e):
        ds = e.get("date_str", "")
        if ds:
            try:
                ev = HackathonEvent(title="", url="", source="", date_str=ds)
                d = ev.parsed_date()
                if d:
                    return (0, d.isoformat())
            except Exception:
                pass
        return (1, "9999-12-31")

    updated_events.sort(key=sort_key)

    # Salva
    data["events"] = updated_events
    data["last_check"] = now.isoformat()
    events_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Salvato events.json: %d eventi", len(updated_events))

    # Rigenera HTML
    try:
        generate_html()
        logger.info("HTML rigenerata")
    except Exception as e:
        logger.error("Errore HTML: %s", e)


if __name__ == "__main__":
    main()
