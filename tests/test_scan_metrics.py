"""Per-scan metrics, source alerts and classification provenance."""

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import config
from filters import llm_filter
from filters.llm_filter import LLMResult
from models import HackathonEvent
from notifiers.telegram import _format_run_summary
from utils import scan_metrics
from utils.scan_metrics import alert_message, detect_alerts, record_scan, scan_record


def _report(sources: dict[str, int], *, raw: int = 400, status: str = "completed", **extra) -> dict:
    return {
        "status": status, "attempted_at": "2026-10-17T16:03:00+02:00", "raw_events": raw,
        "post_dedup": raw - 10, "post_keyword": 40, "post_llm": 2, "new_events": 1,
        "review_queue": 5, "total_stored": 6,
        "collector_runs": [
            {"name": name, "ok": count > 0, "event_count": count,
             "status": "healthy" if count else "blocked",
             "issues": [] if count else [{"kind": "http_403", "detail": "HTTP 403",
                                          "endpoint": "https://example.org/private-path"}]}
            for name, count in sources.items()
        ],
        **extra,
    }


def _history(series: dict[str, list[int]]) -> list[dict]:
    length = len(next(iter(series.values())))
    return [scan_record(_report({name: values[index] for name, values in series.items()}),
                        scan_id=f"gh-{index}", commit="abc")
            for index in range(length)]


class TestScanRecord:
    def test_keeps_counts_and_issue_kinds_without_details(self):
        record = scan_record(_report({"luma": 12, "regione_lombardia": 0}, candidate_stages=[
            {"stage": "classification", "input": 44, "output": 2},
        ]), scan_id="gh-1", commit="abc", classifier={"fallback_calls": 0})

        assert record["sources"] == {
            "luma": {"status": "healthy", "events": 12},
            "regione_lombardia": {"status": "blocked", "events": 0, "issues": ["http_403"]},
        }
        assert record["counts"]["raw"] == 400 and record["counts"]["classified"] == 44
        assert record["stages"] == {"classification": [44, 2]}
        text = json.dumps(record)
        assert "HTTP 403" not in text and "private-path" not in text

    def test_reports_before_source_statuses_are_read_from_ok(self):
        record = scan_record({"collector_runs": [
            {"name": "a", "ok": True, "event_count": 3},
            {"name": "b", "ok": True, "event_count": 0},
            {"name": "c", "ok": False, "event_count": 0},
        ]}, scan_id="gh-1", commit="")
        assert {name: item["status"] for name, item in record["sources"].items()} == {
            "a": "healthy", "b": "empty", "c": "failed",
        }


