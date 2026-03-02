"""
Notifiche Telegram via Bot API.

Tre tipi di messaggio:
1. Notifica nuovo hackathon (per ogni evento nuovo)
2. Report giornaliero (riepilogo di fine run)
3. Alert errore (se un collector crasha)
"""

import logging
from dataclasses import dataclass

import requests

import config
from models import HackathonEvent

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


# ─── Messaggi formattati ────────────────────────────────────────────────────


def notify_new_hackathon(event: HackathonEvent) -> bool:
    """Invia notifica per un nuovo hackathon trovato: struttura chiara, solo campi utili."""
    lines = []

    # Intestazione
    lines.append("🆕 <b>Nuovo hackathon</b>")
    lines.append("")
    lines.append(f"<b>{_escape_html(event.title)}</b>")

    # Dettagli (solo se presenti e non vuoti)
    parts = []
    if (event.date_str or "").strip():
        parts.append(f"📅 {_escape_html(event.date_str.strip())}")
    if (event.location or "").strip():
        parts.append(f"📍 {_escape_html(event.location.strip())}")
    if (event.organizer or "").strip():
        parts.append(f"👤 {_escape_html(event.organizer.strip())}")
    if parts:
        lines.append("")
        lines.append("\n".join(parts))

    # Descrizione breve (1–2 righe, evita “nessuna descrizione”)
    lines.append("")
    if (event.description or "").strip():
        desc = event.description.strip()
        desc = desc.replace("\n", " ").strip()
        if len(desc) > 220:
            desc = desc[:220].rsplit(" ", 1)[0] + "…"
        lines.append(f"<i>{_escape_html(desc)}</i>")
    else:
        lines.append("<i>Apri il link per dettagli e iscrizioni.</i>")

    # Link
    lines.append("")
    lines.append(f"🔗 <a href=\"{event.url}\">Apri evento</a>")
    if event.alternate_urls:
        for i, alt_url in enumerate(event.alternate_urls[:2], 1):
            lines.append(f"🔗 <a href=\"{alt_url}\">Link alternativo {i}</a>")

    return _send_message("\n".join(lines))


@dataclass
class RunReport:
    """Dati del report giornaliero."""
    date: str
    collectors_ok: int
    collectors_total: int
    failed_collectors: list[str]
    raw_events: int
    post_dedup: int
    post_keyword: int
    post_llm: int
    new_events: int
    total_stored: int


def notify_daily_report(report: RunReport) -> bool:
    """Invia il report riepilogativo giornaliero."""
    failed = report.failed_collectors
    collector_status = (
        f"\n⚠️ Falliti: {', '.join(failed)}"
        if failed
        else ""
    )
    lines = [
        "📊 <b>Report giornaliero</b>",
        f"<i>{report.date}</i>",
        "",
        f"🌐 Collector: <b>{report.collectors_ok}/{report.collectors_total}</b> ok{collector_status}",
        "",
        "<b>Pipeline</b>",
        f"  Raw: <code>{report.raw_events}</code>",
        f"  Post dedup: <code>{report.post_dedup}</code>",
        f"  Post keyword: <code>{report.post_keyword}</code>",
        f"  Post LLM: <code>{report.post_llm}</code>",
        "",
        f"🆕 Nuovi notificati: <b>{report.new_events}</b>",
        f"📚 Storico: <b>{report.total_stored}</b> eventi",
    ]
    return _send_message("\n".join(lines))


def notify_collector_error(collector_name: str, error_message: str) -> bool:
    """Invia alert per un collector fallito."""
    text = (
        f"⚠️ <b>Collector fallito: {_escape_html(collector_name)}</b>\n"
        f"<i>{_escape_html(str(error_message)[:400])}</i>"
    )
    return _send_message(text)


def _escape_html(text: str) -> str:
    """Escape caratteri speciali HTML per Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
