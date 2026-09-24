"""Project metrics must separate unknown values and omit private source details."""

from datetime import date
import hashlib
import json

from scripts import project_metrics


def write_data(root, name, payload):
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / name).write_text(json.dumps(payload), encoding="utf-8")


def test_catalog_dates_are_complete_and_do_not_invent_upcoming_events(tmp_path):
    values = ["2026-09-23", "2026-09-24", "2026-09-25T01:00:00+02:00", "", "21settembre2026", "2026-02-30", "2026-10", None]
    write_data(tmp_path, "events.json", {
        "last_check": "2026-09-23T10:00:00+02:00",
        "events": [{"date_str": value, "is_hackathon": True, "review_status": "ai_verified"} for value in values],
    })
    report = project_metrics.build_report(tmp_path, date(2026, 9, 24))
    catalog = report["catalog"]
    assert catalog["total_events"] == catalog["confirmed_hackathons"] == 8
    assert (catalog["complete_dates"], catalog["missing_dates"], catalog["unrecognized_dates"]) == (3, 2, 3)
    assert (catalog["upcoming_dated"], catalog["past_dated"]) == (2, 1)
    assert catalog["review_status_counts"] == {"ai_verified": 8}
    assert catalog["sha256"] == hashlib.sha256((tmp_path / "data/events.json").read_bytes()).hexdigest()
    assert report["site_usage"]["visitors"] is None
    assert report["review_queue"]["count"] is None


def test_optional_sources_expose_only_whitelisted_aggregates(tmp_path):
    write_data(tmp_path, "events.json", {"events": [{"date_str": "", "review_status": "private reviewer note"}]})
    write_data(tmp_path, "review_queue.json", {"updated_at": "2026-09-20T12:00:00", "count": 999, "candidates": [{"review_note": "private queue note"}]})
    write_data(tmp_path, "last_report.json", {
        "date": "2026-05-03 13:41", "status": "completed", "raw_events": 12,
        "new_events": -1, "post_llm": True, "collectors_ok": "private collector note",
        "failed_collectors": ["private source details"], "token": "private credential",
    })
    report = project_metrics.build_report(tmp_path, date(2026, 9, 24))
    assert report["review_queue"]["count"] == 1
    assert report["last_scan"]["recorded_at"] == "2026-05-03 13:41"
    assert report["last_scan"]["counts"] == {"raw_events": 12}
    assert report["catalog"]["review_status_counts"] == {"unknown": 1}
    assert "private" not in json.dumps(report)
    markdown = project_metrics.render_markdown(report)
    assert "2026-05-03 13:41" in markdown
    assert "può essere precedente" in markdown
    assert "Non equivale a zero utenti" in markdown


def test_cli_writes_only_local_reports_and_handles_missing_optional_sources(tmp_path, monkeypatch):
    write_data(tmp_path, "events.json", {"events": []})
    source = (tmp_path / "data/events.json").read_bytes()
    monkeypatch.setattr(project_metrics, "ROOT", tmp_path)
    assert project_metrics.main(["--as-of", "2026-09-24"]) == 0
    report = json.loads((tmp_path / ".local/metrics/latest.json").read_text())
    assert report["as_of"] == "2026-09-24"
    assert report["review_queue"]["available"] is False
    assert report["last_scan"]["available"] is False
    assert report["site_usage"]["page_views"] is None
    assert (tmp_path / ".local/metrics/latest.md").exists()
    assert (tmp_path / "data/events.json").read_bytes() == source
    assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file()) == [".local/metrics/latest.json", ".local/metrics/latest.md", "data/events.json"]
