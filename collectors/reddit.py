"""Read-only Reddit discovery for existing approved API clients.

Reddit is migrating public Data API applications to its Developer Platform.
No anonymous RSS fallback is used: Reddit is ending RSS support in November 2026.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit

try:
    import praw
    _PRAW_AVAILABLE = True
except ImportError:
    praw = None
    _PRAW_AVAILABLE = False

import config
from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue, record_success

logger = logging.getLogger(__name__)

SUBREDDITS = ["ItalyInformatica", "italy"]
SEARCH_QUERIES = ["hackathon", "hackathon Milano", "hackathon Milan"]
SEARCH_TIME_FILTER = "month"
MAX_RESULTS_PER_QUERY = 25


class RedditCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "reddit"

    def collect(self) -> list[HackathonEvent]:
        user_agent = getattr(config, "REDDIT_USER_AGENT", "")
        if not config.REDDIT_CLIENT_ID or not config.REDDIT_CLIENT_SECRET:
            record_issue("disabled", "Approved Reddit API access not configured; public API migration required")
            logger.info("Reddit: accesso API approvato non configurato; migrazione Developer Platform richiesta")
            return []
        if not isinstance(user_agent, str) or not user_agent.strip():
            record_issue("disabled", "REDDIT_USER_AGENT must identify the actual approved application")
            return []
        if not _PRAW_AVAILABLE:
            record_issue("disabled", "praw not installed")
            return []

        self._stop_requested = False
        try:
            reddit = praw.Reddit(
                client_id=config.REDDIT_CLIENT_ID,
                client_secret=config.REDDIT_CLIENT_SECRET,
                user_agent=user_agent.strip(),
                requestor_kwargs={"timeout": config.HTTP_TIMEOUT},
                ratelimit_seconds=0,
            )
            reddit.read_only = True
        except Exception as error:
            self._record_error(error)
            return []

        events: list[HackathonEvent] = []
        seen_ids: set[str] = set()
        for subreddit_name in SUBREDDITS:
            events.extend(self._search_subreddit(reddit, subreddit_name, seen_ids))
            if self._stop_requested:
                break

        logger.info("Reddit: %d post rilevanti", len(events))
        return events

    def _record_error(self, error: Exception) -> None:
        status = getattr(getattr(error, "response", None), "status_code", None)
        kind = "blocked" if status in {401, 403, 429} else "error"
        detail = f"HTTP {status}" if type(status) is int else type(error).__name__
        record_issue(kind, detail)
        logger.warning("Reddit API: %s", detail)
        if kind == "blocked" or type(error).__name__ in {"OAuthException", "InvalidToken", "InsufficientScope"}:
            self._stop_requested = True

    def _search_subreddit(self, reddit, subreddit_name: str, seen_ids: set[str]) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        try:
            subreddit = reddit.subreddit(subreddit_name)
        except Exception as error:
            self._record_error(error)
            return events

        for query in SEARCH_QUERIES:
            try:
                results = subreddit.search(query, sort="new", time_filter=SEARCH_TIME_FILTER,
                                           limit=MAX_RESULTS_PER_QUERY)
                for submission in results:
                    event = self._parse_submission(submission, subreddit_name)
                    if event is not None and event.id not in seen_ids:
                        seen_ids.add(event.id)
                        events.append(event)
                record_success()
            except Exception as error:
                self._record_error(error)
                if self._stop_requested:
                    break
        return events

    def _parse_submission(self, submission, subreddit_name: str) -> HackathonEvent | None:
        title = getattr(submission, "title", "")
        url = getattr(submission, "url", "")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            return None
        try:
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
                return None
        except ValueError:
            return None
        if parts.hostname == "reddit.com" or parts.hostname.endswith(".reddit.com"):
            permalink = getattr(submission, "permalink", "")
            if not isinstance(permalink, str) or not permalink.startswith("/r/"):
                return None
            url = f"https://www.reddit.com{permalink}"

        description = getattr(submission, "selftext", "")
        published_at = ""
        created = getattr(submission, "created_utc", None)
        if type(created) in {float, int}:
            try:
                published_at = datetime.fromtimestamp(created, timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                pass
        return HackathonEvent(
            title=title.strip(), url=url, source=f"reddit/r/{subreddit_name}",
            description=description[:500] if isinstance(description, str) else "",
            published_at=published_at, date_source="unknown",
        )
