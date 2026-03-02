"""
Hackathon Milano Monitor — Orchestratore principale.

Pipeline:
1. Carica storico eventi
2. Esegue tutti i collector in parallelo (con error handling per ciascuno)
3. Deduplicazione a due livelli (URL esatto + fuzzy titolo)
4. Pre-filtro keyword (+ filtro eventi passati)
5. Filtro LLM (Groq — Llama 3.3 70B)
6. Notifica nuovi hackathon via Telegram
7. Salvataggio storico e ultimo report

Usage:
    python main.py              # Run completo con notifiche
    python main.py --dry-run    # Run senza notifiche (test locale)
"""

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import config
from models import BaseCollector, HackathonEvent
from collectors.eventbrite import EventbriteCollector
from collectors.web_search import WebSearchCollector
from collectors.innovup import InnovUpCollector
from collectors.luma import LumaCollector
from collectors.devpost import DevpostCollector
from collectors.polihub import PoliHubCollector
from collectors.universities import UniversitiesCollector
from collectors.reddit import RedditCollector
from filters.keyword_filter import keyword_filter_batch
from filters.llm_filter import llm_filter, llm_dedup
from storage.json_store import EventStore
from notifiers.telegram import (
    notify_new_hackathon,
)

# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hackathon-monitor")


# ─── Collector registry ────────────────────────────────────────────────────

def get_collectors() -> list[BaseCollector]:
    """Istanzia tutti i collector registrati."""
    return [
        EventbriteCollector(),
        WebSearchCollector(),
        InnovUpCollector(),
        LumaCollector(),
        DevpostCollector(),
        PoliHubCollector(),
        UniversitiesCollector(),
        RedditCollector(),
    ]


# ─── Pipeline ──────────────────────────────────────────────────────────────

def run_collectors(
    collectors: list[BaseCollector],
) -> tuple[list[HackathonEvent], list[str], list[str]]:
    """Esegue tutti i collector in parallelo.

    Returns:
        (all_events, ok_collectors, failed_collectors)
    """
    all_events: list[HackathonEvent] = []
    ok_collectors: list[str] = []
    failed_collectors: list[str] = []

    with ThreadPoolExecutor(max_workers=config.MAX_COLLECTOR_WORKERS) as executor:
        future_to_collector = {
            executor.submit(_safe_collect, c): c for c in collectors
        }

        for future in as_completed(future_to_collector):
            collector = future_to_collector[future]
            try:
                events, error = future.result()
                if error:
                    failed_collectors.append(f"{collector.name}: {error}")
                    logger.error("Collector %s fallito: %s", collector.name, error)
                else:
                    ok_collectors.append(collector.name)
                    all_events.extend(events)
                    logger.info(
                        "Collector %s: %d eventi", collector.name, len(events)
                    )
            except Exception as e:
                failed_collectors.append(f"{collector.name}: {e}")
                logger.error("Collector %s eccezione: %s", collector.name, e)

    return all_events, ok_collectors, failed_collectors


def _safe_collect(
    collector: BaseCollector,
) -> tuple[list[HackathonEvent], str | None]:
    """Wrapper per esecuzione sicura di un collector."""
    try:
        events = collector.collect()
        return events, None
    except Exception as e:
        return [], str(e)


def deduplicate_against_store(
    events: list[HackathonEvent], store: EventStore
) -> list[HackathonEvent]:
    """Rimuove eventi già nello storico (dedup livello 1 + 2)."""
    new_events: list[HackathonEvent] = []
    seen_in_batch: set[str] = set()

    for event in events:
        # Dedup intra-batch (stesso URL da collector diversi nella stessa run)
        if event.id in seen_in_batch:
            continue
        seen_in_batch.add(event.id)

        # Dedup vs storico (livello 1: URL esatto + livello 2: fuzzy titolo)
        if store.is_duplicate(event):
            continue

        new_events.append(event)

    return new_events


