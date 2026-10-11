"""
Utility per mantenere una coda di revisione manuale dei candidati dubbi.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config
from models import HackathonEvent
from utils.event_identity import editions_compatible, merge_event_evidence


REVIEW_MIN_CONFIDENCE = 0.45
REVIEW_REJECT_CONFIDENCE_CUTOFF = 0.85


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


def _needs_manual_review(event: HackathonEvent) -> bool:
    """Decide se un candidato LLM merita revisione umana."""
    if event.classification_status in {"insufficient_evidence", "error"}:
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
        if not _needs_manual_review(event):
            if event.classification_status in {"confirmed", "rejected"}:
                queue_by_id.pop(event.id, None)
            continue
        item = _candidate_dict(event)
        if event.id in queue_by_id:
            prior = queue_by_id[event.id]
            if editions_compatible(prior, item):
                merged = merge_event_evidence(prior, item)
                for key in ("confidence", "is_hackathon", "review_status", "review_reason",
                            "classification_status", "review_note", "last_seen_at"):
                    merged[key] = item[key]
                merged["queued_at"] = prior.get("queued_at", item["queued_at"])
                item = merged
        queue_by_id[event.id] = item

    queue: list[dict[str, Any]] = []
    for event_id, item in queue_by_id.items():
        if event_id in confirmed_ids or decisions.get(event_id, {}).get("decision") in {"approved", "rejected"}:
            continue
        event = HackathonEvent(
            title=item.get("title", ""), url=item.get("url", ""), source=item.get("source", ""),
            date_str=item.get("date_str", ""), date_source=item.get("date_source", ""),
        )
        if event.is_past(today):
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
