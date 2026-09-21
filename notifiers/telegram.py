"""
Notifiche Telegram via Bot API.

Invia un riepilogo mobile a fine run con nuovi eventi, stato e link al sito.
"""

import logging
from datetime import datetime
from html import escape
from typing import Any
from urllib.parse import urlparse

import requests

import config

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_EVENT_PREVIEWS = 4

_MONTHS_IT = (
    "gen", "feb", "mar", "apr", "mag", "giu",
    "lug", "ago", "set", "ott", "nov", "dic",
)


def _send_message(
    text: str,
    parse_mode: str = "HTML",
    button_url: str = "",
    button_text: str = "Apri il calendario",
) -> bool:
    """Invia un messaggio Telegram. Ritorna True se successo, False altrimenti."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram non configurato (manca BOT_TOKEN o CHAT_ID)")
        return False

    url = TELEGRAM_API_BASE.format(token=config.TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    safe_button_url = _safe_http_url(button_url)
    if safe_button_url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{
                "text": button_text,
                "url": safe_button_url,
            }]],
        }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return True
        else:
            logger.error(
                "Telegram API errore %d",
                response.status_code,
            )
            return False
    except requests.exceptions.RequestException as e:
        # Le eccezioni HTTP possono includere l'URL contenente il token del bot.
        logger.error("Errore invio Telegram: %s", type(e).__name__)
        return False


def notify_run_summary(
    new_events: int,
    total_upcoming: int,
    elapsed_seconds: float,
    failed_collectors: list[str],
    page_url: str = "",
    events: list[Any] | None = None,
    collectors_ok: int | None = None,
    collectors_total: int | None = None,
    is_test: bool = False,
) -> bool:
    """Invia sempre un riepilogo a fine run, anche quando non ci sono novità."""
    text = _format_run_summary(
        new_events=new_events,
        total_upcoming=total_upcoming,
        elapsed_seconds=elapsed_seconds,
        failed_collectors=failed_collectors,
        events=events or [],
        collectors_ok=collectors_ok,
        collectors_total=collectors_total,
        is_test=is_test,
    )
    return _send_message(
        text,
        button_url=page_url,
        button_text="🗓 Apri il calendario",
    )


def _format_run_summary(
    new_events: int,
    total_upcoming: int,
    elapsed_seconds: float,
    failed_collectors: list[str],
    events: list[Any],
    collectors_ok: int | None = None,
    collectors_total: int | None = None,
    is_test: bool = False,
) -> str:
    """Costruisce il testo HTML del riepilogo senza effettuare chiamate di rete.

    Mostra al massimo MAX_EVENT_PREVIEWS eventi per restare leggibile su mobile.
    """
    lines = [
        "🧪 <b>Anteprima · Hackathon Milano</b>"
        if is_test else "🔎 <b>Hackathon Milano · aggiornamento</b>",
        "",
    ]

    if new_events > 0:
        noun = "nuovo evento" if new_events == 1 else "nuovi eventi"
        verb = "trovato" if new_events == 1 else "trovati"
        lines.append(f"✨ <b>{new_events} {noun} {verb}</b>")
    else:
        lines.extend([
            "✅ <b>Scansione completata</b>",
            "<i>Nessun nuovo evento trovato questa volta.</i>",
        ])

    previews = events[:MAX_EVENT_PREVIEWS]
    if previews:
        lines.extend(["", "<b>Nuovi hackathon</b>"])
        for index, event in enumerate(previews, start=1):
            lines.append(_format_event_preview(event, index))
        hidden = max(0, new_events - len(previews))
        if hidden:
            lines.append(f"<i>+{hidden} altr{'o' if hidden == 1 else 'i'} nel calendario</i>")

    lines.extend(["", "<b>Situazione</b>"])
    event_label = "evento futuro confermato" if total_upcoming == 1 else "eventi futuri confermati"
    lines.append(f"📌 <b>{total_upcoming}</b> {event_label}")

    if collectors_ok is not None and collectors_total is not None:
        status_icon = "🟢" if not failed_collectors else "🟠"
        lines.append(
            f"{status_icon} <b>{collectors_ok}/{collectors_total}</b> fonti operative"
        )

    if failed_collectors:
        lines.append(f"⚠️ Non disponibili: {_escape_html(', '.join(failed_collectors))}")

    lines.append(f"⏱ {_format_duration(elapsed_seconds)}")

    if is_test:
        lines.extend(["", "<i>Messaggio di prova · nessun dato è stato modificato.</i>"])

    return "\n".join(lines)


def _format_event_preview(event: Any, index: int) -> str:
    title = _escape_html(_short_text(_event_value(event, "title") or "Evento senza titolo", 180))
    url = _safe_http_url(str(_event_value(event, "url") or ""))
    date_text = _format_event_date(str(_event_value(event, "date_str") or ""))
    location = _escape_html(_short_text(_event_value(event, "location") or "", 100))

    linked_title = f'<a href="{escape(url, quote=True)}">{title}</a>' if url else title
    lines = [f"{index}. <b>{linked_title}</b>"]

    details = []
    if date_text:
        details.append(f"🗓 {date_text}")
    if location:
        details.append(f"📍 {location}")
    if details:
        lines.append("   " + "  ·  ".join(details))

    return "\n".join(lines)


def _event_value(event: Any, key: str) -> Any:
    if isinstance(event, dict):
        return event.get(key, "")
    return getattr(event, key, "")


def _format_event_date(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value).date()
        return f"{parsed.day} {_MONTHS_IT[parsed.month - 1]} {parsed.year}"
    except ValueError:
        return _escape_html(_short_text(value, 40))


def _short_text(value: Any, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _format_duration(seconds: float) -> str:
    total = max(0, round(seconds))
    minutes, remaining = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {remaining} s"
    return f"{remaining} s"


def _safe_http_url(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlparse(value)
        valid = parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username
    except ValueError:
        return ""
    if valid and not any(char.isspace() for char in value):
        return value
    return ""


def _escape_html(text: str) -> str:
    """Escape caratteri speciali HTML per Telegram."""
    return escape(text, quote=False)
