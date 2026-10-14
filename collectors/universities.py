"""
Collector Università Milanesi — scraping pagine eventi.

Copre:
- Politecnico di Milano
- Università Bocconi
- Università Bicocca
- Università Cattolica
- IULM
- Vita-Salute San Raffaele

Ogni università ha un sotto-parser indipendente in try/except,
così se un sito cambia struttura gli altri continuano a funzionare.
"""

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)


def _response_url(response, fallback: str) -> str:
    """Use the final page URL when a university redirects its event hub."""
    final_url = getattr(response, "url", None)
    return final_url if isinstance(final_url, str) and final_url else fallback


class UniversitiesCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "universities"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []

        parsers = [
            ("PoliMi", self._collect_polimi),
            ("Bocconi", self._collect_bocconi),
            ("Bicocca", self._collect_bicocca),
            ("Cattolica", self._collect_cattolica),
            ("IULM", self._collect_iulm),
            ("San Raffaele", self._collect_san_raffaele),
        ]

        for name, parser_fn in parsers:
            try:
                events = parser_fn()
                all_events.extend(events)
                logger.info("Università %s: trovati %d eventi", name, len(events))
            except Exception as e:
                logger.error("Università %s fallita: %s", name, e)
                record_issue("parse_error", f"University parser failed: {name}")

        return all_events

    # ─── Politecnico di Milano ──────────────────────────────────────────

    def _collect_polimi(self) -> list[HackathonEvent]:
        urls = [
            "https://www.polimi.it/il-politecnico/eventi",
        ]
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        for url in urls:
            response = safe_get(url)
            if response is None:
                continue
            events.extend(self._extract_events(
                response.text, _response_url(response, url), "polimi.it", "Politecnico di Milano", seen
            ))

        return events

    # ─── Università Bocconi ─────────────────────────────────────────────

    def _collect_bocconi(self) -> list[HackathonEvent]:
        urls = [
            "https://www.unibocconi.it/en/news-and-events-hub/events",
        ]
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        for url in urls:
            response = safe_get(url)
            if response is None:
                continue
            events.extend(self._extract_events(
                response.text, _response_url(response, url), "unibocconi.it", "Università Bocconi", seen
            ))

        return events

    # ─── Università Bicocca ─────────────────────────────────────────────

    def _collect_bicocca(self) -> list[HackathonEvent]:
        urls = [
            "https://www.unimib.it/eventi",
        ]
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        for url in urls:
            response = safe_get(url)
            if response is None:
                continue
            events.extend(self._extract_events(
                response.text, _response_url(response, url), "unimib.it", "Università Bicocca", seen
            ))

        return events

    # ─── Università Cattolica ────────────────────────────────────────────

    def _collect_cattolica(self) -> list[HackathonEvent]:
        urls = [
            "https://www.unicatt.it/eventi",
            "https://milano.unicatt.it/eventi",
        ]
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        for url in urls:
            response = safe_get(url)
            if response is None:
                continue
            events.extend(self._extract_events(
                response.text, _response_url(response, url), "unicatt.it", "Università Cattolica", seen
            ))

        return events

    # ─── IULM ───────────────────────────────────────────────────────────

    def _collect_iulm(self) -> list[HackathonEvent]:
        urls = [
            "https://www.iulm.it/it/news-ed-eventi/eventi",
        ]
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        for url in urls:
            response = safe_get(url)
            if response is None:
                continue
            events.extend(self._extract_events(
                response.text, _response_url(response, url), "iulm.it", "IULM", seen
            ))

        return events

    # ─── Vita-Salute San Raffaele ───────────────────────────────────────

    def _collect_san_raffaele(self) -> list[HackathonEvent]:
        urls = [
            "https://www.unisr.it/news?category=eventi",
        ]
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        for url in urls:
            response = safe_get(url)
            if response is None:
                continue
            events.extend(self._extract_events(
                response.text, _response_url(response, url), "unisr.it", "Uni Vita-Salute San Raffaele", seen
            ))

        return events

    # ─── Parser generico ────────────────────────────────────────────────

    def _extract_events(
        self, html: str, base_url: str, domain: str, organizer: str, seen: set[str]
    ) -> list[HackathonEvent]:
        """Parser generico che estrae eventi da una pagina universitaria."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        if domain == "unibocconi.it":
            return self._extract_bocconi_cards(soup, base_url, organizer, seen)
        if domain in {"polimi.it", "iulm.it", "unisr.it"}:
            return self._extract_current_cards(soup, base_url, domain, organizer, seen)

        # Cerca articoli, card, item di eventi
        containers = soup.find_all("article")
        if not containers:
            containers = soup.find_all(
                "div",
                class_=lambda c: c and any(
                    k in str(c).lower()
                    for k in ("event", "card", "news", "item", "listing")
                ),
            )

        for container in containers:
            try:
                title_el = container.find(["h2", "h3", "h4", "h5"])
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                # Escludi paginazione/navigazione
                stripped = title.strip().replace("-", "").replace(" ", "")
                if stripped.isdigit():
                    continue
                skip_titles = {"next", "prev", "previous", "paginazione", "leggi tutto",
                               "read more", "load more", "mostra altro", "vedi tutti"}
                if title.strip().lower() in skip_titles:
                    continue

                # URL
                link = container.find("a", href=True)
                href = link.get("href", "") if link else ""
                href = urljoin(base_url, href) if href else ""
                if not href or href in seen:
                    continue
                if urlparse(href).scheme not in {"http", "https"}:
                    continue
                seen.add(href)

                # Data
                date_str = ""
                time_el = container.find("time")
                if time_el:
                    date_str = time_el.get("datetime", "") or time_el.get_text(strip=True)
                else:
                    date_el = container.find(
                        class_=lambda c: c and "date" in str(c).lower()
                    )
                    if date_el:
                        date_str = date_el.get_text(strip=True)

                # Descrizione
                desc_el = container.find("p")
                description = desc_el.get_text(strip=True)[:500] if desc_el else ""

                events.append(HackathonEvent(
                    title=title,
                    url=href,
                    source=self.name,
                    description=description,
                    date_str=date_str,
                    location=config.SEARCH_LOCATION,
                    organizer=organizer,
                ))

            except Exception as e:
                logger.debug("Errore parsing container %s: %s", domain, e)
                continue

        return events

    def _extract_current_cards(
        self, soup, base_url: str, domain: str, organizer: str, seen: set[str]
    ) -> list[HackathonEvent]:
        """Read each university's event records, excluding navigation cards."""
        selectors = {
            "polimi.it": ".card--editorial-photo",
            "iulm.it": ".rigaevento[data-date]",
            "unisr.it": ".newscard figure[data-linkmanager-href]",
        }
        cards = soup.select(selectors[domain])
        if not cards:
            record_issue("parse_error", f"Unrecognized event listing: {domain}", base_url)
            return []
        events: list[HackathonEvent] = []
        for card in cards:
            if domain == "polimi.it":
                title_el = card.select_one(".card-title")
                link = card.select_one('a[href*="/dettaglio-evento/"]')
                href = link.get("href", "") if link else ""
                date_el = card.select_one(".card-body__date")
                desc_el = card.select_one(".card-text")
            elif domain == "iulm.it":
                title_el = card.select_one("h2 a[href]")
                href = title_el.get("href", "") if title_el else ""
                date_el = None
                desc_el = None
            else:
                title_el = card.select_one("h2")
                href = card.get("data-linkmanager-href", "")
                date_el = card.select_one("figcaption small")
                desc_el = card.select_one("p")
            title = title_el.get_text(" ", strip=True) if title_el else ""
            url = urljoin(base_url, href)
            parts = urlparse(url)
            host = parts.hostname or ""
            if (len(title) < 5 or not href or url in seen
                    or parts.scheme not in {"http", "https"}
                    or not (host == domain or host.endswith("." + domain))):
                continue
            date = (card.get("data-date", "") if domain == "iulm.it"
                    else date_el.get_text(" ", strip=True) if date_el else "")
            description = (card.get("data-abstract", "") if domain == "iulm.it"
                           else desc_el.get_text(" ", strip=True) if desc_el else "")
            # UniSR's news list displays publication dates, not event dates.
            editorial = domain == "unisr.it"
            seen.add(url)
            events.append(HackathonEvent(
                title=title, url=url, source=self.name, description=description[:500],
                date_str="" if editorial else date,
                published_at=date if editorial else "",
                date_source="publication" if editorial else "event_card",
                location="", organizer=organizer,
            ))
        return events

    def _extract_bocconi_cards(
        self, soup: BeautifulSoup, base_url: str, organizer: str, seen: set[str]
    ) -> list[HackathonEvent]:
        """Bocconi's cards have div titles; the outer article is the whole hub."""
        events: list[HackathonEvent] = []
        for card in soup.select("article.bds-component-event-card, article.bds-event-card-basic"):
            title_el = card.select_one(
                ".bds-component-event-card__title, .bds-event-card-basic__title"
            )
            link = card.find("a", href=True)
            if title_el is None or link is None:
                continue
            title = title_el.get_text(" ", strip=True)
            href = urljoin(base_url, link["href"])
            if not title or href in seen or urlparse(href).scheme not in {"http", "https"}:
                continue
            seen.add(href)
            date_el = card.select_one(
                ".bds-component-event-card__date-el, .bds-event-card-basic__date-el"
            )
            location_el = card.select_one(
                ".bds-component-event-card__location, .bds-event-card-basic__location"
            )
            abstract = card.select_one(".bds-event-card-basic__abstract, p")
            events.append(HackathonEvent(
                title=title,
                url=href,
                source=self.name,
                description=abstract.get_text(" ", strip=True)[:500] if abstract else "",
                date_str=date_el.get_text(" ", strip=True) if date_el else "",
                date_source="event_card" if date_el else "",
                location=location_el.get_text(" ", strip=True) if location_el else "",
                organizer=organizer,
            ))
        return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = UniversitiesCollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}/{e.organizer}] {e.title} — {e.url}")
