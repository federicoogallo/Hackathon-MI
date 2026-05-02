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
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse

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
from collectors.gdg import GDGCollector
from collectors.telespazio import TelespazioCollector
from filters.keyword_filter import keyword_filter_batch
from filters.llm_filter import llm_filter, llm_dedup
from storage.json_store import EventStore
from notifiers.telegram import notify_run_summary
from utils.html_export import generate_html
from utils.readme_export import generate_readme_table
from utils.review_queue import (
    build_review_queue,
    load_review_decisions,
    save_review_queue,
)

# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hackathon-monitor")


@dataclass
class CollectorRun:
    """Esito diagnostico di un singolo collector."""

    name: str
    ok: bool
    event_count: int
    duration_seconds: float
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "event_count": self.event_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "error": self.error,
        }

_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_MILAN_RE = re.compile(r"\bmilan(?:o)?\b", re.I)
_NON_MILAN_CITY_RE = re.compile(
    r"\b("
    r"lecco|trento|trentino|bari|roma|rome|torino|napoli|genova|venezia|bologna|"
    r"firenze|bergamo|brescia|udine|padova|verona|palermo|catania|parma|pisa|"
    r"barcelona|madrid|paris|berlin|london|new\s+york|san\s+francisco|los\s+angeles"
    r")\b",
    re.I,
)
_KNOWN_FALSE_POSITIVE_URL_RE = re.compile(
    r"(eventbrite\.it/e/biglietti-hack-the-agriculture-hackathon-1984749196274|"
    r"polihub\.it/news-it/assosoftware-organizza-il-primo-hackathon-su-scala-nazionale)",
    re.I,
)
_KNOWN_UNDATED_STALE_WEB_RESULT_RE = re.compile(
    r"hackingthecity\.today/?$",
    re.I,
)
_PAST_TENSE_HINT_RE = re.compile(
    r"(\b(?:e'|è)\s+stato\b|\bsi\s+e'\s+svolt[oa]\b|\bsi\s+è\s+svolt[oa]\b|"
    r"\bsi\s+e'\s+tenut[oa]\b|\bsi\s+è\s+tenut[oa]\b|\bwas\s+held\b|"
    r"\btook\s+place\b|\bhas\s+ended\b|\bended\b)",
    re.I,
)


def _text_has_milan(text: str) -> bool:
    return bool(_MILAN_RE.search(text or ""))


def _extract_years(*parts: str) -> list[int]:
    years: list[int] = []
    for p in parts:
        if not p:
            continue
        years.extend(int(y) for y in _YEAR_RE.findall(p))
    return years


def _is_clearly_past(event: HackathonEvent) -> bool:
    """Regola deterministica anti-falsi positivi su eventi vecchi."""
    current_year = datetime.now().year
    years = _extract_years(event.title, event.description, event.date_str, event.url)
    if not years:
        return False
    return all(y < current_year for y in years)


def _is_clearly_non_milan(event: HackathonEvent) -> bool:
    """Regola deterministica anti-falsi positivi fuori Milano."""
    full_text = f"{event.title} {event.description} {event.url}"
    location = event.location or ""

    # Se troviamo Milano esplicitamente, non scartiamo.
    if _text_has_milan(full_text) or _text_has_milan(location):
        return False

    # Se non c'è Milano ma compare una città non milanese, scarta.
    if _NON_MILAN_CITY_RE.search(location) or _NON_MILAN_CITY_RE.search(full_text):
        return True

    return False


def _is_undated_likely_stale_web_result(event: HackathonEvent) -> bool:
    """Scarta risultati web_search senza data che hanno forti segnali di evento passato."""
    if event.source != "web_search":
        return False
    if event.parsed_date() is not None:
        return False

    url = event.url or ""
    if _KNOWN_UNDATED_STALE_WEB_RESULT_RE.search(url):
        return True

    # Per home page senza data, usa solo un indizio lessicale forte (passato).
    path = ""
    try:
        path = urlparse(url).path or ""
    except Exception:
        path = ""

    if path not in ("", "/"):
        return False

    text = f"{event.title} {event.description}"
    return bool(_PAST_TENSE_HINT_RE.search(text))


