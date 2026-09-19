"""Edition-specific exclusions verified from event pages or manual reports.

Keep these rules shared by ingestion and stored-event cleanup. Match parsed URL
components so tracking parameters and host aliases cannot revive an excluded
event, while other editions and registration IDs remain eligible.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlsplit


_HARVARD_PATHS = {
    "/knowledge/harvard-hsil-hackathon-2026",
    "/en/knowledge/harvard-hsil-hackathon-2026",
}
_MILAN_AI_WEEK_PATH = "/ai-hackathons/milan-ai-week-hackathon"
_GDG_PATH = (
    "/events/details/google-gdg-on-campus-polytechnic-university-of-milan-"
    "presents-gdg-ai-hack-2026"
)
_POLIMI_CONFERENCE_PATH = (
    "/il-politecnico/eventi/dettaglio-evento/innovation-challenge-2026-"
    "soluzioni-per-evitare-la-disillusione-dellai"
)
_BCG_CANDIDATE_PATHS = {
    "/events/candidate/landing",
    "/events/candidate/registration",
}
_AI_OLYMPICS_EVENTBRITE_PATH = re.compile(r"/e/(?:[^/]*-)?1987936520647")


def event_exclusion_reason(url: str) -> str | None:
    """Return the reason for a known exclusion, independent of extracted dates."""
    try:
        parsed = urlsplit((url or "").strip())
        host = (parsed.hostname or "").lower().removeprefix("www.")
        path = unquote(parsed.path).rstrip("/").lower()
    except ValueError:
        return None

    # Harvard HSIL: 10–11 April 2026. GDG AI HACK: 8–10 May 2026.
    if host == "gsom.polimi.it" and path in _HARVARD_PATHS:
        return "evento passato noto (Harvard HSIL, 10–11 aprile 2026)"
    if host == "gdg.community.dev" and path == _GDG_PATH:
        return "evento passato noto (GDG AI HACK, 8–10 maggio 2026)"

    # These are aliases and project subpages of AI Agent Olympics, 19–20 May 2026.
    if (
        host in {"lu.ma", "luma.com"} and path == "/5fxlxfl5"
        or host == "lablab.ai" and (
            path == _MILAN_AI_WEEK_PATH or path.startswith(_MILAN_AI_WEEK_PATH + "/")
        )
        or host in {"eventbrite.com", "eventbrite.it"}
        and _AI_OLYMPICS_EVENTBRITE_PATH.fullmatch(path)
    ):
        return "evento passato noto (AI Agent Olympics, 19–20 maggio 2026)"

    if host in {"bcg.eightfold.ai", "experiencedtalent.bcg.com"} and path in _BCG_CANDIDATE_PATHS:
        event_ids = parse_qs(parsed.query).get("plannedEventId", [])
        if "aQnm026Vg" in event_ids:
            return "duplicato noto (pagina ufficiale: bcgplatinion.com/hackathon)"

    # The official 21 September 2026 page labels this event as "Convegni".
    if host == "polimi.it" and path == _POLIMI_CONFERENCE_PATH:
        return "convegno, non hackathon (Innovation Challenge 2026)"

    return None
