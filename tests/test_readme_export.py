"""README and the website must agree on reviewed event facts and exclusions."""

import json
from datetime import date

import pytest

from utils.readme_export import TABLE_END, TABLE_START, generate_readme_table


@pytest.fixture
def export(tmp_path, monkeypatch):
    monkeypatch.setattr("utils.readme_export._today_rome", lambda: date(2026, 10, 10))

    def run(events, details=(), exclusions=(), *, as_mapping=False):
        readme = tmp_path / "README.md"
        readme.write_text(f"# Manual introduction\n\n{TABLE_START}\nold\n{TABLE_END}\n\n## New manual section\nKeep this exact text.\n")
        events_file = tmp_path / "events.json"
        records = {str(i): event for i, event in enumerate(events)} if as_mapping else events
        events_file.write_text(json.dumps({"events": records}))
        details_file = tmp_path / "event_details.json"
        details_file.write_text(json.dumps(list(details)))
        exclusions_file = tmp_path / "event_exclusions.json"
        exclusions_file.write_text(json.dumps(list(exclusions)))
        original_data = [path.read_bytes() for path in (events_file, details_file, exclusions_file)]

        generate_readme_table(events_file, readme, details_path=details_file, exclusions_path=exclusions_file)

        assert [path.read_bytes() for path in (events_file, details_file, exclusions_file)] == original_data
        output = readme.read_text()
        assert output.startswith("# Manual introduction\n\n")
        assert output.endswith("\n\n## New manual section\nKeep this exact text.\n")
        return output

    return run


def _event(event_id="event", **overrides):
    return {"id": event_id, "title": f"Archived {event_id}", "url": f"https://example.com/{event_id}",
            "date_str": "2026-11-01", "location": "", "is_hackathon": True, "source": "web_search", **overrides}


def _facts(event_id="event", **overrides):
    return {"id": event_id, "title": f"Reviewed {event_id}", "url": f"https://example.com/official/{event_id}",
            "startDate": "2026-10-09", "endDate": "2026-10-10", "location": "Verified venue",
            "sourceLabel": "Official organizer", **overrides}


def test_reviewed_facts_override_archive_and_keep_event_until_its_end_date(export):
    output = export([_event(date_str="2025-01-01")], [_facts()])

    assert "**1 hackathon**" in output
    assert "[Reviewed event](https://example.com/official/event)" in output
    assert "| 9 Oct 2026 – 10 Oct 2026 | Verified venue | Official organizer |" in output
    assert "Archived event" not in output
    assert "2025" not in output


@pytest.mark.parametrize("as_mapping", [False, True])
def test_excluded_rejected_and_ended_events_are_removed(export, as_mapping):
    events = [
        _event("excluded"),
        _event("rejected", review_status="manual_rejected"),
        _event("ended"),
        _event("legacy-past", date_str="21settembre2026"),
        _event("live"),
    ]
    output = export(events, [_facts("ended", startDate="2026-10-08", endDate="2026-10-09")],
                    [{"id": "excluded"}], as_mapping=as_mapping)

    assert "**1 hackathon**" in output
    assert "Archived live" in output
    for name in ("excluded", "rejected", "ended", "legacy-past"):
        assert f"Archived {name}" not in output
        assert f"Reviewed {name}" not in output


def test_unreviewed_dates_and_empty_places_are_marked_to_verify(export):
    output = export([_event("unreviewed", date_str="2099-02-03")])

    assert "| To verify | To verify | Web search |" in output
    assert "2099" not in output
    assert "| Milano |" not in output


def test_reviewed_dates_sort_first_without_inventing_a_day_for_partial_dates(export):
    output = export([_event("unknown", date_str="November 2026"), _event("reviewed")],
                    [_facts("reviewed", startDate="2026-11-20", endDate="2026-11-20")])

    assert output.index("Reviewed reviewed") < output.index("Archived unknown")
    assert "| 20 Nov 2026 |" in output
    assert "| To verify |" in output
    assert "1 Nov 2026" not in output


def test_non_actionable_links_do_not_reappear_in_readme(export):
    output = export([_event("unsafe", url="javascript:alert(1)"),
                     _event("credentials", url="https://user:pass@example.com"),
                     _event("unconfirmed", is_hackathon=False)])

    assert "**0 hackathons**" in output
    assert "No upcoming hackathons" in output
    assert "Archived" not in output
