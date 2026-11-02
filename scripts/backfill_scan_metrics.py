#!/usr/bin/env python3
"""Rebuild data/metrics/scans.jsonl from the scans GitHub Actions still keeps.

    python scripts/backfill_scan_metrics.py fetch   # reports, logs and run data via `gh`
    python scripts/backfill_scan_metrics.py build   # merge them into the metrics file

`fetch` saves each run's uploaded report, its log and its commit under the ignored
`.local/ci-history/` (logs contain candidate titles: they stay private). GitHub keeps
both for about 90 days. `build` reads only the reports for per-source counts and
the logs for classifier trouble and duration; tokens and per-model calls were not
logged before, so backfilled lines leave them unknown. Existing lines win over
rebuilt ones with the same scan, and alerts are replayed in chronological order.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils import scan_metrics  # noqa: E402

DEFAULT_DIR = ROOT / ".local" / "ci-history"
REPORT_ARTIFACT = "hackathon-monitor-report"
# Primary model plus one fallback during the whole retained period.
MODELS_PER_CALL = 2
LOCAL_TZ = ZoneInfo("Europe/Rome")

_LOG_PATTERNS = {
    "classified": re.compile(r"LLM (?:CONFERMATO|SCARTATO): "),
    "errors": re.compile(r"LLM SCARTATO: .*conf=0\.00"),
    "rate_limit_retries": re.compile(r"Rate limit Groq \("),
    "fallback_lines": re.compile(r"Fallback LLM: provo modello successivo"),
    "failed_calls": re.compile(r"Tutti i modelli LLM hanno fallito"),
}
_DURATION = re.compile(r"Run completata in ([0-9.]+) secondi")


def _gh(*args: str) -> bytes:
    return subprocess.check_output(["gh", *args], cwd=ROOT)


def cmd_fetch(args) -> None:
    folder = Path(args.dir)
    for name in ("reports", "logs", "runs"):
        (folder / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    listing = _gh("api", "--paginate", "repos/{owner}/{repo}/actions/artifacts?per_page=100",
                  "-q", f'.artifacts[] | select(.name=="{REPORT_ARTIFACT}" and .expired==false) '
                        '| [.id, .workflow_run.id] | @tsv').decode()
    pairs = [line.split("\t") for line in listing.splitlines() if line.strip()]
    print(f"{len(pairs)} report disponibili")
    for artifact_id, run_id in pairs:
        report = folder / "reports" / f"{run_id}.json"
        if not report.exists():
            archive = zipfile.ZipFile(io.BytesIO(_gh(
                "api", f"repos/{{owner}}/{{repo}}/actions/artifacts/{artifact_id}/zip")))
            report.write_bytes(archive.read("last_report.json"))
        meta = folder / "runs" / f"{run_id}.json"
        if not meta.exists():
            meta.write_bytes(_gh("run", "view", run_id, "--json", "attempt,createdAt,headSha,conclusion"))
        log = folder / "logs" / f"{run_id}.log"
        if not log.exists():
            try:
                log.write_bytes(_gh("run", "view", run_id, "--log"))
            except subprocess.CalledProcessError:
                print(f"log non disponibile per la run {run_id}")
    print(f"Salvati in {folder}")


def classifier_from_log(text: str) -> tuple[dict, int, float | None]:
    """Classifier trouble and duration as far as the log of the time shows them."""
    found = {key: len(pattern.findall(text)) for key, pattern in _LOG_PATTERNS.items()}
    duration = _DURATION.findall(text)
    classifier = {
        "primary_model": None, "prompt_version": None, "models": None,
        # A call failing on every model logs one fallback line per model.
        "fallback_calls": max(0, found["fallback_lines"] - MODELS_PER_CALL * found["failed_calls"]),
        "failed_calls": found["failed_calls"],
        "rate_limit_retries": found["rate_limit_retries"],
        "errors": found["errors"],
    }
    return classifier, found["classified"], float(duration[-1]) if duration else None


def _attempted_at(report: dict, meta: dict) -> str:
    if report.get("attempted_at"):
        return report["attempted_at"]
    try:
        return datetime.strptime(report["date"], "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ).isoformat()
    except (KeyError, TypeError, ValueError):
        return meta.get("createdAt", "")


def backfilled_records(folder: Path) -> list[dict]:
    records = []
    for path in sorted((folder / "reports").glob("*.json")):
        run_id = path.stem
        report = json.loads(path.read_text(encoding="utf-8"))
        meta_path = folder / "runs" / f"{run_id}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        log_path = folder / "logs" / f"{run_id}.log"
        classifier, classified, duration = (
            classifier_from_log(log_path.read_text(encoding="utf-8", errors="replace"))
            if log_path.exists() else (None, None, None)
        )
        attempt = int(meta.get("attempt") or 1)
        report = {**report, "attempted_at": _attempted_at(report, meta),
                  "duration_seconds": report.get("duration_seconds", duration)}
        record = scan_metrics.scan_record(
            report, scan_id=f"gh-{run_id}" if attempt == 1 else f"gh-{run_id}-{attempt}",
            commit=meta.get("headSha", ""), classifier=classifier, origin="backfill",
        )
        if classified is not None and "classified" not in record["counts"]:
            record["counts"]["classified"] = classified
        records.append(record)
    return records


def cmd_build(args) -> None:
    output = Path(args.output) if args.output else scan_metrics.metrics_path()
    existing = scan_metrics.load_history(output, limit=10**9)
    known = {record.get("scan_id") for record in existing}
    merged = existing + [record for record in backfilled_records(Path(args.dir))
                         if record["scan_id"] not in known]
    merged.sort(key=lambda record: datetime.fromisoformat(record["attempted_at"]))

    replayed, active, notified = [], 0, 0
    for record in merged:
        alerts = scan_metrics.detect_alerts(replayed, record)
        record["alerts"] = [alert["kind"] for alert in alerts]
        active += len(alerts)
        for alert in filter(scan_metrics.is_notable, alerts):
            notified += 1
            marker = "promemoria " if alert.get("reminder") else ""
            print(f"{record['attempted_at'][:10]}  {marker}{scan_metrics.alert_message(alert)}")
        replayed.append(record)
    print(f"{notified} avvisi notificati su {active} attivi nelle scansioni")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                              for record in merged), encoding="utf-8")
    print(f"{len(merged)} scansioni in {output} ({len(merged) - len(existing)} ricostruite)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default=str(DEFAULT_DIR), help="cartella dei dati scaricati")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", parents=[common], help="scarica report, log e commit delle run con gh")
    build = commands.add_parser("build", parents=[common],
                                help="unisce le run scaricate al file delle metriche")
    build.add_argument("--output", default="", help="file di destinazione (default: quello configurato)")
    args = parser.parse_args()
    {"fetch": cmd_fetch, "build": cmd_build}[args.command](args)


if __name__ == "__main__":
    main()
