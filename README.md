# 🏆 Hackathon Milan Monitor

**Live site → [federicoogallo.github.io/Hackathon-MI](https://federicoogallo.github.io/Hackathon-MI/)**

Automated aggregator for hackathon events in Milan from 28 heterogeneous sources.  
Filters with LLM, routes uncertain candidates to manual review, notifies via Telegram Bot, and publishes a static website on GitHub Pages. Runs locally or on GitHub Actions.

<br>

<p align="center">
  <img src="docs/banner.svg" alt="Upcoming Hackathons in Milan" width="100%">
</p>

<!-- HACKATHON_TABLE_START -->

> **4 hackathons** coming up in Milan · Last updated: May 03, 2026 13:37
>
> 🌐 **[View the full website](https://federicoogallo.github.io/Hackathon-MI/)** for search, filters & details.

| Name | Date | Location | Source |
| --- | --- | --- | --- |
| [GDG AI HACK - 2026](https://gdg.community.dev/events/details/google-gdg-on-campus-polytechnic-university-of-milan-presents-gdg-ai-hack-2026/) | 9 May 2026 | Randstad Box, 5 Via San Vigilio | gdg_community |
| [Hackathon Leonardo - Space Edition - telespazio.com](https://www.telespazio.com/en/careers/hackathon-space-edition) | 9 May 2026 | Milano | web_search |
| [ALSO Hackathon](https://www.linkedin.com/posts/alsogroup_registration-is-now-open-for-the-also-activity-7440736410866741248-VjKz) | 28 May 2026 | Milano | web_search |
| [Hack The Boot: Italy's Signature Hackathon](https://hacktheboot.it/) | TBD | Milano | web_search |

<!-- HACKATHON_TABLE_END -->

<br>

<p align="center">
  <img src="https://img.shields.io/badge/auto--updated-daily-blue?style=for-the-badge" alt="Auto-updated daily">
  <img src="https://img.shields.io/badge/AI--verified-Llama_3.3_70B-purple?style=for-the-badge" alt="AI Verified">
  <img src="https://img.shields.io/badge/sources-28-green?style=for-the-badge" alt="28 Sources">
</p>

---

## Architecture

```
Collectors (28 sources in parallel)
        │
        ▼
  4-Level Deduplication
    L1  SHA-256(URL) exact match + alternate_urls index
    L2  Fuzzy title (SequenceMatcher ≥ 0.75)
    L3  Same date + shared distinctive keywords
    L4  Cross-reference (title words found in other event's text)
        │
        ▼
  Keyword Pre-filter (117+ regex patterns, junk-URL blocklist, past-year check)
        │
        ▼
  LLM Filter (Groq · Llama 3.3 70B, batches of 5, few-shot, threshold 0.7)
        │  Only events PHYSICALLY in Milan — online/remote → discarded
        ├── Low-confidence candidates → Manual Review Queue
        │       data/review_queue.json + docs/review.html
        ▼
  Telegram Notification (summary + link to site)
        │
        ▼
  Persistent Storage (data/events.json)
        │
        ▼
  HTML Page (docs/index.html → GitHub Pages) + README Table
```

<details>
<summary><strong>Registered Collectors</strong></summary>

#### Original Sources

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 1 | **Eventbrite** | REST API | Requires `EVENTBRITE_API_KEY` |
| 2 | **Eventbrite Web** | HTML scraping (JSON-LD) | Fallback without API key — works in CI |
| 3 | **Web Search (DDG)** | DuckDuckGo DDGS | Free meta-aggregator, 21 queries (IT + EN + site-specific) |
| 4 | **InnovUp** | HTML scraping | innovup.net/eventi |
| 5 | **Luma** | `__NEXT_DATA__` JSON + HTML fallback | lu.ma |
| 6 | **Devpost** | HTML scraping | Low coverage for Milan |
| 7 | **PoliHub** | HTML scraping | Blocked by WAF (covered by DDG web search) |
| 8 | **Universities** | HTML scraping | PoliMi, Bocconi, Bicocca, Cattolica, IULM, San Raffaele |
| 9 | **Reddit** | PRAW (official API) | r/ItalyInformatica + r/italy. Requires `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |
| 10 | **Taikai** | HTML scraping | taikai.network — international tech hackathons |

#### High-Impact New Sources

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 11 | **Meetup** | GraphQL API + HTML fallback | Milan geo-search (30 km). Optional `MEETUP_API_KEY` |
| 12 | **Hackathon.com** | HTML scraping | hackathon.com/city/italy/milan + /country/italy |
| 13 | **MLH** | HTML + `__NEXT_DATA__` + JSON | Major League Hacking seasons. Italy geo-filter |
| 14 | **Codemotion** | HTML scraping | community.codemotion.com — largest Italian tech community |
| 15 | **Talent Garden** | HTML scraping | TAG Milano campuses (Calabiana, Isola). IT + EN pages |
| 16 | **Cariplo Factory** | HTML scraping | cariplofactory.it/eventi — Fondazione Cariplo hub |
| 17 | **Startup Italia** | RSS + HTML fallback | startupitalia.eu — Italian startup media |

#### International Platforms

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 18 | **DoraHacks** | REST API | Web3/blockchain hackathons. Italy geo-filter |
| 19 | **HackerEarth** | HTML scraping | hackerearth.com/challenges — online + onsite |
| 20 | **Devfolio** | `__NEXT_DATA__` + HTML fallback | Growing EU platform. Italy geo-filter |
| 21 | **ChallengeRocket** | HTML scraping | EU/CEE hackathons + challenges |
| 22 | **Unstop** | HTML + Angular JSON | Ex-Dare2Compete. Italy geo-filter |
| 23 | **Lablab.ai** | `__NEXT_DATA__` + HTML | AI hackathons — LLM filters for Milan relevance |

#### Institutional Sources

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 24 | **Comune di Milano** | HTML scraping | comune.milano.it innovation page — civic hackathons |
| 25 | **Camera di Commercio** | HTML scraping | milomb.camcom.it — events + grants |
| 26 | **Regione Lombardia** | HTML scraping | Open Innovation Lombardia portal |

#### Community Platforms

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 27 | **GDG Community** | HTML scraping + JSON-LD | gdg.community.dev — Google Developer Groups Milan chapters |

#### Focus Sources

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 28 | **Telespazio** | HTML scraping | Leonardo/Telespazio career hackathon pages |

</details>

---

<details>
<summary><strong>Local Setup</strong></summary>

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

Edit `.env` with your keys. The monitor can run without paid services, but `GROQ_API_KEY` is strongly recommended: without it, new candidates cannot be AI-verified and the pipeline preserves the existing archive instead of adding unverified events.

| Variable | How to obtain |
|----------|---------------|
| `EVENTBRITE_API_KEY` | [eventbrite.com/platform/api](https://www.eventbrite.com/platform/api) → create an app → copy the Private token |
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

### 5. Review uncertain candidates

```bash
# Show candidates waiting for manual review
python scripts/review_candidate.py list

# Publish a candidate into data/events.json
python scripts/review_candidate.py approve <candidate-id>

# Suppress a candidate from future queues
python scripts/review_candidate.py reject <candidate-id>
```

Manual approvals rebuild the static site and README immediately. The public review queue is available at `docs/review.html`.

### 6. Pre-render static site (SSG)

```bash
python scripts/build_static_site.py
```

This generates `docs/index.html` and `docs/review.html` with content already embedded in HTML, then updates the README table from `data/events.json`, so content is visible before any JavaScript runs.

</details>

---

<details>
<summary><strong>Deploy on GitHub Actions</strong></summary>

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
- Auto-commits `data/events.json`, `data/review_queue.json`, `data/review_decisions.json`, `docs/index.html`, `docs/review.html`, and `README.md` on each run

</details>

---

<details>
<summary><strong>Telegram Bot</strong></summary>

`bot.py` runs a long-polling bot with the following commands:

| Command | Description |
|---------|-------------|
| `/scan` | Trigger a manual scan |
| `/help` | List commands |

The bot automatically sends a **summary** after each scan (number of new hackathons + link to site).  
Full event details are available on the GitHub Pages site and in the README table above.

Local start:

```bash
source .venv/bin/activate
python bot.py
```

Restricted to the configured `TELEGRAM_CHAT_ID` — all other messages are automatically rejected.

</details>

---

<details>
<summary><strong>Adding a New Collector</strong></summary>

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

</details>

---

<details>
<summary><strong>Project Structure</strong></summary>

```
hackathon-monitor/
├── main.py                  # Pipeline orchestrator
├── bot.py                   # Telegram bot (long-polling)
├── config.py                # Centralized configuration
├── models.py                # HackathonEvent, BaseCollector
├── requirements.txt
├── .env.example
├── .gitignore
├── collectors/              # 28 source modules
│   ├── eventbrite.py        # REST API
│   ├── eventbrite_web.py    # HTML scraping (no API key, CI-friendly)
│   ├── web_search.py        # DuckDuckGo meta-aggregator (21 queries)
│   ├── luma.py              # __NEXT_DATA__ + HTML
│   ├── meetup.py            # GraphQL API
│   ├── ...                  # 20 more (see Registered Collectors above)
│   └── regione_lombardia.py
├── filters/
│   ├── keyword_filter.py    # Regex pre-filter + junk-URL blocklist
│   └── llm_filter.py        # Groq · Llama 3.3 70B classifier
├── notifiers/
│   └── telegram.py          # Telegram notifications
├── storage/
│   └── json_store.py        # Persistence + 4-level dedup
├── utils/
│   ├── http.py              # HTTP client with retry/backoff
│   ├── html_export.py       # GitHub Pages generator
│   ├── readme_export.py     # README table generator
│   └── review_queue.py      # Manual review queue persistence
├── scripts/
│   ├── review_candidate.py  # Manual approve/reject workflow
│   ├── slow_classify.py     # Recovery: classify one-by-one with rate-limit safety
│   ├── collect_only.py      # Debug: collect + keyword filter, save candidates
│   └── extract_dates.py     # Backfill missing event dates via LLM
├── data/
│   ├── events.json          # Event history (auto-generated)
│   ├── review_queue.json    # Low-confidence candidates
│   └── review_decisions.json # Manual approve/reject decisions
├── docs/
│   ├── index.html           # GitHub Pages site (auto-generated)
│   ├── review.html          # Public manual-review queue (auto-generated)
│   └── banner.svg           # Header banner
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

</details>

---

<details>
<summary><strong>Known Limitations</strong></summary>

- **PoliHub**: blocked by WAF/Cloudflare (403). Indirectly covered by DDG web search.
- **Twitter/X**: Free Tier API is write-only. Covered by DDG web search (`site:twitter.com`).
- **LinkedIn**: no public API for events. Covered by DDG web search (`site:linkedin.com/events`).
- **Groq free tier**: 14,400 req/day, 30 RPM. Without `GROQ_API_KEY`, new candidates are not AI-verified; if candidates need LLM validation, the pipeline preserves the existing archive and records the issue in `data/last_report.json`.
- **Manual review**: low-confidence candidates are not published automatically; they are written to `data/review_queue.json` and can be approved or rejected with `scripts/review_candidate.py`.
- **Run diagnostics**: `data/last_report.json` includes per-collector status, event counts, durations, and errors. GitHub Actions uploads it as the `hackathon-monitor-report` artifact.
- **Some collectors** may return 404/403 temporarily due to site changes — they fail gracefully and don't block the pipeline.

</details>

---

## Contributing

Contributions are warmly welcome!

- 🔌 **Add a new source** — write a collector and open a PR
- 🐛 **Report a wrong entry** — open an issue with the event link
- 🧠 **Improve LLM filtering** — better prompts, fewer false positives
- 📍 **Spot a missing hackathon?** — [open an issue](https://github.com/federicoogallo/Hackathon-MI/issues/new?title=Missing+hackathon)

---

> [!WARNING]
> **Early-stage project.** The dataset may contain inaccuracies — past events, duplicates, events outside Milan, or missing hackathons. Data is scraped and filtered automatically; false positives and false negatives are expected. Always verify details at the original source before making plans.

---

<div align="center">

<sub>🧑‍💻 **vibe coded** — built with AI-assisted development to simplify the search for hackathons in Milan.<br>
The goal is to remove the friction of manually browsing dozens of sites, so you can focus on hacking.</sub>

</div>
