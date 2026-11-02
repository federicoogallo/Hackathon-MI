"""Invariants of the data a scan publishes, checked before any file is replaced.

A violation stops the scan: the previous events.json and review_queue.json stay
as they were. Field types follow `HackathonEvent.to_dict`; the date rules are the
ones the pipeline already applies (archive cleanup, review expiry, gate 5d).
Messages name records by position and short id, never by title: they end up in
the public run report and annotations.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Iterable
from urllib.parse import urlsplit

from models import HackathonEvent
from utils.event_dates import event_temporal_status

# Hard ceiling; main.ALIAS_WARNING_LIMIT (10) only warns. Every alias is an
# identity key, so a record far above it has absorbed unrelated pages.
ALIAS_LIMIT = 25
REVIEW_STATUSES = frozenset({
    "ai_pending", "ai_verified", "manual_approved", "manual_rejected",
    "needs_review", "llm_error", "rejected",
})
_REQUIRED = {
    "id": str, "title": str, "url": str, "source": str, "description": str,
    "date_str": str, "location": str, "organizer": str, "is_hackathon": bool,
    "confidence": float, "review_status": str, "alternate_urls": list, "discovered_at": str,
}
_OPTIONAL = {
    "review_reason": str, "reviewed_at": str, "published_at": str, "date_source": str,
    "classification_status": str, "provenance": dict,
}
_ID = re.compile(r"[0-9a-f]{64}")
MAX_REPORTED = 20


class DataContractError(RuntimeError):
    def __init__(self, violations: list[str]):
        self.violations = violations
        shown = "; ".join(violations[:5])
        more = f" (+{len(violations) - 5})" if len(violations) > 5 else ""
        super().__init__(f"{len(violations)} violazioni dei contratti sui dati: {shown}{more}")


def _http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _type_ok(value: Any, kind: type) -> bool:
    if kind is float:
        return type(value) in (int, float) and math.isfinite(value)
    if kind is bool:
        return type(value) is bool
    return isinstance(value, kind)


def _label(item: dict, index: int) -> str:
    identifier = item.get("id")
    return f"#{index} {identifier[:12]}" if isinstance(identifier, str) and _ID.fullmatch(identifier) else f"#{index}"


def _event(item: dict) -> HackathonEvent:
    return HackathonEvent(
        title=item.get("title", ""), url=item.get("url", ""), source=item.get("source", ""),
        description=item.get("description", ""), date_str=item.get("date_str", ""),
        date_source=item.get("date_source", ""), location=item.get("location", ""),
        alternate_urls=list(item.get("alternate_urls") or []),
    )


def record_problems(item: Any, label: str) -> list[str]:
    """Field presence, types and formats of one stored event record."""
    if not isinstance(item, dict):
        return [f"{label}: il record non è un oggetto"]
    problems = []
    for key, kind in _REQUIRED.items():
        if key not in item:
            problems.append(f"{label}: manca il campo {key}")
        elif not _type_ok(item[key], kind):
            problems.append(f"{label}: {key} ha tipo {type(item[key]).__name__}")
    for key, kind in _OPTIONAL.items():
        if key in item and item[key] is not None and not _type_ok(item[key], kind):
            problems.append(f"{label}: {key} ha tipo {type(item[key]).__name__}")
    if problems:
        return problems

    if not item["title"].strip():
        problems.append(f"{label}: titolo vuoto")
    if not _http_url(item["url"]):
        problems.append(f"{label}: URL non http(s)")
    elif not _ID.fullmatch(item["id"]) or item["id"] != HackathonEvent(title="", url=item["url"], source="").id:
        problems.append(f"{label}: id diverso dall'hash dell'URL")
    if not 0 <= item["confidence"] <= 1:
        problems.append(f"{label}: confidence fuori da 0–1")
    if item["review_status"] not in REVIEW_STATUSES:
        problems.append(f"{label}: review_status sconosciuto '{item['review_status'][:30]}'")
    aliases = item["alternate_urls"]
    if not all(_http_url(url) for url in aliases):
        problems.append(f"{label}: URL alternativo non http(s)")
    if len(aliases) > ALIAS_LIMIT:
        problems.append(f"{label}: {len(aliases)} URL alternativi (limite {ALIAS_LIMIT})")
    return problems


def _unique_ids(items: list, what: str) -> list[str]:
    seen, problems = set(), []
    for item in items:
        identifier = item.get("id") if isinstance(item, dict) else None
        if identifier in seen:
            problems.append(f"{what}: id duplicato {str(identifier)[:12]}")
        seen.add(identifier)
    return problems


def check_archive(payload: Any, today: date, *,
                  reviewed_end_dates: dict[str, date] | None = None) -> list[str]:
    """events.json: structure, unique identities, aliases and no expired publications."""
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return ["events.json: serve un oggetto con la lista events"]
    if payload.get("last_check") is not None and not isinstance(payload["last_check"], str):
        return ["events.json: last_check non è una stringa"]
    events = payload["events"]
    problems = [problem for index, item in enumerate(events)
                for problem in record_problems(item, f"evento {_label(item, index) if isinstance(item, dict) else index}")]
    if problems:
        return problems
    problems += _unique_ids(events, "events.json")

    primaries = {item["url"]: item["id"] for item in events}
    reviewed_end_dates = reviewed_end_dates or {}
    for index, item in enumerate(events):
        label = f"evento {_label(item, index)}"
        foreign = [url for url in item["alternate_urls"] if primaries.get(url, item["id"]) != item["id"]]
        if foreign:
            problems.append(f"{label}: un URL alternativo è l'URL di un altro evento")
        if not item["is_hackathon"]:
            continue
        end = reviewed_end_dates.get(item["id"])
        expired = end < today if end is not None else event_temporal_status(_event(item), today) == "past"
        if expired:
            problems.append(f"{label}: evento passato ancora pubblicato")
    return problems


def check_review_queue(candidates: Any, today: date, *, published_ids: Iterable[str] = (),
                       decisions: dict[str, dict] | None = None) -> list[str]:
    """review_queue.json candidates: records, unique, unresolved and still current."""
    if not isinstance(candidates, list):
        return ["review_queue.json: candidates non è una lista"]
    problems = []
    for index, item in enumerate(candidates):
        label = f"candidato {_label(item, index) if isinstance(item, dict) else index}"
        found = record_problems(item, label)
        if not found:
            if item.get("review_status") != "needs_review":
                found.append(f"{label}: review_status non è needs_review")
            if not isinstance(item.get("queued_at"), str) or not item["queued_at"]:
                found.append(f"{label}: manca queued_at")
        problems += found
    if problems:
        return problems
    problems += _unique_ids(candidates, "review_queue.json")

    published, decisions = set(published_ids), decisions or {}
    for index, item in enumerate(candidates):
        label = f"candidato {_label(item, index)}"
        if item["id"] in published:
            problems.append(f"{label}: è già pubblicato")
        if decisions.get(item["id"], {}).get("decision") in {"approved", "rejected"}:
            problems.append(f"{label}: ha già una decisione")
        if event_temporal_status(_event(item), today) == "past":
            problems.append(f"{label}: evento passato ancora in coda")
    return problems


def check_queue_file(payload: Any) -> list[str]:
    """Envelope of review_queue.json as written by save_review_queue."""
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        return ["review_queue.json: serve un oggetto con la lista candidates"]
    if payload.get("count") != len(payload["candidates"]):
        return ["review_queue.json: count diverso dal numero di candidati"]
    return []


def check_publications(events: list[HackathonEvent], today: date) -> list[str]:
    """Automatic publications of this scan carry a date the code reads as future."""
    return [
        f"pubblicazione {event.id[:12]}: data evento non verificata come futura"
        for event in events if event_temporal_status(event, today) != "future"
    ]
