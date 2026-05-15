"""
Collector InnovUp — scraping HTML del sito dell'associazione startup italiana.

URL: https://innovup.net/eventi/
Sito HTML statico, nessun JS rendering necessario.
Ottima copertura per hackathon corporate e istituzionali italiani.
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

INNOVUP_URL = "https://innovup.net/eventi/"


class InnovUpCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "innovup"

    def collect(self) -> list[HackathonEvent]:
        response = safe_get(INNOVUP_URL)
        if response is None:
            logger.error("InnovUp: impossibile raggiungere %s", INNOVUP_URL)
            return []

        events = self._parse_html(response.text)
        logger.info("InnovUp: trovati %d eventi", len(events))
        return events

    def _parse_html(self, html: str) -> list[HackathonEvent]:
        """Parsa la pagina eventi di InnovUp."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # InnovUp usa card/article per gli eventi
        # Cerchiamo strutture comuni: article, div con classe event, ecc.
        articles = soup.find_all("article")
        if not articles:
            # Fallback: cerca div con classi comuni per eventi
            articles = soup.find_all("div", class_=lambda c: c and ("event" in c.lower() if isinstance(c, str) else any("event" in x.lower() for x in c)))

        if not articles:
            # Fallback generico: cerca tutti i link con testo che potrebbe essere un evento
            articles = soup.find_all("div", class_=lambda c: c and ("post" in str(c).lower() or "card" in str(c).lower()))

        for article in articles:
            event = self._parse_article(article)
            if event:
                events.append(event)

        # Se nessun article trovato, prova a estrarre dai link della pagina
        if not events:
            events = self._fallback_link_extraction(soup)

        return events

    @staticmethod
    def _is_valid_title(title: str) -> bool:
        """Controlla che il titolo sia un vero titolo evento (non paginazione o navigazione)."""
        if not title or len(title) < 5:
            return False
        # Escludi numeri puri (paginazione), date nude, ecc.
        stripped = title.strip().replace("-", "").replace(" ", "")
        if stripped.isdigit():
            return False
        # Escludi titoli generici di navigazione
        skip = {"next", "prev", "previous", "page", "paginazione", "leggi tutto",
                "read more", "scopri", "vedi tutti", "load more", "mostra altro"}
        if title.strip().lower() in skip:
            return False
        return True

    def _parse_article(self, article) -> HackathonEvent | None:
        """Estrae un evento da un elemento article/div."""
        try:
            # Titolo: cerca h2, h3, h4 o link principale
            title_el = article.find(["h2", "h3", "h4"])
            if not title_el:
                link = article.find("a")
                if link:
                    title_el = link

            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not self._is_valid_title(title):
                return None

            # URL
            link = title_el.find("a") if title_el.name != "a" else title_el
            if not link:
                link = article.find("a")
            url = link.get("href", "") if link else ""

            if not url:
                return None
            if url.startswith("/"):
                url = f"https://innovup.net{url}"

            # Data: cerca elementi con classe date, time, o tag time
            date_str = ""
            time_el = article.find("time")
            if time_el:
                date_str = time_el.get("datetime", "") or time_el.get_text(strip=True)
            else:
                date_el = article.find(class_=lambda c: c and "date" in str(c).lower())
                if date_el:
                    date_str = date_el.get_text(strip=True)

            # Descrizione: testo del paragrafo o excerpt
            desc_el = article.find("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description[:500],
                date_str=date_str,
                location="",
            )

        except Exception as e:
            logger.debug("Errore parsing article InnovUp: %s", e)
            return None

    def _fallback_link_extraction(self, soup: BeautifulSoup) -> list[HackathonEvent]:
        """Fallback: estrae eventi dai link della pagina."""
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if not text or len(text) < 5:
                continue
            if href in seen:
                continue

            # Filtra link che sembrano eventi (contengono /eventi/ o /event/)
            if "/event" in href.lower() and href != INNOVUP_URL:
                if not self._is_valid_title(text):
                    continue
                seen.add(href)
                if href.startswith("/"):
                    href = f"https://innovup.net{href}"

                events.append(HackathonEvent(
                    title=text,
                    url=href,
                    source=self.name,
                    location="",
                ))

        return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = InnovUpCollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}] {e.title} — {e.url}")
