"""Data contracts: the published files keep their shape and the pipeline's own rules."""

import json
import re
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from models import HackathonEvent
from utils import data_contracts as contracts
from utils.data_contracts import DataContractError

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 29)


def _record(url="https://example.com/hack", **changes) -> dict:
    item = HackathonEvent(title="Milano AI Hackathon", url=url, source="luma",
                          date_str="2026-11-20", date_source="event", location="Milano",
                          is_hackathon=True, confidence=0.95, review_status="ai_verified").to_dict()
    item.update(changes)
    return item


def _queued(url="https://example.com/queued", **changes) -> dict:
    item = _record(url, is_hackathon=False, review_status="needs_review",
                   queued_at="2026-10-20T10:00:00+00:00")
    item.update(changes)
    return item


class TestArchive:
    def test_valid_archive(self):
        assert contracts.check_archive({"last_check": "x", "events": [_record()]}, TODAY) == []

    @pytest.mark.parametrize("changes, expected", [
        ({"confidence": True}, "confidence ha tipo bool"),
        ({"is_hackathon": "true"}, "is_hackathon ha tipo str"),
        ({"title": "  "}, "titolo vuoto"),
        ({"url": "javascript:alert(1)"}, "URL non http(s)"),
        ({"id": "0" * 64}, "id diverso dall'hash dell'URL"),
        ({"confidence": 1.5}, "confidence fuori da 0–1"),
        ({"review_status": "maybe"}, "review_status sconosciuto"),
        ({"provenance": "gpt"}, "provenance ha tipo str"),
    ])
    def test_field_problems(self, changes, expected):
        [problem] = contracts.check_archive({"events": [_record(**changes)]}, TODAY)
        assert expected in problem

    def test_missing_field(self):
        item = _record()
        del item["alternate_urls"]
        assert contracts.check_archive({"events": [item]}, TODAY) == [
            f"evento #0 {item['id'][:12]}: manca il campo alternate_urls",
        ]

    def test_messages_name_records_by_short_id_never_by_title(self):
        """Violations reach the public run report: candidate titles stay out of it."""
        bad = [_record(f"https://example.com/{index}", title="Riservato", **change) for index, change in
               enumerate([{"confidence": 2.0}, {"review_status": "x"}])]
        problems = contracts.check_archive({"events": bad}, TODAY)
        problems += contracts.check_archive({"events": [_record(title="Riservato", date_str="2026-01-01")]}, TODAY)
        problems += contracts.check_review_queue([_queued(title="Riservato", queued_at="")], TODAY)
        assert len(problems) == 4 and not any("Riservato" in problem for problem in problems)
        assert contracts.check_archive({"events": [_record(id="x", title="Riservato")]}, TODAY) == [
            "evento #0: id diverso dall'hash dell'URL",
        ]

    def test_alias_ceiling_catches_the_september_corruption(self):
        """Oliver Wyman reached 26 aliases on 2026-09-09 and 99 by late October."""
        aliases = [f"https://example.com/other-{index}" for index in range(26)]
        [problem] = contracts.check_archive({"events": [_record(alternate_urls=aliases)]}, TODAY)
        assert "26 URL alternativi (limite 25)" in problem
        assert contracts.check_archive({"events": [_record(alternate_urls=aliases[:25])]}, TODAY) == []

    def test_an_alias_cannot_be_another_events_page(self):
        other = _record("https://example.com/other")
        first = _record(alternate_urls=["https://example.com/other"])
        [problem] = contracts.check_archive({"events": [first, other]}, TODAY)
        assert "URL alternativo è l'URL di un altro evento" in problem

    def test_duplicate_ids(self):
        problems = contracts.check_archive({"events": [_record(), _record()]}, TODAY)
        assert any("id duplicato" in problem for problem in problems)

    def test_no_expired_publication_unless_a_reviewed_end_date_covers_it(self):
        started = _record(date_str="2026-10-27")
        [problem] = contracts.check_archive({"events": [started]}, TODAY)
        assert "evento passato ancora pubblicato" in problem
        ends = {started["id"]: date(2026, 10, 30)}
        assert contracts.check_archive({"events": [started]}, TODAY, reviewed_end_dates=ends) == []

    def test_unpublished_records_may_be_past(self):
        assert contracts.check_archive(
            {"events": [_record(date_str="2026-01-01", is_hackathon=False)]}, TODAY) == []

    def test_structure(self):
        assert contracts.check_archive([], TODAY) == ["events.json: serve un oggetto con la lista events"]


