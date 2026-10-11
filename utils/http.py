"""
Client HTTP condiviso con retry automatico, backoff esponenziale e timeout.

Tutti i collector devono usare queste funzioni per le chiamate HTTP,
così da avere un comportamento uniforme in caso di errori di rete.
"""

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
from utils.collector_health import public_endpoint, record_issue, record_success

logger = logging.getLogger(__name__)

# Session singleton (creata al primo uso)
_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Ritorna una session HTTP condivisa con retry e backoff configurati."""
    global _session
    if _session is not None:
        return _session

    _session = requests.Session()

    # Retry con backoff esponenziale su errori temporanei
    retry_strategy = Retry(
        total=config.HTTP_MAX_RETRIES,
        backoff_factor=config.HTTP_BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    _session.mount("https://", adapter)
    _session.mount("http://", adapter)

    # User-Agent realistico
    _session.headers.update({
        "User-Agent": config.HTTP_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    return _session


def safe_get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | None = None,
) -> requests.Response | None:
    """GET con gestione errori. Ritorna None (mai crash) se la richiesta fallisce.

    Args:
        url: URL da richiedere.
        params: Query parameters opzionali.
        headers: Headers aggiuntivi (si sommano a quelli della session).
        timeout: Timeout in secondi (default da config.HTTP_TIMEOUT).

    Returns:
        Response se la richiesta ha successo (status < 400), None altrimenti.
    """
    if timeout is None:
        timeout = config.HTTP_TIMEOUT

    session = get_session()
    try:
        response = session.get(url, params=params, headers=headers, timeout=timeout)
        if response.status_code >= 400:
            record_issue("blocked" if response.status_code in {401, 403, 405, 429} else "http_error",
                         f"HTTP {response.status_code}", url)
            logger.warning(
                "HTTP %d per %s",
                response.status_code,
                public_endpoint(url),
            )
            return None
        record_success()
        return response

    except requests.exceptions.Timeout:
        record_issue("timeout", "request timed out", url)
        logger.error("Timeout (%ds) per %s", timeout, public_endpoint(url))
        return None

    except requests.exceptions.ConnectionError:
        record_issue("connection_error", "connection failed", url)
        logger.error("Connessione fallita per %s", public_endpoint(url))
        return None

    except requests.exceptions.RequestException as e:
        record_issue("http_error", type(e).__name__, url)
        logger.error("Errore HTTP per %s: %s", public_endpoint(url), type(e).__name__)
        return None


def safe_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | None = None,
) -> dict | list | None:
    """GET che ritorna direttamente il JSON parsato, o None in caso di errore."""
    response = safe_get(url, params=params, headers=headers, timeout=timeout)
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        record_issue("parse_error", "invalid JSON", url)
        logger.error("JSON non valido da %s", public_endpoint(url))
        return None


def reset_session() -> None:
    """Reset della session (utile per i test)."""
    global _session
    if _session is not None:
        _session.close()
    _session = None
