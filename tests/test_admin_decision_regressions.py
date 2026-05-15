import pytest

from filters.keyword_filter import keyword_filter
from main import _passes_quality_gate
from utils.admin_audit import admin_regression_cases, event_from_admin_action


DETERMINISTIC_REJECT_CODES = {
    "online_only",
    "not_milan",
    "past_or_finished",
    "missing_date_or_venue",
    "known_false_positive",
}


def _case_id(case: dict) -> str:
    if not isinstance(case, dict):
        return "no-admin-regressions"
    title = case.get("title") or "untitled"
    return f"{case.get('expected', 'review')}:{case.get('reason_code', 'other')}:{title[:40]}"


@pytest.mark.parametrize("case", admin_regression_cases(), ids=_case_id)
def test_admin_decision_regressions(case: dict):
    event = event_from_admin_action(case)
    expected = case.get("expected")
    quality_ok, reason = _passes_quality_gate(event)

    if expected == "publish":
        if "passato" in reason:
            pytest.skip("Approved event has aged out; keep it in the audit corpus.")
        assert quality_ok, reason
        return

    if expected == "reject":
        reason_code = case.get("reason_code")
        if reason_code not in DETERMINISTIC_REJECT_CODES:
            pytest.skip("This admin decision needs LLM/human semantics, not a hard filter.")
        keyword_ok = keyword_filter(event)
        assert not keyword_ok or not quality_ok
        return

    pytest.skip("Review/dismiss actions are audited but not hard regression assertions.")