def _passes_quality_gate(event: HackathonEvent) -> tuple[bool, str]:
    """Vincoli hard prima del salvataggio finale."""
    if _KNOWN_FALSE_POSITIVE_URL_RE.search(event.url or ""):
        return False, "false positive noto"
    if _is_clearly_past(event):
        return False, "evento chiaramente passato"
    if _is_undated_likely_stale_web_result(event):
        return False, "evento web senza data (probabile passato)"
    if _is_clearly_non_milan(event):
        return False, "evento chiaramente non a Milano"
    return True, "ok"


def _event_rank_for_dedup(event: HackathonEvent) -> int:
    """Punteggio per scegliere il record migliore quando due eventi coincidono."""
    score = 0
    url_l = (event.url or "").lower()
    if "lists." in url_l or "hyperkitty" in url_l:
        score -= 2
    if event.location and _text_has_milan(event.location):
        score += 1
    if len(event.description or "") >= 120:
        score += 1
    if event.source != "web_search":
        score += 1
    return score


def _deterministic_semantic_dedup(events: list[HackathonEvent]) -> list[HackathonEvent]:
    """Dedup di fallback (deterministico) per stessa data + keyword forti condivise."""
    deduped: list[HackathonEvent] = []

    for event in events:
        event_date = (event.parsed_date().isoformat() if event.parsed_date() else "")
        event_kw = EventStore._extract_distinctive_keywords(f"{event.title} {event.description}")

        duplicate_idx: int | None = None
        for i, kept in enumerate(deduped):
            kept_date = kept.parsed_date().isoformat() if kept.parsed_date() else ""
            if not event_date or event_date != kept_date:
                continue

            kept_kw = EventStore._extract_distinctive_keywords(f"{kept.title} {kept.description}")
            overlap = event_kw & kept_kw
            strong_overlap = any(len(k) >= 8 for k in overlap)
            if len(overlap) >= 2 or (len(overlap) == 1 and strong_overlap):
                duplicate_idx = i
                break

        if duplicate_idx is None:
            deduped.append(event)
            continue

        kept = deduped[duplicate_idx]
        if _event_rank_for_dedup(event) > _event_rank_for_dedup(kept):
            logger.info("Dedup fallback: sostituito '%s' con '%s'", kept.title[:60], event.title[:60])
            deduped[duplicate_idx] = event
        else:
            logger.info("Dedup fallback: scartato duplicato '%s'", event.title[:60])

    return deduped


def _deterministic_semantic_dedup_dicts(events: list[dict]) -> list[dict]:
    """Versione dict-preserving della dedup semantica per cleanup dello storico."""
    deduped: list[dict] = []

    def _as_event(item: dict) -> HackathonEvent:
        return HackathonEvent(
            title=item.get("title", ""),
            url=item.get("url", ""),
            source=item.get("source", ""),
            description=item.get("description", ""),
            date_str=item.get("date_str", ""),
            location=item.get("location", ""),
            organizer=item.get("organizer", ""),
        )

    for item in events:
        event = _as_event(item)
        event_date = event.parsed_date().isoformat() if event.parsed_date() else ""
        event_kw = EventStore._extract_distinctive_keywords(f"{event.title} {event.description}")

        duplicate_idx: int | None = None
        for i, kept_item in enumerate(deduped):
            kept = _as_event(kept_item)
            kept_date = kept.parsed_date().isoformat() if kept.parsed_date() else ""
            if not event_date or event_date != kept_date:
                continue

            kept_kw = EventStore._extract_distinctive_keywords(f"{kept.title} {kept.description}")
            overlap = event_kw & kept_kw
            strong_overlap = any(len(k) >= 8 for k in overlap)
            if len(overlap) >= 2 or (len(overlap) == 1 and strong_overlap):
                duplicate_idx = i
                break

        if duplicate_idx is None:
            deduped.append(item)
            continue

        kept_item = deduped[duplicate_idx]
        kept = _as_event(kept_item)
        if _event_rank_for_dedup(event) > _event_rank_for_dedup(kept):
            logger.info("Dedup fallback: sostituito '%s' con '%s'", kept.title[:60], event.title[:60])
            deduped[duplicate_idx] = item
        else:
            logger.info("Dedup fallback: scartato duplicato '%s'", event.title[:60])

    return deduped


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
        # ── Tier 4: Community platforms ──
        GDGCollector(),
        # ── Tier 5: Focus sources ──
        TelespazioCollector(),
    ]


