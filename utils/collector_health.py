"""Per-collector diagnostics, isolated across parallel worker contexts."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit


def public_endpoint(url: str) -> str:
    """Do not persist credentials, query parameters or fragments in diagnostics."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ""
        return urlunsplit((parts.scheme, parts.hostname, parts.path, "", ""))
    except (TypeError, ValueError):
        return ""


@dataclass
class CollectorHealth:
    requests_ok: int = 0
    issues: list[dict] = field(default_factory=list)

    def outcome(self, event_count: int) -> str:
        if not self.issues:
            return "healthy" if event_count else "empty"
        if event_count or self.requests_ok:
            return "degraded"
        kinds = {item["kind"] for item in self.issues}
        if kinds == {"disabled"}:
            return "disabled"
        if kinds <= {"blocked"}:
            return "blocked"
        return "failed"


_current: ContextVar[CollectorHealth | None] = ContextVar("collector_health", default=None)


@contextmanager
def track_collector():
    health = CollectorHealth()
    token = _current.set(health)
    try:
        yield health
    finally:
        _current.reset(token)


def record_success() -> None:
    health = _current.get()
    if health is not None:
        health.requests_ok += 1


def record_issue(kind: str, detail: str = "", url: str = "") -> None:
    health = _current.get()
    if health is not None:
        health.issues.append({"kind": kind, "detail": detail, "endpoint": public_endpoint(url)})