def run_pipeline(dry_run: bool = False) -> None:
    """Pipeline completa di raccolta, filtro e notifica."""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("Hackathon Monitor — run iniziata: %s", start_time.isoformat())
    logger.info("=" * 60)

    # 1. Carica storico
    store = EventStore()
    logger.info("Storico caricato: %d eventi", store.count)

    # 2. Esegui collector
    collectors = get_collectors()
    all_events, ok_collectors, failed_collectors = run_collectors(collectors)
    raw_count = len(all_events)
    logger.info("Totale eventi raw: %d (da %d collector)", raw_count, len(ok_collectors))

    # 3. Deduplicazione vs storico
    new_events = deduplicate_against_store(all_events, store)
    post_dedup_count = len(new_events)
    logger.info("Post dedup: %d nuovi candidati", post_dedup_count)

    # 4. Pre-filtro keyword
    keyword_passed, keyword_discarded = keyword_filter_batch(new_events)
    post_keyword_count = len(keyword_passed)
    logger.info(
        "Post keyword filter: %d passati, %d scartati",
        post_keyword_count, keyword_discarded,
    )

    # 4b. Filtra eventi passati rispetto alla data corrente
    pre_date_filter = len(keyword_passed)
    keyword_passed = [e for e in keyword_passed if e.is_upcoming()]
    post_date_filter = len(keyword_passed)
    logger.info(
        "Post date filter: %d → %d (rimosse %d eventi passati)",
        pre_date_filter, post_date_filter, pre_date_filter - post_date_filter,
    )

    # 5. Filtro LLM
    llm_confirmed, llm_discarded = llm_filter(keyword_passed)
    post_llm_count = len(llm_confirmed)
    logger.info(
        "Post LLM filter: %d confermati, %d scartati",
        post_llm_count, llm_discarded,
    )

    # 5b. Dedup semantica con LLM (rimuove duplicati con titoli/URL diversi)
    llm_confirmed = llm_dedup(llm_confirmed)
    post_llm_dedup_count = len(llm_confirmed)
    if post_llm_dedup_count < post_llm_count:
        logger.info(
            "Post LLM dedup: %d -> %d unici",
            post_llm_count, post_llm_dedup_count,
        )

    # 6. Notifica nuovi hackathon
    notified_count = 0
    for event in llm_confirmed:
        event.is_hackathon = True

        if not dry_run:
            success = notify_new_hackathon(event)
            if success:
                notified_count += 1
                logger.info("Notifica inviata: %s", event.title)
            else:
                logger.warning("Notifica fallita per: %s", event.title)
        else:
            notified_count += 1
            logger.info("[DRY RUN] Nuovo hackathon: %s — %s", event.title, event.url)

        # Aggiungi allo storico
        store.add_event(event)

    # 7. Salva report su file (accessibile via /report dal bot)
    report = {
        "date": start_time.strftime("%Y-%m-%d %H:%M"),
        "collectors_ok": len(ok_collectors),
        "collectors_total": len(collectors),
        "failed_collectors": [f.split(":")[0] for f in failed_collectors],
        "raw_events": raw_count,
        "post_dedup": post_dedup_count,
        "post_keyword": post_keyword_count,
        "post_llm": post_llm_count,
        "new_events": notified_count,
        "total_stored": store.count,
    }

    report_path = Path(config.DATA_DIR) / "last_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Report salvato in %s", report_path)

    if dry_run:
        logger.info("[DRY RUN] Report: %s", report)

    # 8. Salva storico
    store.save_with_timestamp(start_time.isoformat())

    # Riepilogo finale
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info("Run completata in %.1f secondi", elapsed)
    logger.info(
        "Risultato: %d raw → %d post-dedup → %d post-kw → %d confermati",
        raw_count, post_dedup_count, post_keyword_count, post_llm_count,
    )
    logger.info("Nuovi hackathon notificati: %d", notified_count)
    logger.info("Storico totale: %d eventi", store.count)
    logger.info("=" * 60)


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Hackathon Milano Monitor — Aggrega hackathon da fonti multiple"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Esegui senza inviare notifiche Telegram (per test locale)",
    )
    args = parser.parse_args()

    run_pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
