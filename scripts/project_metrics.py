#!/usr/bin/env python3
"""Build a local project report from saved data, without APIs or application imports."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
REVIEW_STATUSES = {"ai_pending", "ai_verified", "manual_approved", "manual_rejected", "needs_review", "llm_error"}
SCAN_COUNTS = ("collectors_ok", "collectors_total", "raw_events", "post_dedup", "post_keyword", "post_llm", "new_events", "total_stored", "review_queue")


def read_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a JSON object")
    return data


def iso_date(value: object) -> date | None:
    """Accept complete ISO dates/timestamps; never infer missing days or years."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def source_timestamp(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and iso_date(value) else None


def known_status(value: object, allowed: set[str]) -> str:
    return value if isinstance(value, str) and value in allowed else "unknown"


def revision(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, text=True, timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def review_queue(root: Path) -> dict:
    result = {"source": "data/review_queue.json", "available": False, "updated_at": None, "count": None}
    try:
        data = read_object(root / result["source"])
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or any(not isinstance(item, dict) for item in candidates):
            return result
        result.update(available=True, updated_at=source_timestamp(data.get("updated_at")), count=len(candidates))
    except (OSError, ValueError):
        pass
    return result


def last_scan(root: Path) -> dict:
    result = {"source": "data/last_report.json", "available": False, "recorded_at": None, "status": None, "counts": {}}
    try:
        data = read_object(root / result["source"])
        result.update(
            available=True,
            recorded_at=source_timestamp(data.get("date")),
            status=known_status(data.get("status"), {"completed", "llm_failed_preserved"}),
            counts={key: data[key] for key in SCAN_COUNTS if type(data.get(key)) is int and data[key] >= 0},
        )
    except (OSError, ValueError):
        pass
    return result


def build_report(root: Path, as_of: date) -> dict:
    path = root / "data/events.json"
    raw = path.read_bytes()
    payload = json.loads(raw)
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list) or any(not isinstance(item, dict) for item in events):
        raise ValueError("events.json: expected an events array of objects")

    dates = [iso_date(event.get("date_str")) for event in events]
    dated = [value for value in dates if value is not None]
    missing = sum(
        event.get("date_str") is None
        or isinstance(event.get("date_str"), str) and not event["date_str"].strip()
        for event in events
    )
    statuses = Counter(known_status(event.get("review_status"), REVIEW_STATUSES) for event in events)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of.isoformat(),
        "timezone": "Europe/Rome",
        "source_revision": revision(root),
        "catalog": {
            "source": "data/events.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "last_check": source_timestamp(payload.get("last_check")),
            "total_events": len(events),
            "confirmed_hackathons": sum(event.get("is_hackathon") is True for event in events),
            "complete_dates": len(dated),
            "missing_dates": missing,
            "unrecognized_dates": len(events) - len(dated) - missing,
            "upcoming_dated": sum(value >= as_of for value in dated),
            "past_dated": sum(value < as_of for value in dated),
            "review_status_counts": dict(sorted(statuses.items())),
        },
        "review_queue": review_queue(root),
        "last_scan": last_scan(root),
        "site_usage": {
            "available": False,
            "visitors": None,
            "page_views": None,
            "source": "Vercel Web Analytics dashboard (separate source)",
            "note": "Traffic is not contained in the repository and is not fetched by this report.",
        },
    }


def render_markdown(report: dict) -> str:
    catalog, queue, scan = report["catalog"], report["review_queue"], report["last_scan"]
    rows = [
        ("Eventi in archivio", catalog["total_events"]),
        ("Hackathon confermati", catalog["confirmed_hackathons"]),
        ("Con data ISO completa", catalog["complete_dates"]),
        ("Senza data", catalog["missing_dates"]),
        ("Data non interpretabile", catalog["unrecognized_dates"]),
        ("Datati: oggi o futuri", catalog["upcoming_dated"]),
        ("Datati: passati", catalog["past_dated"]),
        ("Candidati in revisione", queue["count"] if queue["available"] else "Non disponibile"),
    ]
    lines = [
        "# Hackathon Milano — Metriche del progetto", "",
        f"Generato: {report['generated_at']} · riferimento: {report['as_of']} (Europe/Rome).",
        f"Revisione: {report['source_revision'] or 'non disponibile'}.",
        f"Fonte: `{catalog['source']}` · ultima scansione dichiarata: {catalog['last_check'] or 'non disponibile'}.",
        f"SHA-256 del catalogo locale: `{catalog['sha256']}`.", "",
        "| Indicatore | Valore |", "| --- | ---: |",
        *[f"| {label} | {value} |" for label, value in rows], "",
        "Conteggi relativi all’archivio locale, non allo storico di tutti gli eventi mai trovati. Le date mancanti o non interpretabili non sono classificate come future. Una data completa descrive il formato, non certifica la correttezza dell’evento.", "",
        "## Revisione", "",
        *[f"- {status}: {count}" for status, count in catalog["review_status_counts"].items()],
        f"\nFonte coda: `{queue['source']}` · aggiornata: {queue['updated_at'] or 'non disponibile'}.", "",
        "## Ultimo report locale della pipeline", "",
    ]
    if scan["available"]:
        lines.extend([
            f"Fonte: `{scan['source']}` · data: {scan['recorded_at'] or 'non disponibile'} · stato: {scan['status']}.",
            "Questo report può essere precedente al catalogo: i suoi conteggi non rappresentano necessariamente la scansione corrente.", "",
            *[f"- {key}: {value}" for key, value in scan["counts"].items()], "",
        ])
    else:
        lines.extend(["Non disponibile; nessun conteggio stimato.", ""])
    lines.extend([
        "## Utilizzo del sito", "",
        "Visitatori e visualizzazioni: **non disponibili in questo report**. Non equivale a zero utenti.",
        "Consultare Web Analytics nel progetto Vercel, dopo l’attivazione, indicando sempre il periodo osservato. Il traffico è una fonte separata e non viene recuperato da questo script.", "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(ZoneInfo("Europe/Rome")).date(), metavar="YYYY-MM-DD")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".local/metrics", help="Report directory (default: ignored .local/metrics)")
    args = parser.parse_args(argv)
    try:
        report = build_report(ROOT, args.as_of)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "latest.md").write_text(render_markdown(report), encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Local reports written to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
