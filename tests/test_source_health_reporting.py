from unittest.mock import patch

import pytest
from ddgs.exceptions import DDGSException, TimeoutException, RatelimitException

from collectors.web_search import WebSearchCollector
from notifiers.telegram import _format_run_summary
from scripts.check_sources import probe
from utils.collector_health import record_issue, record_success, track_collector


@pytest.mark.parametrize("error,expected", [
    (DDGSException("No results found."), "empty"),
    (DDGSException("upstream unavailable"), "failed"),
    (TimeoutException("No results found."), "failed"),
    (RatelimitException("rate limited"), "failed"),
    (ValueError("No results found."), "failed"),
])
def test_empty_search_is_distinct_from_transport_failure(error, expected):
    with patch("ddgs.DDGS") as client, track_collector() as health:
        client.return_value.text.side_effect = error
        assert WebSearchCollector()._search("hackathon Milano", set()) == []
    assert health.outcome(0) == expected


@pytest.mark.parametrize("empty_result", [[], DDGSException("No results found.")])
def test_successful_search_followed_by_error_is_partial(empty_result):
    with patch("ddgs.DDGS") as client, track_collector() as health:
        client.return_value.text.side_effect = [empty_result, TimeoutException("timeout")]
        collector = WebSearchCollector()
        collector._search("first", set())
        collector._search("second", set())
    assert health.outcome(0) == "degraded"


def test_summary_separates_partial_blocked_failed_disabled_and_empty():
    runs = [dict(name=name, status=status) for name, status in [
        ("source", "healthy"), ("empty", "empty"), ("uni<one>", "degraded"),
        ("private", "blocked"), ("old", "failed"), ("optional", "disabled"),
    ]]
    text = _format_run_summary(0, 2, 30, ["uni<one>", "private", "old"], [],
                               collector_runs=runs, scan_status="degraded")
    assert "6 integrazioni" in text
    assert "1 con risultati · 1 senza risultati" in text
    assert "Parziali / da verificare (1): uni&lt;one&gt;" in text
    assert "Accesso bloccato (1): private" in text
    assert "In errore (1): old" in text
    assert "Disattivate (1): optional" in text
    assert "fonti operative" not in text
    assert "Non disponibili" not in text
    assert "Scansione con limitazioni" in text


@pytest.mark.parametrize("status", ["collection_failed_preserved", "llm_failed_preserved"])
def test_failed_scan_does_not_claim_no_new_events(status):
    text = _format_run_summary(0, 2, 30, [], [], scan_status=status)
    assert "Scansione non completata" in text
    assert "Archivio precedente preservato" in text
    assert "Nessun nuovo evento" not in text


def test_probe_does_not_classify_write_archive_or_notify():
    class Source:
        name = "sample"

    runs = [{"name": "sample", "status": "empty"}]
    with patch("scripts.check_sources.get_collectors", return_value=[Source()]), \
         patch("scripts.check_sources.run_collectors", return_value=([], ["sample"], [], runs)), \
         patch("main.EventStore") as store, patch("main.llm_filter") as classify, \
         patch("main.notify_run_summary") as notify:
        assert probe(["sample"])["collector_status_counts"] == {"empty": 1}
    store.assert_not_called()
    classify.assert_not_called()
    notify.assert_not_called()


def test_probe_rejects_unknown_sources_before_any_request():
    with patch("scripts.check_sources.run_collectors") as run:
        with pytest.raises(ValueError, match="Unknown sources"):
            probe(["not_a_source"])
    run.assert_not_called()


def test_browser_verification_http_200_is_blocked_when_no_records_available():
    with track_collector() as health:
        record_success()
        record_issue("blocked", "browser verification required")
    assert health.outcome(0) == "blocked"
    assert health.outcome(1) == "degraded"