class TestSourceAlerts:
    def test_regione_lombardia_fires_on_the_third_scan_without_records(self):
        history = _history({"regione_lombardia": [29] * 10 + [0, 0], "luma": [12] * 12})
        current = scan_record(_report({"regione_lombardia": 0, "luma": 12}), scan_id="gh-x", commit="")

        alerts = detect_alerts(history, current)

        assert alerts == [{
            "kind": "source_silent", "source": "regione_lombardia", "status": "blocked",
            "scans": 3, "usual_events": 29, "new": True, "reminder": False,
        }]
        assert "nessun evento da 3 scansioni" in alert_message(alerts[0])

    def test_an_ongoing_silence_is_no_longer_new(self):
        history = _history({"camera_commercio": [74] * 10 + [0, 0, 0]})
        current = scan_record(_report({"camera_commercio": 0}), scan_id="gh-x", commit="")
        [alert] = detect_alerts(history, current)
        assert alert["scans"] == 4 and alert["new"] is False and alert["reminder"] is False

    def test_a_known_silence_is_repeated_once_a_week_and_its_end_is_reported(self):
        """Replay as the pipeline does: 10 active scans, 18 silent ones, then records again."""
        replayed, notable = [], []
        for index, events in enumerate([74] * 10 + [0] * 18 + [70]):
            record = scan_record(_report({"camera_commercio": events}), scan_id=f"gh-{index}", commit="")
            alerts = detect_alerts(replayed, record)
            record["alerts"] = [alert["kind"] for alert in alerts]
            replayed.append(record)
            notable += [(index, alert["kind"], alert.get("scans")) for alert in alerts
                        if scan_metrics.is_notable(alert)]
        assert notable == [
            (12, "source_silent", 3),       # new
            (19, "source_silent", 10),      # reminders, one every REMINDER_SCANS scans
            (26, "source_silent", 17),
            (28, "source_recovered", 18),
        ]

    def test_a_crashed_scan_does_not_break_or_restart_a_silence(self):
        history = _history({"camera_commercio": [74] * 10 + [0, 0, 0]})
        history.insert(-1, scan_record({"status": "crashed", "error": "OSError"}, scan_id="gh-c", commit=""))
        current = scan_record(_report({"camera_commercio": 0}), scan_id="gh-x", commit="")
        [alert] = detect_alerts(history, current)
        assert alert["scans"] == 4 and alert["new"] is False

    def test_long_silence_keeps_its_reminders_and_recovery(self, tmp_path):
        path = tmp_path / "scans.jsonl"
        history = _history({"camera_commercio": [74] * 10 + [0] * 128})
        path.write_text("".join(json.dumps(record) + "\n" for record in history), encoding="utf-8")

        _, alerts = record_scan(_report({"camera_commercio": 0}), scan_id="gh-still-silent",
                                commit="", classifier=None, path=path)
        assert alerts == [{
            "kind": "source_silent", "source": "camera_commercio", "status": "blocked",
            "scans": 129, "usual_events": 74, "new": False, "reminder": True,
        }]

        _, alerts = record_scan(_report({"camera_commercio": 70}), scan_id="gh-recovered",
                                commit="", classifier=None, path=path)
        assert alerts == [{
            "kind": "source_recovered", "source": "camera_commercio", "events": 70,
            "scans": 129, "new": True, "reminder": False,
        }]

    def test_repeated_classifier_trouble_is_new_only_the_first_time(self):
        classifier = {"primary_model": "a", "fallback_calls": 1, "models": {"a": {}, "b": {}}}
        replayed, flags = [], []
        for index in range(9):
            record = scan_record(_report({"luma": 3}), scan_id=f"gh-{index}", commit="",
                                 classifier=classifier)
            [alert] = detect_alerts(replayed, record)
            record["alerts"] = [alert["kind"]]
            replayed.append(record)
            flags.append((alert["new"], alert["reminder"]))
        assert flags[0] == (True, False) and flags[1] == (False, False)
        assert flags[7] == (False, True) and flags.count((False, False)) == 7

    @pytest.mark.parametrize("values", [
        [0] * 12,                       # never produced records
        [0] * 9 + [1, 1],               # two active scans are not a habit
        [5] * 10 + [0],                 # two scans without records are not a silence yet
    ])
    def test_no_alert_without_an_established_source_or_a_long_enough_silence(self, values):
        history = _history({"mlh": values})
        current = scan_record(_report({"mlh": 0}), scan_id="gh-x", commit="")
        assert detect_alerts(history, current) == []

    def test_disabled_integrations_are_not_silent_sources(self):
        history = _history({"reddit": [4] * 10 + [0, 0]})
        current = scan_record(_report({"reddit": 0}), scan_id="gh-x", commit="")
        current["sources"]["reddit"]["status"] = "disabled"
        assert detect_alerts(history, current) == []

    def test_volume_drop_against_the_recent_median(self):
        history = [scan_record(_report({"luma": 3}, raw=raw), scan_id=str(raw), commit="")
                   for raw in (460, 440, 470, 455, 480)]
        low = scan_record(_report({"luma": 3}, raw=200), scan_id="low", commit="")
        normal = scan_record(_report({"luma": 3}, raw=300), scan_id="ok", commit="")

        assert detect_alerts(history, low) == [
            {"kind": "volume_drop", "raw": 200, "median": 460, "new": True, "reminder": False},
        ]
        assert detect_alerts(history, normal) == []
        assert detect_alerts(history[:4], low) == []  # too little history

    def test_classifier_fallback_and_errors(self):
        current = scan_record(_report({"luma": 3}), scan_id="gh-x", commit="", classifier={
            "primary_model": "openai/gpt-oss-120b", "fallback_calls": 2, "failed_calls": 1, "errors": 5,
            "models": {"openai/gpt-oss-120b": {"calls": 7}, "qwen/qwen3.8-27b": {"calls": 2}},
        })
        alerts = detect_alerts([], current)
        assert alerts == [
            {"kind": "classifier_fallback", "calls": 2, "models": ["qwen/qwen3.8-27b"],
             "new": True, "reminder": False},
            {"kind": "classifier_errors", "failed_calls": 1, "errors": 5, "new": True, "reminder": False},
        ]
        assert alert_message(alerts[0]).startswith("qwen/qwen3.8-27b ha risposto a 2 chiamate")


