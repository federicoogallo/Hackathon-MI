"""ChallengeRocket's public challenge catalogue (no account required)."""

import logging
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)
CHALLENGEROCKET_URLS = ["https://challengerocket.com/hackathons-and-challenges.html"]


class ChallengeRocketCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "challengerocket"

    def collect(self) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        seen: set[str] = set()
        for url in CHALLENGEROCKET_URLS:
            response = safe_get(url)
            if response is not None:
                events.extend(self._parse_html(response.text, seen))
        logger.info("ChallengeRocket: trovati %d candidati", len(events))
        return events

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(".challenge-card")
        if not cards:
            record_issue("parse_error", "challenge catalogue cards missing", CHALLENGEROCKET_URLS[0])
        return [event for card in cards if (event := self._parse_card(card, seen_urls))]

    def _parse_card(self, card, seen_urls: set[str]) -> HackathonEvent | None:
        title_el = card.select_one(".challenge-card__title a[href]")
        if title_el is None:
            return None
        title = title_el.get_text(" ", strip=True)
        url = urljoin(CHALLENGEROCKET_URLS[0], title_el["href"])
        if not title or url in seen_urls or urlsplit(url).hostname != "challengerocket.com":
            return None
        features = {}
        for row in card.select(".challenge-card__feature-list-item"):
            label = row.select_one(".challenge-card__feature-list-label")
            value = row.select_one(".challenge-card__feature-list-value")
            if label and value:
                features[label.get_text(" ", strip=True).lower()] = value.get_text(" ", strip=True)
        category = features.get("category", "")
        # The catalogue also contains jobs and two-minute recruiting quizzes.
        if "hackathon" not in f"{title} {category}".lower() and "creative challenge" not in category.lower():
            return None
        seen_urls.add(url)
        return HackathonEvent(
            title=title, url=url, source=self.name,
            description=category,
            location="Online" if "online" in category.lower() else features.get("location", ""),
        )
