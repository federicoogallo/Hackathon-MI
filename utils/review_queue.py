"""
Utility per mantenere una coda di revisione manuale dei candidati dubbi.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config
from models import HackathonEvent
from utils.event_dates import event_temporal_status
from utils.event_identity import editions_compatible, merge_event_evidence


REVIEW_MIN_CONFIDENCE = 0.45
REVIEW_REJECT_CONFIDENCE_CUTOFF = 0.85

# Milan, a Milan venue or a Milan institution named by the candidate itself.
# This signal is enough for manual review; publication uses stricter checks.
_MILAN_SIGNAL = re.compile(
    r"\b(?:milan(?:o|ese|esi)?|politecnico|polimi|polihub|bocconi|unibocconi|bicocca|unimib|unimi|"
    r"iulm|unicatt|human\s+technopole|mind\s+milano|triulza|cariplo\s+factory|talent\s+garden|"
    r"fiera\s+milano|sesto\s+san\s+giovanni|rho|segrate|cinisello\s+balsamo)\b",
    re.I,
)
# A bare city is the event's own city when a collector reads it from the event
# (Eventbrite, Luma, Meetup venues, university and hub calendars). Search results
# may echo the query instead: archived web_search records carry "Milano" whatever
# the event's city.
_BARE_MILAN_LOCATIONS = frozenset({
    "milano", "milan", "milano, italia", "milan, italy", "milano, italy", "milan, italia",
})
_QUERY_ECHO_SOURCES = frozenset({"web_search", "reddit"})
_LOCATION_EVIDENCE_FIELDS = ("title", "description", "url", "organizer", "location", "source")


def _milan_evidence(event: HackathonEvent | dict[str, Any]) -> dict[str, str] | None:
    """Keep the source text behind a review signal, including an earlier discovery."""
    get = event.get if isinstance(event, dict) else lambda key, default="": getattr(event, key, default)
    current = {key: str(get(key, "") or "") for key in _LOCATION_EVIDENCE_FIELDS}
    for record in (current, get("review_location_evidence", None)):
        if not isinstance(record, dict):
            continue
        evidence = {key: str(record.get(key, "") or "") for key in _LOCATION_EVIDENCE_FIELDS}
        location = evidence["location"].strip()
        if location.lower() in _BARE_MILAN_LOCATIONS and evidence["source"] in _QUERY_ECHO_SOURCES:
            location = ""
        text = " ".join(evidence[key] for key in ("title", "description", "url", "organizer"))
        if _MILAN_SIGNAL.search(f"{text} {location}".replace("-", " ").replace("_", " ")):
            return evidence
    return None


def has_milan_signal(event: HackathonEvent | dict[str, Any]) -> bool:
    """True when source evidence names Milan or the surrounding metropolitan area."""
    return _milan_evidence(event) is not None


def load_review_decisions(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Carica decisioni manuali persistenti, indicizzate per event id."""
    path = path or config.REVIEW_DECISIONS_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    decisions = data.get("decisions", {})
    return decisions if isinstance(decisions, dict) else {}


def save_review_decisions(decisions: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    """Salva decisioni manuali persistenti."""
    path = path or config.REVIEW_DECISIONS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(),
        "decisions": decisions,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _needs_manual_review(event: HackathonEvent, milan_signal: bool | None = None) -> bool:
    """Decide se un candidato LLM merita revisione umana.

    `milan_signal` lets the caller include evidence already queued for the event.
    """
    if event.classification_status == "error":
        return True  # never judged: a person must see it
    if not (has_milan_signal(event) if milan_signal is None else milan_signal):
        return False
    if event.classification_status == "insufficient_evidence":
        return True
    if event.confidence <= 0.0:
        return False
    if event.is_hackathon and event.confidence < config.LLM_CONFIDENCE_THRESHOLD:
        return True
    if not event.is_hackathon and REVIEW_MIN_CONFIDENCE <= event.confidence < REVIEW_REJECT_CONFIDENCE_CUTOFF:
        return True
    return False


def _candidate_dict(event: HackathonEvent) -> dict[str, Any]:
    item = event.to_dict()
    item["review_status"] = "needs_review"
    item["queued_at"] = datetime.now(timezone.utc).isoformat()
    item["last_seen_at"] = item["queued_at"]
    item["review_note"] = (
        "Evidence needs review: verify date, venue and event format before approval."
    )
    return item


def build_review_queue(
    candidates: list[HackathonEvent],
    confirmed: list[HackathonEvent],
    decisions: dict[str, dict[str, Any]] | None = None,
    *,
    previous: list[dict[str, Any]] | None = None,
    ref_date: date | None = None,
    published_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Keep unresolved candidates until decision, event expiry or 60 days without a date."""
    decisions = decisions or {}
    today = ref_date or datetime.now(timezone.utc).date()
    confirmed_ids = {event.id for event in confirmed} | (published_ids or set())
    queue_by_id = {item["id"]: dict(item) for item in (previous or []) if item.get("id")}

    for event in candidates:
        item = _candidate_dict(event)
        prior = queue_by_id.get(event.id)
        same_edition = prior is not None and editions_compatible(prior, item)
        # A rediscovery may carry less text than the queued record: judge both.
        evidence = _milan_evidence(event) or (_milan_evidence(prior) if same_edition else None)
        milan = evidence is not None
        if not _needs_manual_review(event, milan):
            if event.classification_status in {"confirmed", "rejected"} or not milan:
                queue_by_id.pop(event.id, None)
            continue
        if prior is not None:
            if same_edition:
                merged = merge_event_evidence(prior, item)
                for key in ("confidence", "is_hackathon", "review_status", "review_reason",
                            "classification_status", "review_note", "last_seen_at"):
                    merged[key] = item[key]
                merged["queued_at"] = prior.get("queued_at", item["queued_at"])
                item = merged
        # A more precise date can win the merge while its shorter description
        # loses the location. Retain the source evidence for subsequent scans.
        if evidence is not None and not has_milan_signal(item):
            item["review_location_evidence"] = evidence
        queue_by_id[event.id] = item

    queue: list[dict[str, Any]] = []
    for event_id, item in queue_by_id.items():
        if event_id in confirmed_ids or decisions.get(event_id, {}).get("decision") in {"approved", "rejected"}:
            continue
        # Earlier scans queued candidates without any Milan reference.
        if item.get("classification_status") != "error" and not has_milan_signal(item):
            continue
        event = HackathonEvent(
            title=item.get("title", ""), url=item.get("url", ""), source=item.get("source", ""),
            description=item.get("description", ""),
            date_str=item.get("date_str", ""), date_source=item.get("date_source", ""),
        )
        # Same rule as publication: a range stays current through its last day.
        if event_temporal_status(event, today) == "past":
            continue
        if event.parsed_date() is None:
            try:
                queued = datetime.fromisoformat(item.get("queued_at", "")).date()
            except (TypeError, ValueError):
                queued = today
                item["queued_at"] = today.isoformat()
            if queued < today - timedelta(days=60):
                continue
        queue.append(item)

    queue.sort(key=lambda item: (-float(item.get("confidence", 0.0)), item.get("title", "")))
    return queue


def save_review_queue(queue: list[dict[str, Any]], path: Path | None = None) -> Path:
    """Scrive `data/review_queue.json`."""
    path = path or config.REVIEW_QUEUE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(),
        "count": len(queue),
        "candidates": queue,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_review_queue(path: Path | None = None) -> list[dict[str, Any]]:
    """Carica la lista candidati in coda."""
    path = path or config.REVIEW_QUEUE_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    candidates = data.get("candidates", [])
    return candidates if isinstance(candidates, list) else []
