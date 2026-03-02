"""
Collector Reddit — ricerca hackathon su subreddit italiani via PRAW.

Subreddit monitorati:
- r/ItalyInformatica (~48k membri, community developer italiana)
- r/italy (community italiana generale)

Copertura bassa ma complementare — cattura annunci che non appaiono altrove.

Se praw non è installato o Reddit non è configurato, il collector viene saltato
senza far fallire la pipeline.
"""

import logging

try:
    import praw
    from prawcore.exceptions import PrawcoreException
    _PRAW_AVAILABLE = True
except ImportError as e:
    praw = None
    PrawcoreException = None
    _PRAW_AVAILABLE = False
    _PRAW_IMPORT_ERROR = e

import config
from models import BaseCollector, HackathonEvent

logger = logging.getLogger(__name__)

SUBREDDITS = ["ItalyInformatica", "italy"]
SEARCH_QUERIES = ["hackathon", "hackathon Milano", "hackathon Milan"]
SEARCH_TIME_FILTER = "month"  # Ultimi 30 giorni
MAX_RESULTS_PER_QUERY = 25


class RedditCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "reddit"

    def collect(self) -> list[HackathonEvent]:
        if not _PRAW_AVAILABLE:
            logger.warning(
                "Reddit collector disattivato: praw non installato (%s). "
                "Esegui: pip install praw",
                getattr(_PRAW_IMPORT_ERROR, "msg", _PRAW_IMPORT_ERROR),
            )
            return []
        if not config.REDDIT_CLIENT_ID or not config.REDDIT_CLIENT_SECRET:
            logger.warning("Reddit non configurato (manca CLIENT_ID o CLIENT_SECRET) — skip")
            return []

        try:
            reddit = praw.Reddit(
                client_id=config.REDDIT_CLIENT_ID,
                client_secret=config.REDDIT_CLIENT_SECRET,
                user_agent="hackathon-monitor/1.0 (by /u/hackathon-bot)",
            )
        except PrawcoreException as e:
            logger.error("Errore inizializzazione Reddit: %s", e)
            return []

        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for subreddit_name in SUBREDDITS:
            try:
                events = self._search_subreddit(reddit, subreddit_name, seen_urls)
                all_events.extend(events)
            except Exception as e:
                logger.error("Reddit r/%s fallito: %s", subreddit_name, e)

        logger.info("Reddit: trovati %d post rilevanti", len(all_events))
        return all_events

    def _search_subreddit(
        self, reddit: praw.Reddit, subreddit_name: str, seen_urls: set[str]
    ) -> list[HackathonEvent]:
        """Cerca hackathon in un subreddit specifico."""
        events: list[HackathonEvent] = []
        subreddit = reddit.subreddit(subreddit_name)

        for query in SEARCH_QUERIES:
            try:
                results = subreddit.search(
                    query,
                    sort="new",
                    time_filter=SEARCH_TIME_FILTER,
                    limit=MAX_RESULTS_PER_QUERY,
                )

                for submission in results:
                    url = submission.url
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    # Se il link è un post Reddit (self-post), usa il permalink
                    if "reddit.com" in url:
                        url = f"https://www.reddit.com{submission.permalink}"

                    title = submission.title.strip()
                    if not title:
                        continue

                    # Descrizione dal selftext o dal titolo
                    description = ""
                    if submission.selftext:
                        description = submission.selftext[:500]

                    events.append(HackathonEvent(
                        title=title,
                        url=url,
                        source=f"reddit/r/{subreddit_name}",
                        description=description,
                        date_str="",
                        location=config.SEARCH_LOCATION,
                    ))

            except Exception as e:
                logger.warning("Reddit search '%s' in r/%s: %s", query, subreddit_name, e)

        return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = RedditCollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}] {e.title} — {e.url}")