# ─── Pipeline ──────────────────────────────────────────────────────────────

def run_collectors(
    collectors: list[BaseCollector],
) -> tuple[list[HackathonEvent], list[str], list[str], list[dict]]:
    """Esegue tutti i collector in parallelo.

    Returns:
        (all_events, ok_collectors, failed_collectors, collector_runs)
    """
    all_events: list[HackathonEvent] = []
    ok_collectors: list[str] = []
    failed_collectors: list[str] = []
    collector_runs: list[dict] = []

    with ThreadPoolExecutor(max_workers=config.MAX_COLLECTOR_WORKERS) as executor:
        future_to_collector = {
            executor.submit(_safe_collect, c): c for c in collectors
        }

        for future in as_completed(future_to_collector):
            collector = future_to_collector[future]
            try:
                events, error, duration = future.result()
                if error:
                    failed_collectors.append(f"{collector.name}: {error}")
                    collector_runs.append(CollectorRun(
                        name=collector.name,
                        ok=False,
                        event_count=0,
                        duration_seconds=duration,
                        error=error,
                    ).to_dict())
                    logger.error("Collector %s fallito: %s", collector.name, error)
                else:
                    ok_collectors.append(collector.name)
                    all_events.extend(events)
                    collector_runs.append(CollectorRun(
                        name=collector.name,
                        ok=True,
                        event_count=len(events),
                        duration_seconds=duration,
                    ).to_dict())
                    logger.info(
                        "Collector %s: %d eventi", collector.name, len(events)
                    )
            except Exception as e:
                failed_collectors.append(f"{collector.name}: {e}")
                collector_runs.append(CollectorRun(
                    name=collector.name,
                    ok=False,
                    event_count=0,
                    duration_seconds=0.0,
                    error=str(e),
                ).to_dict())
                logger.error("Collector %s eccezione: %s", collector.name, e)

    collector_runs.sort(key=lambda item: item["name"])
    return all_events, ok_collectors, failed_collectors, collector_runs


def _safe_collect(
    collector: BaseCollector,
) -> tuple[list[HackathonEvent], str | None, float]:
    """Wrapper per esecuzione sicura di un collector."""
    started = perf_counter()
    try:
        events = collector.collect() or []
        return events, None, perf_counter() - started
    except Exception as e:
        return [], str(e), perf_counter() - started


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


def _all_llm_results_failed(events: list[HackathonEvent]) -> bool:
    """True se il LLM sembra fallito tecnicamente per tutti i candidati."""
    return bool(events) and all(getattr(e, "confidence", 1.0) == 0.0 for e in events)


def _failed_collector_names(failed_collectors: list[str]) -> list[str]:
    """Estrae solo il nome collector da stringhe 'nome: errore'."""
    return [f.split(":", 1)[0] for f in failed_collectors]


def _write_report(report: dict) -> Path:
    """Scrive il report dell'ultima run e ritorna il path."""
    report_path = Path(config.DATA_DIR) / "last_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Report salvato in %s", report_path)
    return report_path


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


def deduplicate_post_llm_against_store(
    events: list[HackathonEvent], store: EventStore
) -> list[HackathonEvent]:
    """Seconda passata di dedup vs storico dopo arricchimento LLM (date/titoli migliori)."""
    unique: list[HackathonEvent] = []
    for event in events:
        if store.is_duplicate(event):
            logger.info(
                "Post-LLM dedup vs store: scartato duplicato '%s'",
                event.title[:70],
            )
            continue
        unique.append(event)
    return unique


