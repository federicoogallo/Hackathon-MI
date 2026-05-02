#!/usr/bin/env python3
"""Review candidates from data/review_queue.json.

Usage:
    python scripts/review_candidate.py list
    python scripts/review_candidate.py approve <candidate-id>
    python scripts/review_candidate.py reject <candidate-id>
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from models import HackathonEvent
from storage.json_store import EventStore
from utils.html_export import generate_html
from utils.readme_export import generate_readme_table
from utils.review_queue import (
    load_review_decisions,
    load_review_queue,
    save_review_decisions,
    save_review_queue,
)


def _resolve_candidate(candidate_id: str, queue: list[dict]) -> dict:
    matches = [item for item in queue if str(item.get("id", "")).startswith(candidate_id)]
    if not matches:
        raise SystemExit(f"No review candidate matches id prefix: {candidate_id}")
    if len(matches) > 1:
        raise SystemExit(f"Ambiguous id prefix: {candidate_id}")
    return matches[0]


def _event_from_candidate(candidate: dict) -> HackathonEvent:
    return HackathonEvent(
        title=candidate.get("title", ""),
        url=candidate.get("url", ""),
        source=candidate.get("source", ""),
        description=candidate.get("description", ""),
        date_str=candidate.get("date_str", ""),
        location=candidate.get("location", ""),
        organizer=candidate.get("organizer", ""),
        is_hackathon=True,
        confidence=float(candidate.get("confidence") or 0.0),
        review_status="manual_approved",
        review_reason=candidate.get("review_reason", "Manual review approved"),
        reviewed_at=datetime.now().isoformat(),
        alternate_urls=candidate.get("alternate_urls", []),
        discovered_at=candidate.get("discovered_at") or datetime.now().isoformat(),
    )


def _save_decision(candidate: dict, decision: str) -> None:
    decisions = load_review_decisions()
    decisions[candidate["id"]] = {
        "decision": decision,
        "title": candidate.get("title", ""),
        "url": candidate.get("url", ""),
        "reviewed_at": datetime.now().isoformat(),
    }
    save_review_decisions(decisions)


def _remove_from_queue(candidate: dict, queue: list[dict]) -> None:
    remaining = [item for item in queue if item.get("id") != candidate.get("id")]
    save_review_queue(remaining)


def _rebuild_site() -> None:
    generate_html()
    generate_readme_table()


def list_candidates() -> int:
    queue = load_review_queue()
    if not queue:
        print("No candidates waiting for manual review.")
        return 0

    for item in queue:
        candidate_id = item.get("id", "")[:12]
        confidence = float(item.get("confidence") or 0.0)
        title = item.get("title", "Untitled")
        source = item.get("source", "")
        reason = item.get("review_reason", "")
        print(f"{candidate_id}  {confidence:.2f}  {source}  {title}")
        if reason:
            print(f"  reason: {reason}")
    return 0


def approve_candidate(candidate_id: str) -> int:
    queue = load_review_queue()
    candidate = _resolve_candidate(candidate_id, queue)
    event = _event_from_candidate(candidate)

    store = EventStore()
    if not store.is_duplicate(event):
        store.add_event(event)
        store.save_with_timestamp(datetime.now().isoformat())

    _save_decision(candidate, "approved")
    _remove_from_queue(candidate, queue)
    _rebuild_site()
    print(f"Approved: {event.title}")
    return 0


def reject_candidate(candidate_id: str) -> int:
    queue = load_review_queue()
    candidate = _resolve_candidate(candidate_id, queue)
    _save_decision(candidate, "rejected")
    _remove_from_queue(candidate, queue)
    print(f"Rejected: {candidate.get('title', 'Untitled')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Review hackathon candidates")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")

    approve = sub.add_parser("approve")
    approve.add_argument("candidate_id")

    reject = sub.add_parser("reject")
    reject.add_argument("candidate_id")

    args = parser.parse_args()
    if args.command == "list":
        return list_candidates()
    if args.command == "approve":
        return approve_candidate(args.candidate_id)
    if args.command == "reject":
        return reject_candidate(args.candidate_id)
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