class TestPersistence:
    def test_record_scan_appends_one_line_and_skips_unreadable_ones(self, tmp_path):
        path = tmp_path / "metrics" / "scans.jsonl"
        path.parent.mkdir()
        path.write_text("not json\n", encoding="utf-8")

        record, alerts = record_scan(_report({"luma": 3}), scan_id="gh-1", commit="abc",
                                     classifier=None, path=path)
        record_scan(_report({"luma": 3}), scan_id="gh-2", commit="abc", classifier=None,
                    path=path, persist=False)

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2 and json.loads(lines[1])["scan_id"] == "gh-1"
        assert record["alerts"] == [] and alerts == []
        assert [item["scan_id"] for item in scan_metrics.load_history(path)] == ["gh-1"]

    def test_retry_preserves_the_first_record_without_extending_a_silence(self, tmp_path):
        path = tmp_path / "scans.jsonl"
        history = _history({"luma": [3, 3, 3, 0]})
        path.write_text("".join(json.dumps(record) + "\n" for record in history), encoding="utf-8")
        first = record_scan(_report({"luma": 0}), scan_id="gh-retry", commit="abc",
                            classifier=None, path=path)
        saved = path.read_bytes()

        retry = record_scan(_report({"luma": 0}, raw=200), scan_id="gh-retry", commit="changed",
                            classifier=None, path=path)

        assert retry == first and retry[1] == []
        assert path.read_bytes() == saved
        _, alerts = record_scan(_report({"luma": 0}), scan_id="gh-next", commit="abc",
                                classifier=None, path=path)
        assert len(scan_metrics.load_history(path)) == 6
        assert len(alerts) == 1 and alerts[0]["scans"] == 3 and alerts[0]["new"] is True

    def test_only_notable_alerts_become_workflow_annotations(self, monkeypatch, capsys, caplog):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        caplog.set_level("INFO", logger="utils.scan_metrics")
        silent = {"kind": "source_silent", "source": "codemotion", "status": "empty",
                  "scans": 12, "usual_events": 4}
        scan_metrics.emit_alerts([
            {"kind": "volume_drop", "raw": 100, "median": 450, "new": True},
            {**silent, "new": False, "reminder": False},
            {**silent, "source": "camera_commercio", "new": False, "reminder": True},
            {"kind": "source_recovered", "source": "taikai", "events": 6, "scans": 5, "new": True},
        ])
        assert capsys.readouterr().out.splitlines() == [
            "::warning title=Calo degli eventi raccolti::100 eventi raccolti, meno della metà "
            "della mediana delle scansioni precedenti (450)",
            "::warning title=Fonte ferma (promemoria)::camera_commercio: nessun evento da 12 "
            "scansioni (prima di solito 4; stato empty)",
            "::notice title=Fonte tornata::taikai è tornata: 6 eventi dopo 5 scansioni senza risultati",
        ]
        assert "Avviso già segnalato: codemotion" in caplog.text


class TestTelegramAlerts:
    def test_summary_details_new_alerts_and_names_known_ones(self):
        silent = {"kind": "source_silent", "status": "blocked", "usual_events": 29}
        text = _format_run_summary(0, 3, 65, [], [], 28, 28, alerts=[
            {**silent, "source": "regione_lombardia", "scans": 3, "new": True, "reminder": False},
            {**silent, "source": "camera_commercio", "scans": 9, "new": False, "reminder": False},
            {**silent, "source": "codemotion", "scans": 10, "new": False, "reminder": True},
            {"kind": "source_recovered", "source": "taikai", "events": 6, "scans": 5,
             "new": True, "reminder": False},
            {"kind": "classifier_fallback", "calls": 1, "models": ["m"], "new": False, "reminder": False},
        ])
        assert "<b>Avvisi</b>" in text
        assert "🆕 regione_lombardia: nessun evento da 3 scansioni" in text
        assert "🔁 codemotion: nessun evento da 10 scansioni" in text
        assert "✅ taikai è tornata: 6 eventi dopo 5 scansioni" in text
        assert "Ancora attivi, già segnalati: camera_commercio, modello di riserva" in text
        assert "camera_commercio: nessun evento" not in text

    def test_no_section_without_alerts(self):
        assert "Avvisi" not in _format_run_summary(0, 3, 65, [], [], 28, 28, alerts=[])

    def test_contract_failure_is_an_interrupted_scan(self):
        text = _format_run_summary(0, 3, 65, [], [], scan_status="contract_failed_preserved",
                                   contract_violations=["evento #0 'X': 30 URL alternativi (limite 25)"])
        assert "Scansione non completata" in text and "contratti sui dati" in text
        assert "30 URL alternativi" in text


