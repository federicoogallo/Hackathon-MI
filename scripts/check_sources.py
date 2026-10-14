#!/usr/bin/env python3
"""Probe collectors without classification, archive writes or notifications."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import get_collectors, run_collectors


def probe(source_names: list[str] | None = None) -> dict:
    collectors = get_collectors()
    if source_names:
        unknown = set(source_names) - {collector.name for collector in collectors}
        if unknown:
            raise ValueError(f"Unknown sources: {', '.join(sorted(unknown))}")
        collectors = [collector for collector in collectors if collector.name in source_names]
    events, _, _, runs = run_collectors(collectors)
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": "collectors_only",
        "collectors_total": len(collectors),
        "collector_status_counts": dict(Counter(run["status"] for run in runs)),
        "raw_events": len(events),
        "collector_runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*", help="Collector names; omit to check all")
    parser.add_argument("--save", action="store_true", help="Save aggregate diagnostics in ignored .local/audit/")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s", force=True)
    try:
        report = probe(args.sources)
    except ValueError as error:
        parser.error(str(error))
    for run in report["collector_runs"]:
        print(f"{run['name']:22s} {run['status']:9s} {run['event_count']:4d} records  {run['duration_seconds']:.1f}s")
    print(json.dumps(report["collector_status_counts"], sort_keys=True))
    if args.save:
        directory = Path(__file__).resolve().parents[1] / ".local" / "audit"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"sources-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(report, output, indent=2, ensure_ascii=False)
        print(f"Report: {path}")
    # Disabled integrations are reported but do not make an explicit subset probe fail.
    return int(any(run["status"] in {"degraded", "blocked", "failed"} for run in report["collector_runs"]))


if __name__ == "__main__":
    raise SystemExit(main())
