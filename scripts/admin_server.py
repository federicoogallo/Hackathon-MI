#!/usr/bin/env python3
"""Local-only web admin for the hackathon monitor.

This server intentionally binds to 127.0.0.1 and is not meant for deployment.
It edits the same JSON files used by the maintainer CLI, then rebuilds docs/.
"""

from __future__ import annotations

import argparse
import html
import json
import secrets
import sys
from contextlib import redirect_stdout
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config
from models import HackathonEvent
from scripts import review_candidate as admin
from storage.json_store import EventStore
from utils.admin_audit import load_admin_actions
from utils.html_export import _sort_key
from utils.review_queue import load_review_queue


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TOKEN = secrets.token_urlsafe(24)
LOCAL_TZ = ZoneInfo("Europe/Rome")
STALE_AFTER_HOURS = 36

REASON_LABELS = {
    "valid_milan_event": "Valido a Milano",
    "online_only": "Solo online",
    "not_milan": "Fuori Milano",
    "past_or_finished": "Passato/finito",
    "missing_date_or_venue": "Data/venue mancanti",
    "duplicate": "Duplicato",
    "not_hackathon": "Non hackathon",
    "source_noise": "Fonte rumorosa",
    "known_false_positive": "Falso positivo noto",
    "other": "Altro",
}


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _short_id(item: dict) -> str:
    return str(item.get("id", ""))[:12]


def _event_date(item: dict) -> str:
    return str(item.get("date_str") or "TBD")


def _reason_options(default: str = "other") -> str:
    return "".join(
        f'<option value="{_esc(code)}"{" selected" if code == default else ""}>'
        f"{_esc(REASON_LABELS.get(code, code))}</option>"
        for code in admin.REASON_CODES
    )


def _search_text(*parts: object) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def _status_banner(message: str, kind: str = "ok") -> str:
    if not message:
        return ""
    return f'<div class="banner {kind}" role="status">{_esc(message)}</div>'


def _external_link(url: str) -> str:
    if not url:
        return ""
    return (
        f'<a class="icon-link" href="{_esc(url)}" target="_blank" '
        'rel="noopener" title="Apri evento">Apri</a>'
    )


def _field(label: str, control: str) -> str:
    return f'<label class="field"><span>{_esc(label)}</span>{control}</label>'


def _form(
    action: str,
    identifier: str,
    submit_label: str,
    *,
    danger: bool = False,
    note: bool = False,
    audit: bool = False,
    regression: bool = False,
    blacklist: bool = False,
    default_reason_code: str = "other",
) -> str:
    confirm = "return confirm('Confermi questa azione?')" if danger else "return true"
    fields = [
        f'<input type="hidden" name="csrf" value="{TOKEN}">',
        f'<input type="hidden" name="action" value="{_esc(action)}">',
        f'<input type="hidden" name="identifier" value="{_esc(identifier)}">',
    ]
    if blacklist:
        fields.append('<input type="hidden" name="blacklist" value="1">')
    if note:
        fields.append(
            _field(
                "Nota",
                '<input name="note" placeholder="Perche va rivisto?" autocomplete="off">',
            )
        )
    if audit:
        fields.append(
            _field(
                "Motivo",
                '<input name="reason" placeholder="Decisione admin" autocomplete="off">',
            )
        )
    if audit or note:
        fields.append(
            _field(
                "Categoria",
                f'<select name="reason_code">{_reason_options(default_reason_code)}</select>',
            )
        )
    if regression:
        fields.append(
            '<label class="checkline">'
            '<input type="checkbox" name="regression" value="1">'
            "<span>Usa nei test</span>"
            "</label>"
        )

    button_class = "submit danger" if danger else "submit"
    return (
        f'<form class="decision-form" method="post" action="/action" onsubmit="{confirm}">'
        f'<div class="decision-fields">{"".join(fields)}</div>'
        f'<button class="{button_class}" type="submit">{_esc(submit_label)}</button>'
        "</form>"
    )


def _action_panel(label: str, form_html: str, *, tone: str = "") -> str:
    return (
        f'<details class="action-panel {tone}">'
        f'<summary>{_esc(label)}</summary>'
        f'<div class="action-popover">{form_html}</div>'
        "</details>"
    )


