from pathlib import Path

from main import _passes_quality_gate
from models import HackathonEvent
from utils.admin_audit import (
    admin_regression_cases,
    event_from_admin_action,
    load_admin_actions,
    record_admin_action,
)


def test_admin_action_log_roundtrip(tmp_path: Path):
    path = tmp_path / "admin_actions.json"
    event = HackathonEvent(
        title="Remote Game Jam",
        url="https://itch.io/jam/remote-game-jam",
        source="test",
        description="Online game jam on Discord.",
        date_str="2026-08-01",
        location="Online",
        is_hackathon=True,
        confidence=0.9,
    )

    recorded = record_admin_action(
        "removed",
        event,
        reason="Online only",
        reason_code="online_only",
        regression=True,
        path=path,
    )

    assert recorded["expected"] == "reject"
    assert recorded["reason"] == "Online only"
    assert recorded["reason_code"] == "online_only"
    assert load_admin_actions(path)[0]["title"] == "Remote Game Jam"
    assert admin_regression_cases(path)[0]["id"] == recorded["id"]


def test_admin_regression_case_can_drive_quality_gate(tmp_path: Path):
    path = tmp_path / "admin_actions.json"
    event = HackathonEvent(
        title="Remote Game Jam",
        url="https://itch.io/jam/remote-game-jam",
        source="test",
        description="Online game jam on Discord.",
        date_str="2026-08-01",
        location="Online",
        is_hackathon=True,
        confidence=0.9,
    )

    record_admin_action(
        "removed",
        event,
        reason="Online only",
        reason_code="online_only",
        regression=True,
        path=path,
    )

    [case] = admin_regression_cases(path)
    ok, reason = _passes_quality_gate(event_from_admin_action(case))

    assert ok is False
    assert "online" in reason
