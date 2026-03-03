"""
Notifiche Telegram via Bot API.

Invia un summary a fine run con il numero di nuovi hackathon e link al sito.
"""

import logging

import requests

import config

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def _send_message(text: str, parse_mode: str = "HTML") -> bool:
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

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return True
        else:
            logger.error(
                "Telegram API errore %d: %s",
                response.status_code,
                response.text[:200],
            )
            return False
    except requests.exceptions.RequestException as e:
        logger.error("Errore invio Telegram: %s", e)
        return False


def notify_run_summary(
    new_events: int,
    total_upcoming: int,
    elapsed_seconds: float,
    failed_collectors: list[str],
    page_url: str = "",
) -> bool:
    """Invia sempre un summary a fine run — anche quando non ci sono nuovi eventi.

    Permette di verificare che il bot sia vivo e la pipeline abbia girato.
    """
    if new_events > 0:
        header = f"🆕 <b>+{new_events} nuovo{'i' if new_events > 1 else ''} hackathon</b>"
    else:
        header = "🔍 <b>Scansione completata</b>\n<i>Nessun nuovo hackathon trovato oggi.</i>"

    lines = [header, ""]

    if total_upcoming > 0:
        label = f"hackathon {'attivi' if total_upcoming > 1 else 'attivo'}"
        lines.append(f"📅 In archivio: <b>{total_upcoming}</b> {label} (futuri)")
    else:
        lines.append("📅 Nessun hackathon futuro confermato in archivio.")

    if failed_collectors:
        lines.append(f"⚠️ Collector falliti: {_escape_html(', '.join(failed_collectors))}")

    lines.append(f"\n<i>⏱ Completata in {elapsed_seconds:.0f}s</i>")

    if page_url:
        lines.append(f'\n🌐 <a href="{page_url}">Vedi tutti gli hackathon</a>')

    return _send_message("\n".join(lines))


def _escape_html(text: str) -> str:
    """Escape caratteri speciali HTML per Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