def _events_last_check() -> datetime | None:
    try:
        data = json.loads(config.EVENTS_FILE.read_text(encoding="utf-8"))
        last_check = data.get("last_check")
        if not last_check:
            return None
        parsed = datetime.fromisoformat(last_check)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=LOCAL_TZ)
        return parsed.astimezone(LOCAL_TZ)
    except Exception:
        return None


def _events_reference_date() -> date | None:
    last_check = _events_last_check()
    return last_check.date() if last_check else None


def _freshness_warning() -> tuple[str, str]:
    last_check = _events_last_check()
    if last_check is None:
        return (
            "Dati locali senza last_check: aggiorna il repository prima di decidere eventi o review.",
            "warn",
        )

    age_hours = (datetime.now(LOCAL_TZ) - last_check).total_seconds() / 3600
    if age_hours <= STALE_AFTER_HOURS:
        return "", "ok"

    age_days = max(1, round(age_hours / 24))
    label = last_check.strftime("%d %b %Y alle %H:%M")
    return (
        f"Dati locali aggiornati al {label} ({age_days} giorni fa): fai pull/fetch prima di amministrare.",
        "warn",
    )


def _is_public_event(item: dict, ref_date: date | None) -> bool:
    if not item.get("is_hackathon"):
        return False
    try:
        event = HackathonEvent(
            title=item.get("title", ""),
            url=item.get("url", ""),
            source=item.get("source", ""),
            date_str=item.get("date_str", ""),
        )
        return event.is_upcoming(ref_date=ref_date)
    except Exception:
        return True


def _public_events(events: list[dict]) -> list[dict]:
    ref_date = _events_reference_date()
    public = [item for item in events if _is_public_event(item, ref_date)]
    public.sort(key=_sort_key)
    return public


def _archive_events(events: list[dict], public: list[dict]) -> list[dict]:
    public_ids = {item.get("id") for item in public}
    archive = [item for item in events if item.get("id") not in public_ids]
    archive.sort(key=_sort_key)
    return archive


def _published_rows(
    events: list[dict],
    *,
    include_review: bool = True,
    empty_label: str = "Nessun evento pubblicato.",
) -> str:
    if not events:
        return f'<div class="empty">{_esc(empty_label)}</div>'

    rows = []
    for item in events:
        identifier = str(item.get("id", ""))
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        source = item.get("source", "")
        location = item.get("location") or "Location non specificata"
        review_action = ""
        if include_review:
            review_action = _action_panel(
                "Review",
                _form("move-to-review", identifier, "Sposta", note=True),
                tone="review",
            )
        rows.append(
            '<article class="row" data-search="'
            f'{_esc(_search_text(title, url, source, location, _event_date(item)))}">'
            '<div class="row-main">'
            '<div class="meta">'
            f'<code>{_esc(_short_id(item))}</code>'
            f'<span>{_esc(_event_date(item))}</span>'
            f'<span>{_esc(source)}</span>'
            "</div>"
            f'<h2><a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(title)}</a></h2>'
            f'<p>{_esc(location)}</p>'
            "</div>"
            '<div class="actions">'
            f"{_external_link(url)}"
            f"{review_action}"
            f'{_action_panel("Elimina", _form("remove", identifier, "Elimina", danger=True, audit=True, regression=True), tone="danger")}'
            f'{_action_panel("Blacklist", _form("remove-blacklist", identifier, "Elimina + blacklist", danger=True, audit=True, regression=True, blacklist=True), tone="danger")}'
            "</div>"
            "</article>"
        )
    return "\n".join(rows)