class TestReviewQueue:
    def test_valid_queue(self):
        assert contracts.check_review_queue([_queued()], TODAY) == []

    def test_published_decided_and_expired_candidates_leave_the_queue(self):
        published, decided = _queued("https://example.com/a"), _queued("https://example.com/b")
        expired = _queued("https://example.com/c", date_str="2026-10-01")
        problems = contracts.check_review_queue(
            [published, decided, expired], TODAY, published_ids={published["id"]},
            decisions={decided["id"]: {"decision": "rejected"}},
        )
        assert [problem.split(": ", 1)[1] for problem in problems] == [
            "è già pubblicato", "ha già una decisione", "evento passato ancora in coda",
        ]

    def test_queue_records(self):
        problems = contracts.check_review_queue(
            [_queued(review_status="ai_verified"), _queued("https://example.com/x", queued_at="")], TODAY)
        assert len(problems) == 2

    def test_envelope_count(self):
        assert contracts.check_queue_file({"count": 2, "candidates": [_queued()]}) == [
            "review_queue.json: count diverso dal numero di candidati",
        ]


def test_publications_need_a_verified_future_date():
    future = HackathonEvent(title="A", url="https://a.com", source="s", date_str="2026-11-20",
                            date_source="event")
    undated = HackathonEvent(title="B", url="https://b.com", source="s")
    assert contracts.check_publications([future, undated], TODAY) == [
        f"pubblicazione {undated.id[:12]}: data evento non verificata come futura",
    ]


class TestCommittedData:
    """The files in the repository satisfy the contracts as of their own last check."""

    @staticmethod
    def _load(name):
        path = ROOT / "data" / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def test_archive_and_queue(self):
        archive = self._load("events.json")
        if archive is None:
            pytest.skip("no archive")
        today = datetime.fromisoformat(archive["last_check"]).date() if archive.get("last_check") else TODAY
        details = self._load("event_details.json") or []
        ends = {item["id"]: date.fromisoformat(item["endDate"]) for item in details
                if isinstance(item, dict) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(item.get("endDate")))}
        assert contracts.check_archive(archive, today, reviewed_end_dates=ends) == []

        queue = self._load("review_queue.json")
        if queue is not None:
            decisions = (self._load("review_decisions.json") or {}).get("decisions") or {}
            published = {item["id"] for item in archive["events"] if item.get("is_hackathon")}
            assert contracts.check_queue_file(queue) == []
            assert contracts.check_review_queue(queue["candidates"], today, published_ids=published,
                                                decisions=decisions) == []

    def test_metrics_lines_hold_aggregates_only(self):
        path = ROOT / "data" / "metrics" / "scans.jsonl"
        if not path.exists():
            pytest.skip("no metrics yet")
        allowed = {"schema", "scan_id", "attempted_at", "status", "origin", "commit",
                   "duration_seconds", "counts", "stages", "sources", "classifier", "alerts", "error"}
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            assert set(record) <= allowed and record["schema"] == 1
            for source in record["sources"].values():
                assert set(source) <= {"status", "events", "issues"}
            datetime.fromisoformat(record["attempted_at"])


