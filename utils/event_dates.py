"""Conservative event-date checks using source facts, never discovery/LLM dates.

Natural-language dates need an explicit year. Publication dates and application
deadlines are not event dates. Ambiguous evidence must be reviewed, not repaired
by assuming the current year. This does not replace structured date extraction.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from models import HackathonEvent


TemporalStatus = Literal["future", "past", "uncertain", "unknown"]
_MONTHS = {
    name: number
    for number, names in enumerate([
        "gennaio january jan", "febbraio february feb", "marzo march mar",
        "aprile april apr", "maggio may", "giugno june jun", "luglio july jul",
        "agosto august aug", "settembre september sept sep",
        "ottobre october oct", "novembre november nov", "dicembre december dec",
    ], 1)
    for name in names.split()
}
_MONTH = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\b\.?"
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_RANGE = r"\s*[-–—]\s*"
_NATURAL = re.compile(
    rf"\b(?:(?P<day>{_DAY})(?:{_RANGE}(?P<end_day>{_DAY}))?\s+(?P<month>{_MONTH})"
    rf"|(?P<month_first>{_MONTH})\s+(?P<first_day>{_DAY})(?:{_RANGE}(?P<first_end>{_DAY}))?)"
    r"(?:,?\s+(?P<year>20\d{2})\b)?", re.I,
)
_NUMERIC = re.compile(r"\b(?:(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})|(?P<d>\d{1,2})[/.](?P<m>\d{1,2})[/.](?P<y>20\d{2}))\b")
_SCHEDULE_CUE = re.compile(
    r"\b(?:save\s+the\s+date|(?:si\s+)?(?:svolge(?:rà)?|svolgerà|terrà|tenuto|tenuta)|"
    r"in\s+programma|avrà\s+luogo|take[sn]?\s+place|taking\s+place|be\s+held|was\s+held|"
    r"event\s+date|data\s+evento)\b", re.I,
)
_EVENT_CUE = re.compile(r"\b(?:hackathon|datathon|makeathon|buildathon|game\s+jam)\b", re.I)
_OTHER_CUE = re.compile(
    r"\b(?:published|posted|updated|pubblicat[oa]|aggiornat[oa]|deadline|"
    r"scadenza|applications?\s+(?:close|by|until)|register\s+by|"
    r"registration\s+(?:opens?|closes?|starts?|ends?)|"
    r"iscrizioni\s+(?:entro|fino)|candidature\s+(?:entro|fino))\b", re.I,
)


def _source_dates(text: str, *, event_field: bool = False, title: bool = False) -> list[date | None]:
    dates: list[date | None] = []
    for pattern in (_NATURAL, _NUMERIC):
        for match in pattern.finditer(text):
            if not event_field:
                # Only the nearest clause can identify what a date refers to.
                prefix = re.split(r"[.!?;\n]", text[:match.start()])[-1][-180:]
                cues = list(_EVENT_CUE.finditer(prefix))
                schedule = list(_SCHEDULE_CUE.finditer(prefix))
                other = list(_OTHER_CUE.finditer(prefix))
                if not title and not cues and not schedule:
                    continue
                if other and (not schedule or other[-1].start() > schedule[-1].start()):
                    continue
            parts = match.groupdict()
            year = parts.get("year") or parts.get("y")
            if not year:
                dates.append(None)
                continue
            if pattern is _NATURAL:
                month = _MONTHS[(parts.get("month") or parts["month_first"]).lower().rstrip(".")]
                day = parts.get("day") or parts["first_day"]
                end = parts.get("end_day") or parts.get("first_end") or day
                day, end = int(re.match(r"\d+", day)[0]), int(re.match(r"\d+", end)[0])
            else:
                month = int(parts.get("month") or parts["m"])
                day = end = int(parts.get("day") or parts["d"])
            try:
                start_date = date(int(year), month, day)
                end_date = date(int(year), month, end)
                dates.append(end_date if start_date <= end_date else None)
            except ValueError:
                dates.append(None)
    return dates


def event_temporal_status(event: HackathonEvent, ref_date: date) -> TemporalStatus:
    """Classify temporal evidence without mutating any source field.

    Structured event dates take precedence over incidental prose. Date ranges
    in an event-date field retain their last day. Conflicting prose dates and
    missing years are uncertain; unknown means no supported event-date signal.
    """
    if event.has_event_date:
        dates = _source_dates(event.date_str, event_field=True)
        if not dates:
            parsed = event.parsed_date()
            dates = [parsed] if parsed is not None else []
        if not dates:
            return "uncertain"
    else:
        dates = _source_dates(event.title, title=True)
        dates += _source_dates(event.description)
    if not dates:
        return "unknown"
    if None in dates:
        return "uncertain"
    is_past = {value < ref_date for value in dates}
    if len(is_past) != 1:
        return "uncertain"
    return "past" if True in is_past else "future"
