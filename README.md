# 🏆 Hackathon Milan Monitor

**Live site → [federicoogallo.github.io/Hackathon-MI](https://federicoogallo.github.io/Hackathon-MI/)**

Automated aggregator for hackathon events in Milan from 10+ heterogeneous sources.  
Filters with LLM (Groq · Llama 3.3 70B, free tier), notifies via Telegram Bot, and publishes a static website on GitHub Pages. Runs locally or on GitHub Actions.

<br>

<p align="center">
  <img src="docs/banner.svg" alt="Upcoming Hackathons in Milan" width="100%">
</p>

<!-- HACKATHON_TABLE_START -->

> **6 hackathons** coming up in Milan · Last updated: Mar 03, 2026 14:21
>
> 🌐 **[View the full website](https://federicoogallo.github.io/Hackathon-MI/)** for search, filters & details.

| Name | Date | Location | Source |
| --- | --- | --- | --- |
| [The Ignition — Opening Gathering: Creative Hackathon - The New Human (Milan & Online)](https://lu.ma/jevwfttk) | 6 Mar 2026 | Google Porta Nuova Isola, Via Federico Confalonieri, 4, 20124 Milano MI, Italia | luma |
| [AI Voice Agent Hackathon powered by ElevenLabs - Milan](https://lu.ma/rgtc75im) | 7 Mar 2026 | Via Polidoro da Caravaggio, 37, 20156 Milano MI, Italia | luma |
| [The Making — Public Sharing: Creative Hackathon - The New Human (Milan)](https://lu.ma/g02myvsa) | 7 Mar 2026 | TrueLayer, Via Joe Colombo, 8, 20124 Milano MI, Italia | luma |
| [EuroGenAI Hackathon League For Social Good: dai giovani,](https://fondazionetriulza.org/eurogenai-hackathon-league-for-social-good-dai-giovani-soluzioni-sostenibili-per-i-territori-con-data-center/) | 13 May 2026 | Milano | web_search |
| [Hack The Boot: Italy's Signature Hackathon](https://hacktheboot.it/) | TBD | Milano | web_search |
| [Harvard HSIL Hackathon 2026 - POLIMI GSoM](https://www.gsom.polimi.it/en/knowledge/harvard-hsil-hackathon-2026/) | TBD | Milano | web_search |

<!-- HACKATHON_TABLE_END -->

<br>

<p align="center">
  <img src="https://img.shields.io/badge/auto--updated-daily-blue?style=for-the-badge" alt="Auto-updated daily">
  <img src="https://img.shields.io/badge/AI--verified-Llama_3.3_70B-purple?style=for-the-badge" alt="AI Verified">
  <img src="https://img.shields.io/badge/sources-10+-green?style=for-the-badge" alt="10+ Sources">
</p>

---

## Architecture

```
Collectors (10 sources in parallel)
        │
        ▼
  Deduplication (SHA-256 URL + fuzzy title via SequenceMatcher > 0.85)
        │
        ▼
  Keyword Pre-filter (62 regex word-boundary patterns: discards "growth hacking", "biohacking", etc.)
        │
        ▼
  LLM Filter (Groq · Llama 3.3 70B, batches of 20, few-shot, threshold 0.7)
        │  Only events PHYSICALLY in Milan — online/remote → discarded
        ▼
  Telegram Notification (summary + link to site)
        │
        ▼
  Persistent Storage (data/events.json)
        │
        ▼
  HTML Page Generation (docs/index.html → GitHub Pages)
        │
        ▼
  README Table Update
```

### Registered Collectors

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 1 | **Eventbrite** | REST API | Requires `EVENTBRITE_API_KEY` |
| 2 | **Eventbrite Web** | HTML scraping (JSON-LD) | Fallback without API key — works in CI |
| 3 | **Google CSE** | Custom Search API | Meta-aggregator: indirectly covers LinkedIn, Meetup, Twitter. Requires `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` |
| 4 | **InnovUp** | HTML scraping | innovup.net/eventi |
| 5 | **Luma** | `__NEXT_DATA__` JSON + HTML fallback | lu.ma |
| 6 | **Devpost** | HTML scraping | Low coverage for Milan |
| 7 | **PoliHub** | HTML scraping | Blocked by WAF (indirectly covered by Google CSE) |
| 8 | **Universities** | HTML scraping | PoliMi, Bocconi, Bicocca (independent parsers) |
| 9 | **Reddit** | PRAW (official API) | r/ItalyInformatica + r/italy. Requires `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |
| 10 | **Taikai** | HTML scraping | taikai.network — international tech hackathons |

---

## Local Setup

### 1. Clone and create virtual environment

```bash
git clone https://github.com/federicoogallo/Hackathon-MI.git
cd Hackathon-MI

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` with your keys. **No key is mandatory** — collectors without a key are silently skipped:

| Variable | How to obtain |
|----------|---------------|
| `EVENTBRITE_API_KEY` | [eventbrite.com/platform/api](https://www.eventbrite.com/platform/api) → create an app → copy the Private token |
| `GOOGLE_CSE_API_KEY` | [console.cloud.google.com](https://console.cloud.google.com/) → APIs & Services → Credentials → Create API Key → enable "Custom Search JSON API" |
| `GOOGLE_CSE_CX` | [programmablesearchengine.google.com](https://programmablesearchengine.google.com/) → create a search engine → copy the ID (cx) |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com/) → API Keys → Create (free, no credit card required) |
| `REDDIT_CLIENT_ID` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → create "script" app → copy the ID below the name |
| `REDDIT_CLIENT_SECRET` | Same Reddit page → copy the "secret" |
| `TELEGRAM_BOT_TOKEN` | Talk to [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → copy the token |
| `TELEGRAM_CHAT_ID` | Send a message to the bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` → grab `chat.id` |

### 3. Run

```bash
# Dry-run (no notifications, logs only)
python main.py --dry-run

# Full run (with Telegram notifications)
python main.py
```

### 4. Tests

```bash
python -m pytest tests/ -v
```

---

## Deploy on GitHub Actions

### 1. Fork/push the repository

### 2. Configure Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add all keys from `.env`.

### 3. Enable GitHub Pages

Go to **Settings → Pages** and set:
- **Source**: `Deploy from a branch`
- **Branch**: `main` · **Folder**: `/docs`

The site will be available at `https://<username>.github.io/<repo>/`.

### 4. Enable the workflow

The workflow is in `.github/workflows/check_hackathons.yml`:
- **Cron**: daily at 12:00 CET (`0 11 * * *` UTC)
- **Manual**: from the "Actions" tab → "Run workflow"
- Auto-commits `data/events.json`, `docs/index.html`, and `README.md` on each run

---

## Telegram Bot

`bot.py` runs a long-polling bot with the following commands:

| Command | Description |
|---------|-------------|
| `/scan` | Trigger a manual scan |
| `/help` | List commands |

The bot automatically sends a **summary** after each scan (number of new hackathons + link to site).  
Full event details are available on the GitHub Pages site and in the README table above.

Local start (activate `.venv` and run `python bot.py`):

```bash
./scripts/start_bot.sh
```

Auto-start on macOS login (launchd):

```bash
./scripts/install_launchd.sh
```

Restricted to the configured `TELEGRAM_CHAT_ID` — all other messages are automatically rejected.

---

## Adding a New Collector

1. Create `collectors/my_collector.py`:

```python
from models import BaseCollector, HackathonEvent

class MyCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "my_collector"

    def collect(self) -> list[HackathonEvent]:
        # Scraping/API logic here
        return [
            HackathonEvent(
                title="...",
                url="...",
                source=self.name,
            )
        ]
```

2. Register it in `main.py` → `get_collectors()`:

```python
from collectors.my_collector import MyCollector

def get_collectors():
    return [
        # ... existing collectors ...
        MyCollector(),
    ]
```

3. Add a test in `tests/test_collectors.py`.

---

## Project Structure

```
hackathon-monitor/
├── main.py                  # Pipeline orchestrator
├── config.py                # Centralized configuration
├── models.py                # HackathonEvent, BaseCollector
├── requirements.txt
├── .env.example
├── .gitignore
├── collectors/
│   ├── eventbrite.py
│   ├── eventbrite_web.py    # HTML scraping (no API key, CI-friendly)
│   ├── google_cse.py
│   ├── innovup.py
│   ├── luma.py
│   ├── devpost.py
│   ├── polihub.py
│   ├── universities.py
│   ├── reddit.py
│   └── taikai.py
├── filters/
│   ├── keyword_filter.py    # Regex pre-filter
│   └── llm_filter.py        # Groq · Llama 3.3 70B classifier
├── notifiers/
│   └── telegram.py          # Telegram Bot
├── storage/
│   └── json_store.py        # Persistence + 2-level dedup
├── utils/
│   ├── http.py              # HTTP client with retry/backoff
│   ├── html_export.py       # GitHub Pages generator
│   └── readme_export.py     # README table generator
├── data/
│   └── events.json          # Event history (auto-generated)
├── docs/
│   └── index.html           # GitHub Pages site (auto-generated)
├── tests/
│   ├── test_models.py
│   ├── test_storage.py
│   ├── test_filters.py
│   ├── test_collectors.py
│   └── test_pipeline.py
└── .github/
    └── workflows/
        └── check_hackathons.yml
```

---

## Known Limitations

- **PoliHub**: blocked by WAF/Cloudflare (403). Indirectly covered by Google CSE.
- **Twitter/X**: Free Tier API is write-only. Indirectly covered by Google CSE (`site:twitter.com`).
- **LinkedIn**: no public API for events. Covered by Google CSE (`site:linkedin.com/events`).
- **Google CSE**: free quota of 100 queries/day (sufficient for 1 run/day with 8 queries).
- **Groq free tier**: 14,400 req/day, 30 RPM. Without `GROQ_API_KEY` the LLM filter is skipped (keyword filter only).

---

## License

MIT

---

<p align="center">
  <sub>🤖 This project is <strong>vibe coded</strong> — built with AI-assisted development to simplify the search for hackathons in Milan.<br>
  The goal is to remove the friction of manually browsing dozens of sites, so you can focus on hacking.</sub>
</p>
