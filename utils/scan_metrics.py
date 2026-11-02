"""Per-scan aggregate metrics and source-health alerts.

Every scan appends one JSON line to ``data/metrics/scans.jsonl``: statuses and
counts only, never candidate content, so the file can be committed with the
public data. Alerts compare the scan with the lines before it.
"""

import json
import logging
import os
from pathlib import Path
from statistics import median

import config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
# A source is silent after SILENT_SCANS consecutive scans without records, when
# at least MIN_ACTIVE_SCANS of the BASELINE_SCANS scans before the silence had records.
SILENT_SCANS = 3
BASELINE_SCANS = 14
MIN_ACTIVE_SCANS = 3
# Raw volume below this share of the median of the previous scans.
VOLUME_DROP_RATIO = 0.5
MIN_VOLUME_HISTORY = 5
# A problem already reported comes back as a reminder every REMINDER_SCANS scans
# while it lasts (about weekly with one scan a day); in between it is one line.
REMINDER_SCANS = 7

_COUNT_KEYS = (
    ("raw", "raw_events"), ("new", "post_dedup"), ("keyword", "post_keyword"),
    ("approved", "post_llm"), ("published", "new_events"),
    ("review_queue", "review_queue"), ("archive", "total_stored"),
)
_ALERT_TITLES = {
    "source_silent": "Fonte ferma",
    "source_recovered": "Fonte tornata",
    "volume_drop": "Calo degli eventi raccolti",
    "classifier_fallback": "Modello di riserva",
    "classifier_errors": "Errori del classificatore",
}


def metrics_path() -> Path:
    """Configured file, else ``metrics/scans.jsonl`` under the current data directory."""
    configured = getattr(config, "METRICS_FILE", "")
    return Path(configured) if configured else Path(config.DATA_DIR) / "metrics" / "scans.jsonl"


def _count(value) -> int | None:
    return value if type(value) is int and value >= 0 else None


def scan_record(report: dict, *, scan_id: str, commit: str,
                classifier: dict | None = None, origin: str = "live") -> dict:
    """Compact, content-free summary of one scan report."""
    sources: dict[str, dict] = {}
    for run in report.get("collector_runs") or []:
        name = run.get("name") if isinstance(run, dict) else None
        if not isinstance(name, str) or not name:
            continue
        events = _count(run.get("event_count")) or 0
        # Reports before October 2026 carry only `ok`; same meaning as collector_health.
        status = run.get("status") or ("failed" if not run.get("ok") else "healthy" if events else "empty")
        entry = {"status": status, "events": events}
        kinds = sorted({str(issue["kind"]) for issue in run.get("issues") or []
                        if isinstance(issue, dict) and issue.get("kind")})
        if kinds:
            entry["issues"] = kinds
        sources[name] = entry

    stages = {
        stage["stage"]: [stage["input"], stage["output"]]
        for stage in report.get("candidate_stages") or []
        if isinstance(stage, dict) and isinstance(stage.get("stage"), str)
        and _count(stage.get("input")) is not None and _count(stage.get("output")) is not None
    }
    counts = {name: _count(report.get(key)) for name, key in _COUNT_KEYS}
    if "classification" in stages:
        counts["classified"] = stages["classification"][0]

    record = {
        "schema": SCHEMA_VERSION,
        "scan_id": scan_id,
        "attempted_at": report.get("attempted_at") or "",
        "status": report.get("status") or "",
        "origin": origin,
        "commit": commit,
        "duration_seconds": report.get("duration_seconds"),
        "counts": counts,
        "stages": stages,
        "sources": dict(sorted(sources.items())),
        "classifier": classifier,
    }
    if isinstance(report.get("error"), str) and report["error"]:
        record["error"] = report["error"][:80]  # exception type of a crashed scan
    return record