def _groq_response(content: str, prompt_tokens: int, completion_tokens: int):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


class TestClassifierUsageAndProvenance:
    @pytest.fixture(autouse=True)
    def fresh_usage(self):
        llm_filter.reset_usage()
        yield
        llm_filter.reset_usage()

    @patch("filters.llm_filter.time.sleep")
    @patch("filters.llm_filter._get_groq_client")
    def test_usage_counts_tokens_retries_and_fallback(self, mock_client, _sleep, monkeypatch):
        monkeypatch.setattr(config, "LLM_MODEL", "primary-model")
        monkeypatch.setattr(config, "LLM_MODEL_FALLBACKS", ["fallback-model"])
        monkeypatch.setattr(config, "LLM_RETRY_MAX", 2)
        create = mock_client.return_value.chat.completions.create
        create.side_effect = [
            _groq_response("{}", 3000, 200),
            Exception("Error code: 429 rate_limit_exceeded"),
            Exception("model not found"),
            _groq_response("{}", 2900, 150),
        ]

        llm_filter._call_llm("sys", "user")
        llm_filter._call_llm("sys", "user")
        summary = llm_filter.usage_summary()

        assert summary["primary_model"] == "primary-model"
        assert summary["models"]["primary-model"]["calls"] == 1
        assert summary["models"]["primary-model"]["prompt_tokens"] == 3000
        assert summary["models"]["fallback-model"]["completion_tokens"] == 150
        assert summary["fallback_calls"] == 1 and summary["rate_limit_retries"] == 1
        assert summary["failed_calls"] == 0
        assert summary["prompt_version"] == llm_filter.prompt_version()

    @patch("filters.llm_filter.time.sleep")
    def test_classified_events_carry_model_prompt_and_commit(self, _sleep, monkeypatch):
        monkeypatch.setattr(config, "GROQ_API_KEY", "fixture")
        monkeypatch.setattr("filters.llm_filter.pipeline_commit", lambda: "c0ffee")

        def answer(system_prompt, user_prompt):
            llm_filter._usage.last_model = "openai/gpt-oss-120b"
            return json.dumps({"results": [{"index": 0, "status": "confirmed", "is_hackathon": True,
                                            "confidence": 0.95, "reason": "ok"}]})

        event = HackathonEvent(title="PoliHack", url="https://example.com/polihack", source="test")
        with patch("filters.llm_filter._call_llm", side_effect=answer):
            confirmed, _ = llm_filter.llm_filter([event])

        assert confirmed == [event]
        assert event.provenance["model"] == "openai/gpt-oss-120b"
        assert event.provenance["prompt_version"] == llm_filter.prompt_version()
        assert event.provenance["pipeline_commit"] == "c0ffee"
        assert event.to_dict()["provenance"]["classified_at"].endswith("+00:00")

    def test_failed_classification_names_no_model(self, monkeypatch):
        monkeypatch.setattr(config, "GROQ_API_KEY", "fixture")
        llm_filter._usage.last_model = "stale-model"
        event = HackathonEvent(title="Hack", url="https://example.com/hack", source="test")
        with patch("filters.llm_filter._call_llm", return_value=""):
            llm_filter.llm_filter([event])
        assert event.classification_status == "error" and event.provenance["model"] == ""

    def test_prompt_version_follows_the_prompt_text(self, monkeypatch):
        before = llm_filter.prompt_version()
        monkeypatch.setattr(llm_filter, "_SYSTEM_PROMPT_TEMPLATE",
                            llm_filter._SYSTEM_PROMPT_TEMPLATE + "\nNuova regola.")
        llm_filter.prompt_version.cache_clear()
        try:
            assert llm_filter.prompt_version() != before
        finally:
            monkeypatch.undo()
            llm_filter.prompt_version.cache_clear()
        assert llm_filter.prompt_version() == before

    def test_events_without_provenance_keep_their_previous_shape(self):
        event = HackathonEvent(title="Hack", url="https://example.com/hack", source="test")
        assert "provenance" not in event.to_dict()


