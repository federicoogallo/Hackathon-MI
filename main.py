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
from collectors.eventbrite_web import EventbriteWebCollector
from collectors.taikai import TaikaiCollector
from collectors.meetup import MeetupCollector
from collectors.hackathon_com import HackathonComCollector
from collectors.mlh import MLHCollector
from collectors.codemotion import CodemotionCollector
from collectors.talent_garden import TalentGardenCollector
from collectors.cariplo_factory import CariploFactoryCollector
from collectors.startup_italia import StartupItaliaCollector
from collectors.dorahacks import DoraHacksCollector
from collectors.hackerearth import HackerEarthCollector
from collectors.devfolio import DevfolioCollector
from collectors.challengerocket import ChallengeRocketCollector
from collectors.unstop import UnstopCollector
from collectors.lablab import LablabCollector
from collectors.comune_milano import ComuneMilanoCollector
from collectors.camera_commercio import CameraCommercioCollector
from collectors.regione_lombardia import RegioneLombardiaCollector
from filters.keyword_filter import keyword_filter_batch
from filters.llm_filter import llm_filter, llm_dedup
from storage.json_store import EventStore
from notifiers.telegram import notify_run_summary
from utils.html_export import generate_html
from utils.readme_export import generate_readme_table

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
        # ── Tier 0: Original collectors ──
        EventbriteCollector(),
        WebSearchCollector(),
        InnovUpCollector(),
        LumaCollector(),
        DevpostCollector(),
        PoliHubCollector(),
        UniversitiesCollector(),
        RedditCollector(),
        EventbriteWebCollector(),
        TaikaiCollector(),
        # ── Tier 1: High-impact new sources ──
        MeetupCollector(),
        HackathonComCollector(),
        MLHCollector(),
        CodemotionCollector(),
        TalentGardenCollector(),
        CariploFactoryCollector(),
        StartupItaliaCollector(),
        # ── Tier 2: International platforms ──
        DoraHacksCollector(),
        HackerEarthCollector(),
        DevfolioCollector(),
        ChallengeRocketCollector(),
        UnstopCollector(),
        LablabCollector(),
        # ── Tier 3: Institutional sources ──
        ComuneMilanoCollector(),
        CameraCommercioCollector(),
        RegioneLombardiaCollector(),
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


def _event_is_upcoming_dict(e: dict) -> bool:
    """Verifica se un evento (dict) è futuro o senza data."""
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