def load_history(path: Path | None = None, limit: int | None = None) -> list[dict]:
    """Records in file order; optionally restrict to the latest lines.

    Alert detection needs the complete history: a long silence must retain the
    productive baseline before it, and reminders must keep their original cadence.
    Unreadable JSON lines are skipped, not fatal.
    """
    path = path or metrics_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        logger.warning("Storico metriche non leggibile (%s): %s", path, type(exc).__name__)
        return []
    records = []
    for line in lines if limit is None else lines[-limit:]:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def append_record(record: dict, path: Path | None = None) -> Path:
    path = path or metrics_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a+b") as output:
        # A line cut short by an interrupted append must not swallow this one.
        if output.seek(0, os.SEEK_END):
            output.seek(-1, os.SEEK_END)
            if output.read(1) != b"\n":
                line = "\n" + line
        output.write(line.encode("utf-8"))  # append mode: always at the end
    return path


def _silent_sources(records: list[dict]) -> list[dict]:
    current = records[-1]
    alerts = []
    for name, entry in current.get("sources", {}).items():
        if entry.get("status") == "disabled" or entry.get("events", 0) > 0:
            continue
        series = [record.get("sources", {}).get(name) for record in records]
        streak = 0
        for item in reversed(series):
            if not isinstance(item, dict) or item.get("events", 0) > 0 or item.get("status") == "disabled":
                break
            streak += 1
        if streak < SILENT_SCANS:
            continue
        baseline = [item for item in series[:-streak] if isinstance(item, dict)][-BASELINE_SCANS:]
        active = [item["events"] for item in baseline if item.get("events", 0) > 0]
        if len(active) < MIN_ACTIVE_SCANS:
            continue
        alerts.append({
            "kind": "source_silent", "source": name, "status": entry.get("status", ""),
            "scans": streak, "usual_events": int(median(active)),
        })
    return alerts


def _mark(alert: dict, reported_for: int) -> dict:
    """`reported_for`: consecutive earlier scans that already had this alert."""
    alert["new"] = reported_for == 0
    alert["reminder"] = reported_for > 0 and reported_for % REMINDER_SCANS == 0
    return alert


def _reported_for(kind: str, ran: list[dict]) -> int:
    streak = 0
    for record in reversed(ran):
        if kind not in (record.get("alerts") or []):
            break
        streak += 1
    return streak


def is_notable(alert: dict) -> bool:
    """New problems, recoveries and reminders; the rest was already reported."""
    return bool(alert.get("new") or alert.get("reminder"))


def detect_alerts(history: list[dict], current: dict) -> list[dict]:
    """Silent sources, a collapse of the raw volume and classifier trouble in this scan.

    Each alert is marked `new`, as a `reminder`, or neither when an earlier scan
    already reported it. A source silent in the previous scan that has records
    again gives a `source_recovered` alert.
    """
    # Scans that reached the sources; a crashed scan neither extends nor breaks a streak.
    ran = [record for record in history if isinstance(record.get("sources"), dict) and record["sources"]]
    before = {alert["source"]: alert for alert in _silent_sources(ran)} if ran else {}
    alerts = [
        _mark(alert, alert["scans"] - SILENT_SCANS if alert["source"] in before else 0)
        for alert in (_silent_sources(ran + [current]) if current.get("sources") else [])
    ]
    for name, silent in before.items():
        entry = current.get("sources", {}).get(name)
        if isinstance(entry, dict) and entry.get("events", 0) > 0:
            alerts.append(_mark({"kind": "source_recovered", "source": name,
                                 "events": entry["events"], "scans": silent["scans"]}, 0))
    others: list[dict] = []

    raw = (current.get("counts") or {}).get("raw")
    prior = [
        record["counts"]["raw"] for record in history[-BASELINE_SCANS:]
        if isinstance(record.get("counts"), dict) and _count(record["counts"].get("raw")) is not None
        and record.get("status") != "collection_failed_preserved"
    ]
    if _count(raw) is not None and len(prior) >= MIN_VOLUME_HISTORY:
        typical = median(prior)
        if typical > 0 and raw < VOLUME_DROP_RATIO * typical:
            others.append({"kind": "volume_drop", "raw": raw, "median": int(typical)})

    classifier = current.get("classifier") or {}
    if classifier.get("fallback_calls"):
        others.append({
            "kind": "classifier_fallback", "calls": classifier["fallback_calls"],
            "models": sorted(name for name in classifier.get("models") or {}
                             if name != classifier.get("primary_model")),
        })
    failed, errors = classifier.get("failed_calls") or 0, classifier.get("errors") or 0
    if failed or errors:
        others.append({"kind": "classifier_errors", "failed_calls": failed, "errors": errors})
    return alerts + [_mark(alert, _reported_for(alert["kind"], ran)) for alert in others]