@pytest.mark.parametrize("dry_run", [False, True])
@patch("main.notify_run_summary")
@patch("main.get_collectors", return_value=["s"])
@patch("main.generate_readme_table")
@patch("main.generate_html")
@patch("main.llm_dedup", side_effect=lambda events: events)
@patch("main.llm_filter")
@patch("main.keyword_filter_batch")
@patch("main.run_collectors")
@patch("main.EventStore")
def test_pipeline_appends_one_metrics_line_per_scan(
    MockStore, mock_run_coll, mock_kw, mock_llm, _dedup, _html, _readme, _collectors, mock_notify,
    tmp_path, dry_run,
):
    from main import run_pipeline

    store = MagicMock(count=0)
    store.all_events.return_value = []
    store.is_duplicate.return_value = False
    MockStore.return_value = store
    events = [HackathonEvent(title="Hack", url="https://a.com/1", source="s",
                             date_str="2030-11-20", date_source="event")]
    mock_run_coll.return_value = (events, ["s"], [], [
        {"name": "s", "ok": True, "event_count": 1, "status": "healthy", "issues": []},
    ])
    mock_kw.return_value = (events, 0)
    mock_llm.return_value = (events, 0)

    with (
        patch("main.config.DATA_DIR", tmp_path),
        patch("main.config.REVIEW_QUEUE_FILE", tmp_path / "review_queue.json"),
        patch("main.config.REVIEW_DECISIONS_FILE", tmp_path / "review_decisions.json"),
    ):
        run_pipeline(dry_run=dry_run)

    metrics = scan_metrics.metrics_path()
    report = json.loads((tmp_path / "last_report.json").read_text())
    assert report["alerts"] == [] and report["classifier"]["errors"] == 0
    assert report["scan_id"] and "duration_seconds" in report
    if dry_run:
        assert not metrics.exists()
        return
    [line] = metrics.read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["scan_id"] == report["scan_id"] and record["status"] == "completed"
    assert record["counts"]["published"] == 1 and record["sources"]["s"]["events"] == 1
    assert mock_notify.call_args.kwargs["alerts"] == []


@pytest.fixture
def pipeline(tmp_path):
    """run_pipeline with one healthy source, one new event and files under tmp_path."""
    events = [HackathonEvent(title="Hack riservato", url="https://a.com/1", source="s",
                             date_str="2030-11-20", date_source="event")]
    store = MagicMock(count=0)
    store.all_events.return_value = []
    store.is_duplicate.return_value = False
    with ExitStack() as stack:
        def enter(target, **options):
            return stack.enter_context(patch(target, **options))

        mocks = SimpleNamespace(store=store, tmp_path=tmp_path)
        enter("main.EventStore", return_value=store)
        mocks.run_collectors = enter("main.run_collectors", return_value=(events, ["s"], [], [
            {"name": "s", "ok": True, "event_count": 1, "status": "healthy", "issues": []},
        ]))
        enter("main.keyword_filter_batch", return_value=(events, 0))
        enter("main.llm_filter", return_value=(events, 0))
        enter("main.llm_dedup", side_effect=lambda items: items)
        enter("main.generate_html")
        enter("main.generate_readme_table")
        enter("main.get_collectors", return_value=["s"])
        mocks.notify = enter("main.notify_run_summary")
        enter("main.config.DATA_DIR", new=tmp_path)
        enter("main.config.REVIEW_QUEUE_FILE", new=tmp_path / "review_queue.json")
        enter("main.config.REVIEW_DECISIONS_FILE", new=tmp_path / "review_decisions.json")
        yield mocks


def _metrics_lines() -> list[dict]:
    return [json.loads(line) for line in
            scan_metrics.metrics_path().read_text(encoding="utf-8").splitlines()]