def deduplicate_against_store(
    events: list[HackathonEvent], store: EventStore
) -> list[HackathonEvent]:
    """Rimuove eventi già nello storico (dedup livello 1 + 2 + 3).

    Include anche dedup intra-batch: eventi nuovi nella stessa run
    vengono confrontati tra loro con fuzzy title matching.
    """
    from difflib import SequenceMatcher
    from models import _normalize_title

    new_events: list[HackathonEvent] = []
    seen_in_batch: set[str] = set()

    for event in events:
        # Dedup intra-batch (stesso URL da collector diversi nella stessa run)
        if event.id in seen_in_batch:
            continue
        seen_in_batch.add(event.id)

        # Dedup vs storico (livello 1: URL esatto + livello 2: fuzzy + livello 3: date+keyword)
        if store.is_duplicate(event):
            continue

        # Dedup intra-batch fuzzy (titoli simili nella stessa run)
        is_intra_dup = False
        for existing in new_events:
            ratio = SequenceMatcher(
                None, event.title_normalized, existing.title_normalized
            ).ratio()
            if ratio >= config.FUZZY_DEDUP_THRESHOLD:
                if event.url not in existing.alternate_urls:
                    existing.alternate_urls.append(event.url)
                    logger.info(
                        "Intra-batch fuzzy: '%s' ≈ '%s'",
                        event.title, existing.title,
                    )
                is_intra_dup = True
                break
        if is_intra_dup:
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

    # ── Protezione anti-sovrascrittura ──
    # Se c'erano candidati keyword ma l'LLM li ha scartati TUTTI,
    # potrebbe essere per errori API (non risultati legittimi).
    # Controlliamo se tutti gli eventi hanno confidence=0.0 (segno di API error).
    # In quel caso, mantieni lo storico e l'HTML intatti.
    if post_keyword_count >= 5 and post_llm_count == 0:
        api_error_count = sum(
            1 for e in keyword_passed
            if getattr(e, "confidence", 1.0) == 0.0
        )
        if api_error_count == post_keyword_count:
            logger.warning(
                "⚠️  LLM ha fallito su tutti i %d candidati (probabili errori API) — "
                "storico NON sovrascritto per preservare i dati precedenti.",
                post_keyword_count,
            )

            # Rigenera comunque HTML e README (con dati dello storico esistente)
            # per aggiornare il timestamp "Last updated" nel banner.
            try:
                generate_html()
                logger.info("HTML page rigenerata (storico preservato)")
            except Exception as e:
                logger.warning("Impossibile rigenerare HTML page: %s", e)
            try:
                generate_readme_table()
                logger.info("README.md aggiornato (storico preservato)")
            except Exception as e:
                logger.warning("Impossibile aggiornare README.md: %s", e)

            elapsed = (datetime.now() - start_time).total_seconds()
            if not dry_run:
                total_upcoming = sum(
                    1 for ev in store.all_events()
                    if ev.get("is_hackathon") and _event_is_upcoming_dict(ev)
                )
                page_url = "https://federicoogallo.github.io/Hackathon-MI/"
                notify_run_summary(
                    new_events=0,
                    total_upcoming=total_upcoming,
                    elapsed_seconds=elapsed,
                    failed_collectors=[f.split(":")[0] for f in failed_collectors],
                    page_url=page_url,
                )
            logger.info("=" * 60)
            logger.info("Run completata in %.1f secondi (storico preservato)", elapsed)
            logger.info("=" * 60)
            return

    # 5b. Dedup semantica con LLM (rimuove duplicati con titoli/URL diversi)
    llm_confirmed = llm_dedup(llm_confirmed)
    post_llm_dedup_count = len(llm_confirmed)
    if post_llm_dedup_count < post_llm_count:
        logger.info(
            "Post LLM dedup: %d -> %d unici",
            post_llm_count, post_llm_dedup_count,
        )

    # 5c. Filtra eventi passati post-LLM (ora le date sono estratte dal LLM)
    pre_date_filter2 = len(llm_confirmed)
    llm_confirmed = [e for e in llm_confirmed if e.is_upcoming()]
    post_date_filter2 = len(llm_confirmed)
    if pre_date_filter2 > post_date_filter2:
        logger.info(
            "Post LLM date filter: %d → %d (rimossi %d eventi passati grazie a date LLM)",
            pre_date_filter2, post_date_filter2, pre_date_filter2 - post_date_filter2,
        )

    # 6. Salva nuovi hackathon nello storico
    notified_count = len(llm_confirmed)
    for event in llm_confirmed:
        event.is_hackathon = True
        store.add_event(event)
        logger.info("%sNuovo hackathon: %s", "[DRY RUN] " if dry_run else "", event.title)

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

    # 9. Genera pagina HTML statica (docs/index.html → GitHub Pages)
    try:
        generate_html()
        logger.info("HTML page generata: docs/index.html")
    except Exception as e:
        logger.warning("Impossibile generare HTML page: %s", e)

    # 9b. Aggiorna tabella hackathon nel README.md
    try:
        generate_readme_table()
        logger.info("README.md aggiornato con tabella hackathon")
    except Exception as e:
        logger.warning("Impossibile aggiornare README.md: %s", e)

    # 10. Conta hackathon futuri confermati nello storico (per summary)
    total_upcoming = sum(
        1 for ev in store.all_events()
        if ev.get("is_hackathon") and _event_is_upcoming_dict(ev)
    )

    # 11. Invia sempre il summary Telegram (anche se 0 nuovi eventi)
    elapsed = (datetime.now() - start_time).total_seconds()
    if not dry_run:
        page_url = "https://federicoogallo.github.io/Hackathon-MI/"
        notify_run_summary(
            new_events=notified_count,
            total_upcoming=total_upcoming,
            elapsed_seconds=elapsed,
            failed_collectors=[f.split(":")[0] for f in failed_collectors],
            page_url=page_url,
        )

    # Riepilogo finale nei log
    logger.info("=" * 60)
    logger.info("Run completata in %.1f secondi", elapsed)
    logger.info(
        "Risultato: %d raw → %d post-dedup → %d post-kw → %d confermati",
        raw_count, post_dedup_count, post_keyword_count, post_llm_count,
    )
    logger.info("Nuovi hackathon notificati: %d", notified_count)
    logger.info("Hackathon futuri in storico: %d", total_upcoming)
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
