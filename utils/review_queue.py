"""
Utility per mantenere una coda di revisione manuale dei candidati dubbi.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import config
from models import HackathonEvent


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
    item["queued_at"] = datetime.now().isoformat()
    item["review_note"] = (
        "AI uncertain: approve to publish, reject to suppress future repeats."
    )
    return item


def build_review_queue(
    candidates: list[HackathonEvent],
    confirmed: list[HackathonEvent],
    decisions: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Costruisce la coda da candidati passati al LLM ma non pubblicati."""
    decisions = decisions or {}
    confirmed_ids = {event.id for event in confirmed}
    queue: list[dict[str, Any]] = []
    seen: set[str] = set()

    for event in candidates:
        if event.id in seen or event.id in confirmed_ids:
            continue
        seen.add(event.id)

        decision = decisions.get(event.id, {}).get("decision")
        if decision in {"approved", "rejected"}:
            continue
        if not _needs_manual_review(event):
            continue
        queue.append(_candidate_dict(event))

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
