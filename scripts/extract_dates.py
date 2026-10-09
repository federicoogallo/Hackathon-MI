#!/usr/bin/env python3
"""Segnala le date mancanti senza completarle o modificare l'archivio.

L'estrazione tramite LLM è stata rimossa: una data può essere aggiunta solo
recuperandola dalla fonte dell'evento e verificandone il significato.

Usage:
    python scripts/extract_dates.py
    python scripts/extract_dates.py --dry-run  # alias compatibile, sempre sola lettura
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("extract-dates")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostica delle date mancanti, senza scritture")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Opzione mantenuta per compatibilità: il comando è sempre in sola lettura",
    )
    parser.add_argument("--events-file", type=Path, default=config.EVENTS_FILE)
    args = parser.parse_args(argv)

    try:
        data = json.loads(args.events_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Impossibile leggere l'archivio: %s", exc)
        return 1

    events = data.get("events") if isinstance(data, dict) else None
    if isinstance(events, dict):
        events = list(events.values())
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        logger.error("Formato dell'archivio non riconosciuto")
        return 1

    needs_date = [event for event in events if not str(event.get("date_str") or "").strip()]
    logger.info("Eventi senza data: %d/%d", len(needs_date), len(events))
    for event in needs_date:
        logger.info("Da verificare nella fonte: %s — %s", event.get("title", ""), event.get("url", ""))

    logger.info(
        "Diagnostica completata, nessun file modificato e nessuna chiamata LLM. "
        "Per le date mancanti consultare la pagina originale o i suoi dati strutturati; "
        "non convertire un mese senza giorno in una data precisa."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
