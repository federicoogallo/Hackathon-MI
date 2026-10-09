"""Genera i rimandi GitHub Pages al sito canonico Next.js.

Le chiamate della pipeline e degli strumenti di manutenzione restano compatibili:
`generate_html` scrive docs/index.html e docs/review.html. Il calendario pubblico
e la coda di revisione sono serviti dal sito principale, senza duplicarne i dati.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from html import escape
from pathlib import Path

import config
from models import HackathonEvent

logger = logging.getLogger(__name__)

# Condiviso con il sito Next e il README: impostare lo stesso valore per tutti
# gli ambienti di pubblicazione quando cambia il dominio principale.
SITE_URL = (
    os.environ.get("NEXT_PUBLIC_SITE_URL", "").strip()
    or "https://hackathon-milano.vercel.app"
).rstrip("/")


def _sort_key(e: dict):
    """Ordinamento per data usato anche dal server di amministrazione locale."""
    try:
        ev = HackathonEvent(
            title=e.get("title", ""),
            url=e.get("url", ""),
            source=e.get("source", ""),
            date_str=e.get("date_str", ""),
        )
        parsed = ev.parsed_date()
        return parsed if parsed is not None else date(9999, 12, 31)
    except Exception:
        return date(9999, 12, 31)


def _redirect_html(path: str, *, heading: str, description: str, link_label: str) -> str:
    """Rimando immediato con destinazione canonica e fallback senza JavaScript."""
    destination = escape(f"{SITE_URL}{path}", quote=True)
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(link_label)} | Hackathon Milano</title>
  <meta name="description" content="{escape(description, quote=True)}">
  <meta http-equiv="refresh" content="0; url={destination}">
  <link rel="canonical" href="{destination}">
  <meta property="og:url" content="{destination}">
  <meta name="color-scheme" content="dark light">
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100svh; display: grid; place-items: center;
      padding: 32px 20px; color: #ecf2ef; background: #101b19;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ width: min(100%, 620px); padding: clamp(28px, 6vw, 56px);
      border: 1px solid #3d514b; border-radius: 24px; background: #182822; }}
    .brand {{ margin: 0 0 32px; color: #b6d4c6; font-size: .875rem;
      font-weight: 650; letter-spacing: .08em; text-transform: uppercase; }}
    h1 {{ margin: 0 0 20px; font-size: clamp(2rem, 5vw, 3rem);
      letter-spacing: -.04em; line-height: 1.1; }}
    p {{ margin: 0 0 24px; color: #c4d4cc; line-height: 1.65; }}
    a {{ display: inline-block; padding: 14px 20px; border-radius: 10px;
      color: #10241b; background: #c5e7b7; text-decoration: none; font-weight: 650; }}
    a:hover {{ background: #e0f4d7; }}
    a:focus-visible {{ outline: 3px solid #ecf2ef; outline-offset: 5px; }}
    .note {{ margin: 24px 0 0; font-size: .875rem; }}
    @media (prefers-color-scheme: light) {{
      body {{ background: #f1f4ef; color: #17271f; }}
      main {{ background: #fff; border-color: #cddbd1; }}
      p, .brand {{ color: #465c4e; }}
      a:focus-visible {{ outline-color: #17271f; }}
    }}
  </style>
</head>
<body>
  <main>
    <p class="brand">Hackathon Milano</p>
    <h1>{escape(heading)}</h1>
    <p>{escape(description)}</p>
    <a href="{destination}">{escape(link_label)}</a>
    <p class="note">Se il trasferimento automatico non parte, usa il collegamento qui sopra.</p>
  </main>
</body>
</html>
"""


def generate_html(events_path=None, output_path=None, review_output_path=None) -> Path:
    """Scrive i due rimandi, mantenendo la firma usata dalla pipeline.

    `events_path` e' conservato per compatibilita': le pagine di trasferimento
    non dipendono dall'archivio, dalla coda di revisione o dall'ultimo report.
    """
    output_path = Path(output_path or (config.BASE_DIR / "docs" / "index.html"))
    review_output_path = Path(review_output_path or (config.BASE_DIR / "docs" / "review.html"))

    pages = (
        (
            output_path,
            _redirect_html(
                "/",
                heading="Il calendario ha un nuovo indirizzo.",
                description="Trovi gli hackathon a Milano e dintorni, la ricerca e gli eventi salvati sul sito principale.",
                link_label="Apri il calendario",
            ),
        ),
        (
            review_output_path,
            _redirect_html(
                "/review",
                heading="La revisione eventi è sul sito principale.",
                description="Consulta i candidati da verificare e segnala informazioni utili dalla pagina di revisione.",
                link_label="Apri la revisione eventi",
            ),
        ),
    )
    for page_path, html in pages:
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(html, encoding="utf-8")
        logger.info("Rimando al sito principale generato: %s", page_path)
    return output_path