def alert_message(alert: dict) -> str:
    """One Italian line, shared by logs, workflow annotations and Telegram."""
    kind = alert.get("kind")
    if kind == "source_silent":
        return (f"{alert['source']}: nessun evento da {alert['scans']} scansioni "
                f"(prima di solito {alert['usual_events']}; stato {alert['status']})")
    if kind == "source_recovered":
        events = alert["events"]
        return (f"{alert['source']} è tornata: {events} event{'o' if events == 1 else 'i'} "
                f"dopo {alert['scans']} scansioni senza risultati")
    if kind == "volume_drop":
        return (f"{alert['raw']} eventi raccolti, meno della metà della mediana "
                f"delle scansioni precedenti ({alert['median']})")
    if kind == "classifier_fallback":
        models = ", ".join(alert.get("models") or []) or "modello di riserva"
        calls = alert["calls"]
        return f"{models} ha risposto a {calls} chiamat{'a' if calls == 1 else 'e'} al posto del modello principale"
    if kind == "classifier_errors":
        errors, failed = alert["errors"], alert["failed_calls"]
        return (f"{errors} candidat{'o' if errors == 1 else 'i'} senza classificazione, "
                f"{failed} chiamat{'a fallita' if failed == 1 else 'e fallite'} su tutti i modelli")
    return str(kind)


def _annotation_text(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def alert_subject(alert: dict) -> str:
    """Short name of what an alert is about, for the line of already reported ones."""
    return alert.get("source") or _ALERT_TITLES.get(alert.get("kind"), str(alert.get("kind"))).lower()


def emit_alerts(alerts: list[dict]) -> None:
    """Warnings and run annotations for notable alerts; known ones only as an info line."""
    for alert in alerts:
        message = alert_message(alert)
        if not is_notable(alert):
            logger.info("Avviso già segnalato: %s", message)
            continue
        logger.warning("Avviso scansione: %s", message)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            title = _ALERT_TITLES.get(alert.get("kind"), "Avviso")
            if alert.get("reminder"):
                title += " (promemoria)"
            level = "notice" if alert.get("kind") == "source_recovered" else "warning"
            # Shown on the workflow run page, not only in the raw log.
            print(f"::{level} title={title}::{_annotation_text(message)}")


def record_scan(report: dict, *, scan_id: str, commit: str, classifier: dict | None,
                persist: bool = True, path: Path | None = None) -> tuple[dict, list[dict]]:
    """Append one outcome per scan ID; a retry returns the first saved outcome.

    With `persist` off, compute the proposed record and alerts without appending.
    """
    path = path or metrics_path()
    history = load_history(path)
    if persist:
        for index, existing in enumerate(history):
            if existing.get("scan_id") == scan_id:
                return existing, detect_alerts(history[:index], existing)
    record = scan_record(report, scan_id=scan_id, commit=commit, classifier=classifier)
    alerts = detect_alerts(history, record)
    record["alerts"] = [alert["kind"] for alert in alerts]
    if persist:
        try:
            append_record(record, path)
        except OSError as exc:
            logger.warning("Metriche della scansione non salvate (%s): %s", path, type(exc).__name__)
    return record, alerts
