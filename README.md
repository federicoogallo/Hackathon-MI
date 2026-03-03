# 🏆 Hackathon Milan Monitor

**Live site → [federicoogallo.github.io/Hackathon-MI](https://federicoogallo.github.io/Hackathon-MI/)**

Automated aggregator for hackathon events in Milan from 10+ heterogeneous sources.  
Filters with LLM, notifies via Telegram Bot, and publishes a static website on GitHub Pages. Runs locally or on GitHub Actions.

<br>

<p align="center">
  <img src="docs/banner.svg" alt="Upcoming Hackathons in Milan" width="100%">
</p>

<!-- HACKATHON_TABLE_START -->

> **22 hackathons** coming up in Milan · Last updated: Mar 03, 2026 15:50
>
> 🌐 **[View the full website](https://federicoogallo.github.io/Hackathon-MI/)** for search, filters & details.

| Name | Date | Location | Source |
| --- | --- | --- | --- |
| [HackTrack EU - Discover European Hackathons](https://hacktrack-eu.vercel.app/) | 5 Mar 2026 | Milano | web_search |
| [The Ignition — Opening Gathering: Creative Hackathon - The New Human (Milan & Online)](https://lu.ma/jevwfttk) | 6 Mar 2026 | Google Porta Nuova Isola, Via Federico Confalonieri, 4, 20124 Milano MI, Italia | luma |
| [The New Human - ART+TECH Festival 2026 DAY 1  — THE IGNITION](https://www.eventbrite.com/e/the-new-human-arttech-festival-2026-day-1-the-ignition-tickets-1984074315688) | 6 Mar 2026 | 4 Via Federico Confalonieri, Milano | eventbrite_web |
| [AI Voice Agent Hackathon powered by ElevenLabs - Milan](https://lu.ma/rgtc75im) | 7 Mar 2026 | Via Polidoro da Caravaggio, 37, 20156 Milano MI, Italia | luma |
| [The Making — Public Sharing: Creative Hackathon - The New Human (Milan)](https://lu.ma/g02myvsa) | 7 Mar 2026 | TrueLayer, Via Joe Colombo, 8, 20124 Milano MI, Italia | luma |
| [HSIL Hackathon 2026 – Building High-Value Health Systems: Leveraging AI - Human Technopole](https://humantechnopole.it/en/trainings/hsil-hackathon-2026-building-high-value-health-systems-leveraging-ai/) | 10 Apr 2026 | Milano | web_search |
| [Progetti e iniziative di Open Innovation \| Università degli Studi di Milano Statale](https://www.unimi.it/it/terza-missione/innovazione-ricerca-e-imprese/progetti-e-iniziative-di-open-innovation) | 10 Apr 2026 | Milano | web_search |
| [HSIL Hackathon 2026 – Building High-Value Health Systems ...](https://www.linkedin.com/posts/htechnopole_hsil-hackathon-2026-building-high-value-activity-7433064159564570624-n-sT) | 10 Apr 2026 | Milano | web_search |
| [Il Wikimedia Hackathon 2026 arriva a Milano - Wikimedia Italia](https://www.wikimedia.it/news/il-wikimedia-hackathon-2026-arriva-a-milano/) | 1 May 2026 | Milano | web_search |
| [Wikimedia - Save the date! The 2026 edition of the Wikimedia Hackathon ...](https://www.facebook.com/WikimediaCH/photos/-save-the-datethe-2026-edition-of-the-wikimedia-hackathon-is-set-to-take-place-f/1317754673721766/) | 1 May 2026 | Milano | web_search |
| [EuroGenAI Hackathon League For Social Good: dai giovani,](https://fondazionetriulza.org/eurogenai-hackathon-league-for-social-good-dai-giovani-soluzioni-sostenibili-per-i-territori-con-data-center/) | 13 May 2026 | Milano | web_search |
| [Free & $21,000 Prize, Blockchain & Data 24hours Hackathon @Milan](https://www.hackathon.com/event/free-and-21000-prize-blockchain-and-data-24hours-hackathon-milan-52262112385) | 24 Nov 2026 | Milano | web_search |
| [Hack The Boot: Italy's Signature Hackathon](https://hacktheboot.it/) | TBD | Milano | web_search |
| [Harvard HSIL Hackathon 2026 - POLIMI GSoM](https://www.gsom.polimi.it/en/knowledge/harvard-hsil-hackathon-2026/) | TBD | Milano | web_search |
| [HackAthena'26](https://hackathena-26.devfolio.co/) | TBD | Milano | devfolio |
| [HACKANOVA 5.O](https://hackanova-5-0.devfolio.co/) | TBD | Milano | devfolio |
| [FastwebAI Hackathon a Milano \| Fastweb](https://www.fastweb.it/fastwebai-hackathon/) | TBD | Milano | web_search |
| [Italian Hackathon League: Milano ospita l'ultima sfida sull'AI vocale](https://www.innovami.news/2026/01/30/milano-ospita-la-sfida-decisiva-dellitalian-hackathon-league-innovazione-e-ai-vocale-in-gioco/) | TBD | Milano | web_search |
| [Global legal Hackathon: tre giorni a Milano per sfidarsi a colpi di coding](https://blblex.it/rassegna_stampa.php?id=788&lang=en) | TBD | Milano | web_search |
| [Hack2BRIDGE expands to Italy with a hackathon aimed at Mobility, Transport and Automotive \| European Cluster Collaboration Platform](https://www.clustercollaboration.eu/content/hack2bridge-expands-italy-hackathon-aimed-mobility-transport-and-automotive) | TBD | Milano | web_search |
| [Platform \| LA CTF](https://platform.2026.lac.tf/) | TBD | Milano | web_search |
| [Con FOSS4G-IT & OSMit 2026 i software e i dati geospaziali](https://www.wikimedia.it/news/con-foss4g-it-osmit-2026-i-software-e-i-dati-geospaziali-liberi-tornano-a-trento/) | TBD | Milano | web_search |

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
Collectors (26 sources in parallel)
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

<details>
<summary><strong>Registered Collectors</strong></summary>

#### Original Sources

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 1 | **Eventbrite** | REST API | Requires `EVENTBRITE_API_KEY` |
| 2 | **Eventbrite Web** | HTML scraping (JSON-LD) | Fallback without API key — works in CI |
| 3 | **Google CSE** | Custom Search API | Meta-aggregator (10 queries, IT + EN). Requires `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` |
| 4 | **Web Search (DDG)** | DuckDuckGo DDGS | Free meta-aggregator, 21 queries (IT + EN + site-specific) |
| 5 | **InnovUp** | HTML scraping | innovup.net/eventi |
| 6 | **Luma** | `__NEXT_DATA__` JSON + HTML fallback | lu.ma |
| 7 | **Devpost** | HTML scraping | Low coverage for Milan |
| 8 | **PoliHub** | HTML scraping | Blocked by WAF (indirectly covered by Google CSE) |
| 9 | **Universities** | HTML scraping | PoliMi, Bocconi, Bicocca, Cattolica, IULM, San Raffaele |
| 10 | **Reddit** | PRAW (official API) | r/ItalyInformatica + r/italy. Requires `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |
| 11 | **Taikai** | HTML scraping | taikai.network — international tech hackathons |

#### High-Impact New Sources

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 12 | **Meetup** | GraphQL API + HTML fallback | Milan geo-search (30 km). Optional `MEETUP_API_KEY` |
| 13 | **Hackathon.com** | HTML scraping | hackathon.com/city/italy/milan + /country/italy |
| 14 | **MLH** | HTML + `__NEXT_DATA__` + JSON | Major League Hacking seasons. Italy geo-filter |
| 15 | **Codemotion** | HTML scraping | community.codemotion.com — largest Italian tech community |
| 16 | **Talent Garden** | HTML scraping | TAG Milano campuses (Calabiana, Isola). IT + EN pages |
| 17 | **Cariplo Factory** | HTML scraping | cariplofactory.it/eventi — Fondazione Cariplo hub |
| 18 | **Startup Italia** | RSS + HTML fallback | startupitalia.eu — Italian startup media |

#### International Platforms

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 19 | **DoraHacks** | REST API | Web3/blockchain hackathons. Italy geo-filter |
| 20 | **HackerEarth** | HTML scraping | hackerearth.com/challenges — online + onsite |
| 21 | **Devfolio** | `__NEXT_DATA__` + HTML fallback | Growing EU platform. Italy geo-filter |
| 22 | **ChallengeRocket** | HTML scraping | EU/CEE hackathons + challenges |
| 23 | **Unstop** | HTML + Angular JSON | Ex-Dare2Compete. Italy geo-filter |
| 24 | **Lablab.ai** | `__NEXT_DATA__` + HTML | AI hackathons — LLM filters for Milan relevance |

#### Institutional Sources

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 25 | **Comune di Milano** | HTML scraping | comune.milano.it innovation page — civic hackathons |
| 26 | **Camera di Commercio** | HTML scraping | milomb.camcom.it — events + grants |
| 27 | **Regione Lombardia** | HTML scraping | Open Innovation Lombardia portal |

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
- Auto-commits `data/events.json`, `docs/index.html`, and `README.md` on each run

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

Local start (activate `.venv` and run `python bot.py`):

```bash
./scripts/start_bot.sh
```

Auto-start on macOS login (launchd):

```bash
./scripts/install_launchd.sh
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

</details>

---

<details>
<summary><strong>Known Limitations</strong></summary>

- **PoliHub**: blocked by WAF/Cloudflare (403). Indirectly covered by Google CSE.
- **Twitter/X**: Free Tier API is write-only. Indirectly covered by Google CSE (`site:twitter.com`).
- **LinkedIn**: no public API for events. Covered by Google CSE (`site:linkedin.com/events`).
- **Google CSE**: free quota of 100 queries/day (sufficient for 1 run/day with 8 queries).
- **Groq free tier**: 14,400 req/day, 30 RPM. Without `GROQ_API_KEY` the LLM filter is skipped (keyword filter only).

</details>

---

<p align="center">
  <sub>🤖 This project is <strong>vibe coded</strong> — built with AI-assisted development to simplify the search for hackathons in Milan.<br>
  The goal is to remove the friction of manually browsing dozens of sites, so you can focus on hacking.</sub>
</p>