def _review_rows(candidates: list[dict]) -> str:
    if not candidates:
        return '<div class="empty">Nessun candidato in revisione.</div>'

    rows = []
    for item in candidates:
        identifier = str(item.get("id", ""))
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        source = item.get("source", "")
        confidence = float(item.get("confidence") or 0.0)
        reason = item.get("review_reason") or item.get("review_note") or "Da valutare"
        location = item.get("location") or "Location non specificata"
        rows.append(
            '<article class="row review-row" data-search="'
            f'{_esc(_search_text(title, url, source, reason, location, _event_date(item)))}">'
            '<div class="row-main">'
            '<div class="meta">'
            f'<code>{_esc(_short_id(item))}</code>'
            f'<span>AI {confidence:.0%}</span>'
            f'<span>{_esc(source)}</span>'
            f'<span>{_esc(_event_date(item))}</span>'
            "</div>"
            f'<h2><a href="{_esc(url)}" target="_blank" rel="noopener">{_esc(title)}</a></h2>'
            f'<p>{_esc(reason)}</p>'
            "</div>"
            '<div class="actions">'
            f"{_external_link(url)}"
            f'{_action_panel("Approva", _form("approve", identifier, "Approva", audit=True, regression=True, default_reason_code="valid_milan_event"), tone="approve")}'
            f'{_action_panel("Rifiuta", _form("reject", identifier, "Rifiuta", danger=True, audit=True, regression=True), tone="danger")}'
            f'{_action_panel("Ignora", _form("dismiss", identifier, "Ignora", audit=True), tone="quiet")}'
            "</div>"
            "</article>"
        )
    return "\n".join(rows)


def _metric(label: str, value: object, sub: str = "") -> str:
    return (
        '<div class="metric">'
        f'<span>{_esc(label)}</span>'
        f'<strong>{_esc(value)}</strong>'
        f'<small>{_esc(sub)}</small>'
        "</div>"
    )