class TestInterruptedScans:
    def test_a_crash_records_its_scan_and_propagates(self, pipeline):
        from main import run_pipeline

        pipeline.run_collectors.side_effect = RuntimeError("boom on 'Hack riservato'")
        with pytest.raises(RuntimeError):
            run_pipeline()

        [record] = _metrics_lines()
        assert record["status"] == "crashed" and record["error"] == "RuntimeError"
        assert record["counts"]["raw"] is None and record["sources"] == {}
        report_text = (pipeline.tmp_path / "last_report.json").read_text()
        assert json.loads(report_text)["status"] == "crashed"
        assert "Hack riservato" not in report_text  # only the type is public

    def test_the_archive_is_saved_before_the_scan_is_recorded(self, pipeline):
        """A failed save leaves a `crashed` line, never a `completed` one."""
        from main import run_pipeline

        pipeline.store.save_with_timestamp.side_effect = OSError("disk full")
        with pytest.raises(OSError):
            run_pipeline()

        assert [(item["status"], item.get("error")) for item in _metrics_lines()] == [("crashed", "OSError")]
        assert not (pipeline.tmp_path / "review_queue.json").exists()

    def test_a_failure_after_the_outcome_adds_no_second_line(self, pipeline):
        from main import run_pipeline

        pipeline.notify.side_effect = RuntimeError("telegram")
        with pytest.raises(RuntimeError):
            run_pipeline()
        assert [item["status"] for item in _metrics_lines()] == ["completed"]

    def test_a_cut_line_does_not_swallow_the_next_one(self, tmp_path):
        path = tmp_path / "scans.jsonl"
        path.write_text('{"scan_id":"gh-1"}\n{"scan_id":"gh-2","sta', encoding="utf-8")
        scan_metrics.append_record({"scan_id": "gh-3"}, path)
        assert [item["scan_id"] for item in scan_metrics.load_history(path)] == ["gh-1", "gh-3"]


def test_an_unreadable_archive_stops_the_scan_before_collecting(tmp_path, monkeypatch, capsys):
    import main

    archive = tmp_path / "events.json"
    archive.write_text('{"events": [', encoding="utf-8")
    monkeypatch.setattr(main.config, "EVENTS_FILE", archive)
    monkeypatch.setattr(main.config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main.config, "REVIEW_QUEUE_FILE", tmp_path / "review_queue.json")
    monkeypatch.setattr(main.config, "REVIEW_DECISIONS_FILE", tmp_path / "review_decisions.json")
    monkeypatch.setattr("sys.argv", ["main.py"])
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    collectors = MagicMock()
    monkeypatch.setattr(main, "run_collectors", collectors)

    with pytest.raises(SystemExit) as exited:
        main.main()

    assert exited.value.code == 1 and not collectors.called
    assert archive.read_text(encoding="utf-8") == '{"events": ['
    [record] = _metrics_lines()
    assert record["status"] == "crashed" and record["error"] == "CorruptDataFile"
    report = json.loads((tmp_path / "last_report.json").read_text())
    assert "events.json non leggibile" in report["error_detail"]
    assert "::error title=File di dati non leggibile::events.json non leggibile" in capsys.readouterr().out


@pytest.mark.parametrize("failed_step, scan_outcome, expected", [
    (None, "success", False),
    ("scan", "failure", True),
    ("SSG", "success", True),
    ("upload", "success", True),
    ("tests", "skipped", False),
    (None, "cancelled", False),
])
def test_workflow_preserves_only_metrics_after_scan_or_later_failure(failed_step, scan_outcome, expected):
    workflow = (scan_metrics.Path(__file__).resolve().parents[1]
                / ".github" / "workflows" / "check_hackathons.yml").read_text(encoding="utf-8")
    steps = {block.split("\n", 1)[0].strip(): block for block in workflow.split("- name: ")[1:]}
    fallback = steps["Commit metrics after a failed run"]
    condition = next(line.strip()[4:] for line in fallback.splitlines() if line.strip().startswith("if: "))
    # Evaluate the boolean subset used by this workflow against failure scenarios.
    expression = (condition.replace("failure()", "had_failure")
                  .replace("steps.scan.outcome", "scan_outcome")
                  .replace("&&", " and ").replace("||", " or "))
    assert eval(expression, {"__builtins__": {}}, {
        "had_failure": failed_step is not None, "scan_outcome": scan_outcome,
    }) is expected
    assert fallback.rstrip().endswith("file_pattern: data/metrics/scans.jsonl")
    assert "id: scan" in steps["Run Hackathon Monitor"]
    assert "if:" not in steps["Commit updated data and page"]  # any failure skips data publication
    names = list(steps)
    assert names.index("Upload run report") < names.index("Commit metrics after a failed run")
    assert names.index("Commit metrics after a failed run") < names.index("Commit updated data and page")