def run_pipeline(dry_run: bool = False) -> None:
    """Pipeline completa di raccolta, filtro e notifica."""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("Hackathon Monitor — run iniziata: %s", start_time.isoformat())
    logger.info("=" * 60)

    # 1. Carica storico
    store = EventStore()
    # Cleanup deterministico dello storico per rimuovere duplicati/falsi positivi legacy
    existing_events: list[dict] = []
    for item in store.all_events():
        ev = HackathonEvent(
            title=item.get("title", ""),
            url=item.get("url", ""),
            source=item.get("source", ""),
            description=item.get("description", ""),
            date_str=item.get("date_str", ""),
            location=item.get("location", ""),
            organizer=item.get("organizer", ""),
        )
        ok, reason = _passes_quality_gate(ev)
        if ok:
            existing_events.append(item)
        else:
            logger.info("Cleanup storico: rimosso '%s' (%s)", ev.title[:70], reason)
    existing_events = _deterministic_semantic_dedup_dicts(existing_events)
    store.replace_events(existing_events)
    logger.info("Storico caricato: %d eventi", store.count)

    # 2. Esegui collector
    collectors = get_collectors()
    all_events, ok_collectors, failed_collectors, collector_runs = run_collectors(
        collectors
    )
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
    review_decisions = load_review_decisions()
    review_queue = build_review_queue(keyword_passed, llm_confirmed, review_decisions)
    logger.info(
        "Post LLM filter: %d confermati, %d scartati",
        post_llm_count, llm_discarded,
    )
    logger.info("Review queue: %d candidati dubbi", len(review_queue))

    # ── Protezione anti-sovrascrittura ──
    # Se c'erano candidati keyword ma l'LLM li ha scartati TUTTI con
    # confidence=0.0, è quasi certamente un errore API/parsing invece di
    # una classificazione legittima. Preserva quindi lo storico su disco.
    if post_keyword_count > 0 and post_llm_count == 0:
        if _all_llm_results_failed(keyword_passed):
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
            _write_report({
                "date": start_time.strftime("%Y-%m-%d %H:%M"),
                "status": "llm_failed_preserved",
                "collectors_ok": len(ok_collectors),
                "collectors_total": len(collectors),
                "failed_collectors": _failed_collector_names(failed_collectors),
                "collector_runs": collector_runs,
                "raw_events": raw_count,
                "post_dedup": post_dedup_count,
                "post_keyword": post_keyword_count,
                "post_llm": post_llm_count,
                "new_events": 0,
                "total_stored": store.count,
                "review_queue": 0,
            })
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
                    failed_collectors=_failed_collector_names(failed_collectors),
                    page_url=page_url,
                )
            logger.info("=" * 60)
            logger.info("Run completata in %.1f secondi (storico preservato)", elapsed)
            logger.info("=" * 60)
            return

    save_review_queue(review_queue)

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

    # 5d. Quality gate deterministico (non-Milano / chiaramente passato)
    quality_passed: list[HackathonEvent] = []
    for event in llm_confirmed:
        ok, reason = _passes_quality_gate(event)
        if ok:
            quality_passed.append(event)
        else:
            logger.info("Quality gate: scartato '%s' (%s)", event.title[:70], reason)
    llm_confirmed = quality_passed

    # 5e. Dedup fallback deterministico (anche se llm_dedup fallisce parsing)
    pre_fallback_dedup = len(llm_confirmed)
    llm_confirmed = _deterministic_semantic_dedup(llm_confirmed)
    if len(llm_confirmed) < pre_fallback_dedup:
        logger.info(
            "Post fallback dedup: %d -> %d unici",
            pre_fallback_dedup,
            len(llm_confirmed),
        )

    # 5f. Dedup finale contro storico usando date/titoli arricchiti dal LLM
    pre_store_dedup = len(llm_confirmed)
    llm_confirmed = deduplicate_post_llm_against_store(llm_confirmed, store)
    if len(llm_confirmed) < pre_store_dedup:
        logger.info(
            "Post-LLM dedup vs store: %d -> %d unici",
            pre_store_dedup,
            len(llm_confirmed),
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
        "status": "completed",
        "collectors_ok": len(ok_collectors),
        "collectors_total": len(collectors),
        "failed_collectors": _failed_collector_names(failed_collectors),
        "collector_runs": collector_runs,
        "raw_events": raw_count,
        "post_dedup": post_dedup_count,
        "post_keyword": post_keyword_count,
        "post_llm": post_llm_count,
        "new_events": notified_count,
        "total_stored": store.count,
        "review_queue": len(review_queue),
    }
    _write_report(report)

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
            failed_collectors=_failed_collector_names(failed_collectors),
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