def _page(message: str = "", kind: str = "ok") -> str:
    store = EventStore()
    all_events = store.all_events()
    events = _public_events(all_events)
    archived = _archive_events(all_events, events)
    candidates = load_review_queue()
    actions = load_admin_actions()
    regressions = [item for item in actions if item.get("regression") is True]
    freshness_message, freshness_kind = _freshness_warning()
    return f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hackathon Monitor Admin</title>
  <style>
    :root {{
      --bg:#f4f5f7; --surface:#ffffff; --surface-2:#f9fafb; --ink:#101828;
      --muted:#667085; --faint:#98a2b3; --border:#d7dce3; --border-strong:#b7c0cc;
      --blue:#2563eb; --blue-soft:#eff4ff; --green:#067647; --green-soft:#ecfdf3;
      --red:#b42318; --red-soft:#fff1f0; --amber:#b54708; --amber-soft:#fff7ed;
      --shadow:0 1px 2px rgba(16,24,40,.05),0 8px 24px rgba(16,24,40,.08);
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; background:var(--bg); color:var(--ink);
      font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing:antialiased;
    }}
    a {{ color:inherit; }}
    .shell {{ min-height:100vh; }}
    .app-header {{
      background:#111827; color:#fff; border-bottom:1px solid rgba(255,255,255,.08);
    }}
    .bar {{
      max-width:1320px; margin:0 auto; padding:18px 24px;
      display:flex; justify-content:space-between; align-items:center; gap:16px;
    }}
    .brand {{ display:flex; gap:12px; align-items:center; min-width:0; }}
    .mark {{
      width:36px; height:36px; border-radius:8px; display:grid; place-items:center;
      background:#2563eb; color:#fff; font-weight:900; letter-spacing:0;
    }}
    .brand h1 {{ margin:0; font-size:18px; line-height:1.15; letter-spacing:0; }}
    .brand p {{ margin:3px 0 0; color:#aab4c5; font-size:13px; }}
    .status-pill {{
      display:inline-flex; align-items:center; gap:8px; border:1px solid rgba(255,255,255,.14);
      color:#d0d5dd; border-radius:999px; padding:7px 11px; font-size:12px; font-weight:700;
      white-space:nowrap;
    }}
    .status-pill::before {{ content:""; width:8px; height:8px; border-radius:50%; background:#22c55e; }}
    main {{ max-width:1320px; margin:0 auto; padding:20px 24px 36px; }}
    .banner {{
      margin-bottom:14px; border-radius:8px; padding:11px 13px; font-weight:750;
      border:1px solid #abefc6; background:var(--green-soft); color:var(--green);
    }}
    .banner.error {{ border-color:#fecdca; background:var(--red-soft); color:var(--red); }}
    .banner.warn {{ border-color:#fedf89; background:var(--amber-soft); color:var(--amber); }}
    .metrics {{
      display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:14px;
    }}
    .metric {{
      background:var(--surface); border:1px solid var(--border); border-radius:8px;
      padding:14px 15px; min-height:88px; box-shadow:0 1px 2px rgba(16,24,40,.03);
    }}
    .metric span {{ display:block; color:var(--muted); font-size:11px; font-weight:850; letter-spacing:.08em; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:28px; letter-spacing:0; line-height:1; }}
    .metric small {{ display:block; margin-top:6px; color:var(--faint); font-size:12px; }}
    .workspace {{
      background:var(--surface); border:1px solid var(--border); border-radius:8px; box-shadow:var(--shadow);
      overflow:visible;
    }}
    .toolbar {{
      position:sticky; top:0; z-index:20; display:flex; align-items:center; gap:12px;
      padding:12px; border-bottom:1px solid var(--border); background:rgba(255,255,255,.92);
      backdrop-filter:blur(10px); border-radius:8px 8px 0 0;
    }}
    .search {{ position:relative; flex:1; min-width:260px; }}
    .search input {{
      width:100%; height:40px; border:1px solid var(--border); border-radius:8px;
      padding:0 12px 0 36px; font:inherit; outline:none; background:#fff;
    }}
    .search input:focus {{ border-color:var(--blue); box-shadow:0 0 0 3px rgba(37,99,235,.12); }}
    .search::before {{ content:""; position:absolute; left:13px; top:50%; width:13px; height:13px; transform:translateY(-50%); border:2px solid var(--faint); border-radius:50%; }}
    .search::after {{ content:""; position:absolute; left:24px; top:25px; width:7px; height:2px; transform:rotate(45deg); background:var(--faint); border-radius:2px; }}
    .tabs {{ display:flex; gap:6px; }}
    .tab {{
      height:40px; border:1px solid var(--border); border-radius:8px; padding:0 13px;
      background:#fff; color:#344054; font-weight:800; cursor:pointer;
    }}
    .tab.active {{ background:#111827; color:#fff; border-color:#111827; }}
    .panel {{ display:none; }}
    .panel.active {{ display:block; }}
    .section-head {{
      display:flex; justify-content:space-between; align-items:center; padding:14px 16px 8px;
    }}
    .section-head h2 {{ margin:0; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.1em; }}
    .count {{ color:var(--muted); font-size:13px; font-weight:700; }}
    .rows {{ padding:0 12px 12px; }}
    .row {{
      position:relative; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; align-items:start;
      border:1px solid var(--border); border-radius:8px; padding:14px; margin-bottom:9px;
      background:var(--surface-2);
    }}
    .row:hover {{ border-color:var(--border-strong); background:#fff; }}
    .row-main {{ min-width:0; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:7px; color:var(--muted); font-size:12px; font-weight:700; }}
    code {{ background:#eef2f7; border:1px solid var(--border); border-radius:6px; padding:2px 6px; color:#344054; }}
    .row h2 {{ margin:7px 0 5px; font-size:16px; line-height:1.35; letter-spacing:0; overflow-wrap:anywhere; }}
    .row h2 a {{ text-decoration:none; }}
    .row h2 a:hover {{ color:var(--blue); }}
    .row p {{ margin:0; color:var(--muted); line-height:1.45; overflow-wrap:anywhere; }}
    .actions {{
      display:flex; justify-content:flex-end; align-items:flex-start; gap:7px; flex-wrap:wrap;
      min-width:340px; max-width:540px;
    }}
    .icon-link, .action-panel summary, .submit {{
      min-height:34px; display:inline-flex; align-items:center; justify-content:center;
      border:1px solid var(--border); border-radius:8px; padding:0 10px;
      background:#fff; color:#344054; font-size:13px; font-weight:850; text-decoration:none; cursor:pointer;
    }}
    .icon-link:hover, .action-panel summary:hover {{ border-color:var(--blue); color:var(--blue); }}
    .action-panel {{ position:relative; }}
    .action-panel summary {{ list-style:none; }}
    .action-panel summary::-webkit-details-marker {{ display:none; }}
    .action-panel.approve summary {{ border-color:#abefc6; background:var(--green-soft); color:var(--green); }}
    .action-panel.review summary {{ border-color:#bfdbfe; background:var(--blue-soft); color:#1d4ed8; }}
    .action-panel.danger summary {{ border-color:#fecdca; background:var(--red-soft); color:var(--red); }}
    .action-panel.quiet summary {{ color:var(--muted); }}
    .action-popover {{
      position:absolute; right:0; top:42px; z-index:30; width:min(420px, calc(100vw - 48px));
      background:#fff; border:1px solid var(--border-strong); border-radius:8px; box-shadow:var(--shadow);
      padding:12px;
    }}
    .decision-form {{ display:grid; gap:10px; }}
    .decision-fields {{ display:grid; grid-template-columns:1fr 170px; gap:9px; align-items:end; }}
    .field {{ display:grid; gap:4px; color:var(--muted); font-size:11px; font-weight:850; text-transform:uppercase; letter-spacing:.06em; }}
    .field input, .field select {{
      width:100%; height:36px; border:1px solid var(--border); border-radius:8px; padding:0 9px;
      font:inherit; color:var(--ink); background:#fff; text-transform:none; letter-spacing:0; font-weight:600;
    }}
    .field input:focus, .field select:focus {{ outline:none; border-color:var(--blue); box-shadow:0 0 0 3px rgba(37,99,235,.12); }}
    .checkline {{
      grid-column:1 / -1; display:flex; align-items:center; gap:7px; color:var(--muted);
      font-size:13px; font-weight:750; text-transform:none; letter-spacing:0;
    }}
    .submit {{ width:100%; background:#111827; color:#fff; border-color:#111827; }}
    .submit:hover {{ background:#0b1220; }}
    .submit.danger {{ background:var(--red); border-color:var(--red); color:#fff; }}
    .empty {{
      margin:0 12px 12px; padding:34px; text-align:center; border:1px dashed var(--border);
      border-radius:8px; color:var(--muted); background:var(--surface-2);
    }}
    .hidden {{ display:none; }}
    @media (max-width:900px) {{
      .bar, main {{ padding-left:14px; padding-right:14px; }}
      .metrics {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .toolbar {{ flex-direction:column; align-items:stretch; }}
      .tabs {{ width:100%; }}
      .tab {{ flex:1; }}
      .row {{ grid-template-columns:1fr; }}
      .actions {{ justify-content:flex-start; min-width:0; max-width:none; }}
      .action-popover {{ left:0; right:auto; }}
    }}
    @media (max-width:560px) {{
      .metrics {{ grid-template-columns:1fr; }}
      .decision-fields {{ grid-template-columns:1fr; }}
      .status-pill {{ display:none; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="app-header">
      <div class="bar">
        <div class="brand">
          <div class="mark">HM</div>
          <div>
            <h1>Hackathon Monitor Admin</h1>
            <p>Console locale per pubblicazione, review e rimozioni</p>
          </div>
        </div>
        <div class="status-pill">127.0.0.1</div>
      </div>
    </header>
    <main>
      {_status_banner(message, kind)}
      {_status_banner(freshness_message, freshness_kind)}
      <section class="metrics" aria-label="Metriche admin">
        {_metric("Pubblicati", len(events), "come GitHub Pages")}
        {_metric("Archivio", len(archived), "storico non pubblico")}
        {_metric("Review", len(candidates), "candidati da decidere")}
        {_metric("Azioni", len(actions), "decisioni registrate")}
        {_metric("Regressioni", len(regressions), "casi nei test")}
      </section>
      <section class="workspace">
        <div class="toolbar">
          <div class="search">
            <input id="search" placeholder="Cerca per titolo, URL, fonte, data o motivo..." autocomplete="off">
          </div>
          <div class="tabs" role="tablist" aria-label="Sezioni admin">
            <button class="tab active" data-tab="published" type="button">Pubblicati</button>
            <button class="tab" data-tab="archive" type="button">Archivio</button>
            <button class="tab" data-tab="review" type="button">Review</button>
          </div>
        </div>
        <section id="published" class="panel active">
          <div class="section-head"><h2>Eventi pubblicati</h2><span class="count" data-count-for="published">{len(events)} eventi</span></div>
          <div class="rows">{_published_rows(events)}</div>
        </section>
        <section id="archive" class="panel">
          <div class="section-head"><h2>Storico non pubblico</h2><span class="count" data-count-for="archive">{len(archived)} eventi</span></div>
          <div class="rows">{_published_rows(archived, include_review=False, empty_label="Nessun evento in archivio.")}</div>
        </section>
        <section id="review" class="panel">
          <div class="section-head"><h2>Candidati in review</h2><span class="count" data-count-for="review">{len(candidates)} candidati</span></div>
          <div class="rows">{_review_rows(candidates)}</div>
        </section>
      </section>
    </main>
  </div>
  <script>
    const tabs = document.querySelectorAll('.tab');
    const panels = document.querySelectorAll('.panel');
    const search = document.getElementById('search');

    function activePanel() {{
      return document.querySelector('.panel.active');
    }}

    function closeOpenPanels(except) {{
      document.querySelectorAll('details[open]').forEach(d => {{
        if (d !== except) d.removeAttribute('open');
      }});
    }}

    function updateVisibleCount(panel) {{
      const rows = panel.querySelectorAll('.row');
      const visible = panel.querySelectorAll('.row:not(.hidden)').length;
      const count = document.querySelector(`[data-count-for="${{panel.id}}"]`);
      if (count) count.textContent = `${{visible}} / ${{rows.length}}`;
    }}

    function filterRows() {{
      const panel = activePanel();
      const q = search.value.trim().toLowerCase();
      panel.querySelectorAll('.row').forEach(row => {{
        row.classList.toggle('hidden', Boolean(q) && !row.dataset.search.includes(q));
      }});
      updateVisibleCount(panel);
    }}

    function selectTab(name) {{
      tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === name));
      panels.forEach(p => p.classList.toggle('active', p.id === name));
      closeOpenPanels();
      filterRows();
    }}

    tabs.forEach(t => t.addEventListener('click', () => selectTab(t.dataset.tab)));
    search.addEventListener('input', filterRows);
    document.addEventListener('toggle', event => {{
      if (event.target.matches('details[open]')) closeOpenPanels(event.target);
    }}, true);
    filterRows();
  </script>
</body>
</html>"""


def _perform_action(fields: dict[str, list[str]]) -> tuple[str, str]:
    if fields.get("csrf", [""])[0] != TOKEN:
        return "Token admin non valido. Ricarica la pagina.", "error"

    action = fields.get("action", [""])[0]
    identifier = fields.get("identifier", [""])[0]
    note = fields.get("note", [""])[0]
    reason = fields.get("reason", [""])[0]
    reason_code = fields.get("reason_code", ["other"])[0] or "other"
    regression = fields.get("regression", [""])[0] == "1"
    output = StringIO()

    try:
        with redirect_stdout(output):
            if action == "approve":
                admin.approve_candidate(
                    identifier,
                    reason=reason,
                    reason_code=reason_code,
                    regression=regression,
                )
            elif action == "reject":
                admin.reject_candidate(
                    identifier,
                    reason=reason,
                    reason_code=reason_code,
                    regression=regression,
                )
            elif action == "dismiss":
                admin.dismiss_candidate(identifier, reason=reason, reason_code=reason_code)
            elif action == "remove":
                admin.remove_event(
                    identifier,
                    add_blacklist=False,
                    reason=reason,
                    reason_code=reason_code,
                    regression=regression,
                )
            elif action == "remove-blacklist":
                admin.remove_event(
                    identifier,
                    add_blacklist=True,
                    reason=reason,
                    reason_code=reason_code,
                    regression=regression,
                )
            elif action == "move-to-review":
                admin.move_event_to_review(identifier, note=note, reason_code=reason_code)
            else:
                return f"Azione non supportata: {action}", "error"
    except SystemExit as exc:
        return str(exc), "error"
    except Exception as exc:
        return f"Errore: {exc}", "error"

    message = output.getvalue().strip() or "Azione completata."
    return message, "ok"


class AdminHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/", "/admin"}:
            self.send_error(404)
            return

        qs = parse_qs(parsed.query)
        message = unquote(qs.get("message", [""])[0])
        kind = qs.get("kind", ["ok"])[0]
        self._send_html(_page(message, kind))

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/action":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        message, kind = _perform_action(parse_qs(raw))
        self.send_response(303)
        self.send_header("Location", f"/admin?kind={quote(kind)}&message={quote(message)}")
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[admin] {self.address_string()} - {fmt % args}")

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local admin web UI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    server = ThreadingHTTPServer((HOST, args.port), AdminHandler)
    print(f"Admin locale: http://{HOST}:{args.port}/admin")
    print("Premi Ctrl+C per fermarlo.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAdmin server fermato.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
