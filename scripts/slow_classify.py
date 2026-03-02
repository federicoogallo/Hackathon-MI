#!/usr/bin/env python3
"""
Recovery script — classifica gli eventi uno alla volta con pause lunghe
per evitare il rate limit Groq (6,000 TPM free tier).

Chiama Groq DIRETTAMENTE senza retry (per evitare che le retry brucino
token e peggiorino il rate limit).

Usage:
    python scripts/slow_classify.py              # Run completo
    python scripts/slow_classify.py --delay 65   # Pausa personalizzata tra chiamate
    python scripts/slow_classify.py --skip-collect  # Usa candidati già salvati
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Aggiungi il progetto al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from models import HackathonEvent
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
from filters.keyword_filter import keyword_filter_batch
from filters.llm_filter import _get_system_prompt, _build_user_prompt, _parse_llm_response, LLMResult, llm_dedup
from storage.json_store import EventStore
from utils.html_export import generate_html

from groq import Groq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("slow-classify")

# ─── Config ───────────────────────────────────────────────────────────────

BATCH_SIZE = 3          # eventi per chiamata (piccolo per stare sotto TPM)
DEFAULT_DELAY = 10      # secondi tra chiamate — 8B ha 131K TPM, delay breve basta

# Per il recovery, usa il modello 8B che ha 131,072 TPM (vs 6,000 del 70B)
RECOVERY_MODEL = "llama-3.1-8b-instant"


def collect_all() -> list[HackathonEvent]:
    """Raccoglie eventi da tutti i collector (sequenziale per sicurezza)."""
    collectors = [
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
    ]
    all_events = []
    for c in collectors:
        try:
            events = c.collect()
            logger.info("  %s: %d eventi", c.name, len(events))
            all_events.extend(events)
        except Exception as e:
            logger.error("  %s: ERRORE %s", c.name, e)
    return all_events


def _call_groq_no_retry(events: list[HackathonEvent]) -> list[LLMResult]:
    """Chiama Groq UNA SOLA VOLTA, senza retry, max_retries=0 nel client."""
    try:
        client = Groq(api_key=config.GROQ_API_KEY, max_retries=0)
        system_prompt = _get_system_prompt()
        user_prompt = _build_user_prompt(events)

        response = client.chat.completions.create(
            model=RECOVERY_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "[]"
        return _parse_llm_response(content, len(events))

    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "rate_limit" in error_str.lower():
            logger.warning("  Rate limit Groq: %s", error_str[:80])
        else:
            logger.error("  Errore Groq: %s", error_str[:120])
        return [LLMResult(is_hackathon=False, confidence=0.0, reason="API error") for _ in events]


def slow_classify(events: list[HackathonEvent], delay: int) -> list[HackathonEvent]:
    """Classifica eventi in micro-batch con pause lunghe."""
    confirmed = []
    total = len(events)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    consecutive_errors = 0

    for batch_idx in range(n_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total)
        batch = events[start_idx:end_idx]

        # Pausa tra batch (non prima del primo)
        if batch_idx > 0:
            # Se ci sono stati errori consecutivi, aumenta il delay
            actual_delay = delay * (2 if consecutive_errors >= 2 else 1)
            logger.info("  ⏳ Pausa %ds (batch %d/%d)...", actual_delay, batch_idx + 1, n_batches)
            time.sleep(actual_delay)

        logger.info("  📡 Batch %d/%d (%d eventi)...", batch_idx + 1, n_batches, len(batch))
        results = _call_groq_no_retry(batch)

        batch_has_error = False
        for event, result in zip(batch, results):
            event.is_hackathon = result.is_hackathon
            event.confidence = result.confidence

            if result.confidence == 0.0 and result.reason == "API error":
                logger.warning("    ⚠️  API ERROR: '%s'", event.title[:60])
                batch_has_error = True
            elif result.is_hackathon and result.confidence >= config.LLM_CONFIDENCE_THRESHOLD:
                confirmed.append(event)
                logger.info("    ✅ '%s' (conf=%.2f) %s", event.title[:60], result.confidence, result.reason)
            else:
                logger.info("    ❌ '%s' (conf=%.2f) %s", event.title[:60], result.confidence, result.reason)

        if batch_has_error:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                logger.error("  ❌ 3 batch consecutivi con errore. Stop.")
                break
        else:
            consecutive_errors = 0

    return confirmed


def main():
    parser = argparse.ArgumentParser(description="Recovery: classifica lenta anti-rate-limit")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY,
                        help=f"Secondi di pausa tra batch (default: {DEFAULT_DELAY})")
    parser.add_argument("--skip-collect", action="store_true",
                        help="Salta la raccolta e usa i candidati salvati in /tmp/candidates.json")
    args = parser.parse_args()

    start = datetime.now()
    logger.info("=" * 60)
    logger.info("SLOW CLASSIFY — Recovery anti-rate-limit")
    logger.info("Batch size: %d | Delay: %ds", BATCH_SIZE, args.delay)
    logger.info("=" * 60)

    # ── 1. Raccolta ──
    candidates_path = Path("/tmp/hackathon_candidates.json")

    if args.skip_collect and candidates_path.exists():
        logger.info("Carico candidati da %s", candidates_path)
        with open(candidates_path) as f:
            data = json.load(f)
        keyword_passed = [HackathonEvent(**d) for d in data]
        logger.info("Caricati %d candidati", len(keyword_passed))
    else:
        logger.info("1. Raccolta eventi...")
        all_events = collect_all()
        logger.info("Totale raw: %d", len(all_events))

        # Dedup intra-batch
        seen = set()
        unique = []
        for e in all_events:
            if e.id not in seen:
                seen.add(e.id)
                unique.append(e)
        logger.info("Post dedup: %d", len(unique))

        # Keyword filter
        logger.info("2. Keyword filter...")
        keyword_passed, kw_discarded = keyword_filter_batch(unique)
        logger.info("Post keyword: %d passati, %d scartati", len(keyword_passed), kw_discarded)

        # Date filter
        pre = len(keyword_passed)
        keyword_passed = [e for e in keyword_passed if e.is_upcoming()]
        logger.info("Post date filter: %d → %d", pre, len(keyword_passed))

        # Salva candidati per eventuale --skip-collect
        cand_data = [
            {
                "title": e.title,
                "url": e.url,
                "source": e.source,
                "description": e.description,
                "date_str": e.date_str,
                "location": e.location,
            }
            for e in keyword_passed
        ]
        candidates_path.write_text(json.dumps(cand_data, indent=2, ensure_ascii=False))
        logger.info("Candidati salvati in %s", candidates_path)

    # ── 2. Classificazione lenta ──
    logger.info("3. Classificazione LLM (SLOW MODE)...")
    logger.info("   %d candidati, ~%d batch, ~%d minuti stimati",
                len(keyword_passed),
                (len(keyword_passed) + BATCH_SIZE - 1) // BATCH_SIZE,
                (len(keyword_passed) // BATCH_SIZE) * args.delay // 60)

    confirmed = slow_classify(keyword_passed, args.delay)
    logger.info("Post LLM: %d confermati", len(confirmed))

    if not confirmed:
        # Controlla se tutti sono API error
        api_errors = sum(1 for e in keyword_passed if getattr(e, "confidence", 1.0) == 0.0)
        if api_errors == len(keyword_passed):
            logger.error("❌ Tutti i candidati hanno dato API error. Rate limit ancora attivo.")
            logger.info("   Riprova tra qualche minuto con: python scripts/slow_classify.py --skip-collect")
            return
        else:
            logger.info("Nessun hackathon confermato (risultato legittimo)")

    # ── 3. Dedup semantica ──
    if len(confirmed) > 1:
        logger.info("4. Dedup semantica LLM...")
        time.sleep(args.delay)  # pausa prima della dedup
        confirmed = llm_dedup(confirmed)
        logger.info("Post dedup: %d unici", len(confirmed))

    # ── 4. Salva in events.json ──
    logger.info("5. Salvataggio...")
    store = EventStore()

    for event in confirmed:
        event.is_hackathon = True
        store.add_event(event)

    store.save_with_timestamp(start.isoformat())
    logger.info("Salvati %d eventi totali in events.json", store.count)

    # ── 5. Genera HTML ──
    logger.info("6. Genera pagina HTML...")
    try:
        generate_html()
        logger.info("HTML generata: docs/index.html")
    except Exception as e:
        logger.error("Errore generazione HTML: %s", e)

    # ── Report ──
    elapsed = (datetime.now() - start).total_seconds()
    logger.info("=" * 60)
    logger.info("COMPLETATO in %.0f secondi", elapsed)
    logger.info("Risultato: %d confermati su %d candidati", len(confirmed), len(keyword_passed))
    logger.info("Eventi totali in storico: %d", store.count)
    logger.info("=" * 60)

    # Salva report
    report = {
        "date": start.strftime("%Y-%m-%d %H:%M"),
        "mode": "slow_classify",
        "raw_events": len(keyword_passed),
        "post_llm": len(confirmed),
        "total_stored": store.count,
    }
    report_path = Path(config.DATA_DIR) / "last_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