@patch("main.notify_run_summary")
@patch("main.get_collectors", return_value=["s"])
@patch("main.generate_readme_table")
@patch("main.generate_html")
@patch("main.llm_dedup", side_effect=lambda events: events)
@patch("main.llm_filter")
@patch("main.keyword_filter_batch")
@patch("main.run_collectors")
@patch("main.EventStore")
def test_a_violation_stops_the_scan_before_any_file_is_replaced(
    MockStore, mock_run_coll, mock_kw, mock_llm, _dedup, mock_html, _readme, _collectors, mock_notify,
    tmp_path, monkeypatch, capsys,
):
    from main import run_pipeline

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    corrupted = _record("https://example.com/archived", date_str="2030-05-01", title="Evento riservato",
                        alternate_urls=[f"https://example.com/p{index}" for index in range(30)])
    store = MagicMock(count=1)
    store.all_events.return_value = [corrupted]
    store.is_duplicate.return_value = False
    MockStore.return_value = store
    events = [HackathonEvent(title="Hack", url="https://a.com/1", source="s",
                             date_str="2030-11-20", date_source="event")]
    mock_run_coll.return_value = (events, ["s"], [], [
        {"name": "s", "ok": True, "event_count": 1, "status": "healthy", "issues": []},
    ])
    mock_kw.return_value = (events, 0)
    mock_llm.return_value = (events, 0)
    queue_file = tmp_path / "review_queue.json"

    with (
        patch("main.config.DATA_DIR", tmp_path),
        patch("main._cleanup_existing_event_dicts", side_effect=lambda items, ref_date: items),
        patch("main.config.REVIEW_QUEUE_FILE", queue_file),
        patch("main.config.REVIEW_DECISIONS_FILE", tmp_path / "review_decisions.json"),
        pytest.raises(DataContractError) as stopped,
    ):
        run_pipeline(dry_run=False)

    assert "30 URL alternativi (limite 25)" in str(stopped.value)
    store.save_with_timestamp.assert_not_called()
    mock_html.assert_not_called()
    assert not queue_file.exists()
    report_text = (tmp_path / "last_report.json").read_text()
    report = json.loads(report_text)
    assert report["status"] == "contract_failed_preserved" and report["new_events"] == 0
    assert report["contract_violation_count"] == 1
    # Counts of the files left on disk; what the scan would have written is apart.
    assert report["total_stored"] == 1 and report["review_queue"] == 0
    assert report["proposed"]["new_events"] == 1
    # Public outputs name the record by short id; the private Telegram summary adds the title.
    short_id = corrupted["id"][:12]
    assert report["contract_violations"] == [f"evento #0 {short_id}: 30 URL alternativi (limite 25)"]
    annotations = capsys.readouterr().out
    assert "::error title=Contratto sui dati violato::evento #0 " + short_id in annotations
    assert "Evento riservato" not in report_text and "Evento riservato" not in annotations
    assert mock_notify.call_args.kwargs["scan_status"] == "contract_failed_preserved"
    assert mock_notify.call_args.kwargs["contract_violations"] == [
        f"evento #0 {short_id} 'Evento riservato': 30 URL alternativi (limite 25)",
    ]


def test_blocked_publication_telegram_counts_only_persisted_events(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main.config, "DATA_DIR", tmp_path)
    proposed = _record(title="Unpublished event")
    store = MagicMock()
    store.all_events.return_value = [proposed]
    report = {"new_events": 1, "total_stored": 1, "review_queue": 0}
    main.reset_usage()
    with patch("main.notify_run_summary") as notify, pytest.raises(DataContractError):
        main._stop_on_contract_violations(
            ["invalid proposal"], report, dry_run=False, store=store, queue=[],
            on_disk={"total_stored": 0, "review_queue": 0, "total_upcoming": 0},
            collector_runs=[], failed_collectors=[], start_time=main._now(),
        )
    assert notify.call_args.kwargs["total_upcoming"] == 0
    assert report["total_stored"] == 0 and report["proposed"]["total_stored"] == 1


def test_the_command_exits_with_an_error(monkeypatch):
    import main

    monkeypatch.setattr("sys.argv", ["main.py", "--dry-run"])
    monkeypatch.setattr(main, "run_pipeline", MagicMock(side_effect=DataContractError(["x"])))
    with pytest.raises(SystemExit) as exited:
        main.main()
    assert exited.value.code == 1
