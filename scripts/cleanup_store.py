#!/usr/bin/env python3
"""Cleanup deterministico dello store: quality gate + dedup fallback."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import (
    _deterministic_semantic_dedup_dicts, _event_from_dict, _now,
    _passes_quality_gate, _reviewed_event_end_dates,
)
from storage.json_store import EventStore
from utils.html_export import generate_html
from utils.readme_export import generate_readme_table


def run() -> None:
    store = EventStore()
    kept: list[dict] = []
    removed: list[tuple[str, str]] = []
    today = _now().date()
    reviewed_end_dates = _reviewed_event_end_dates()

    for item in store.all_events():
        ev = _event_from_dict(item)
        ok, reason = _passes_quality_gate(
            ev, today, reviewed_end_date=reviewed_end_dates.get(item.get("id")),
        )
        if item.get("review_status") in {"rejected", "manual_rejected"}:
            ok, reason = False, "evento rifiutato in revisione"
        if ok:
            kept.append(item)
        else:
            removed.append((ev.title, reason))

    before = len(kept)
    kept = _deterministic_semantic_dedup_dicts(kept)
    dedup_removed = before - len(kept)

    store.replace_events(kept)
    store.save_with_timestamp(_now().isoformat())

    generate_html()
    generate_readme_table()

    print(f"removed_by_quality={len(removed)}")
    for title, reason in removed:
        print(f"- {title[:90]} | {reason}")
    print(f"dedup_removed={dedup_removed}")
    print(f"final_store_count={store.count}")


if __name__ == "__main__":
    run()
