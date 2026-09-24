# 🏆 Hackathon Milan Monitor

**Live site → [hackathon-milano.vercel.app](https://hackathon-milano.vercel.app/)**

<sub>The GitHub Pages build at [federicoogallo.github.io/Hackathon-MI](https://federicoogallo.github.io/Hackathon-MI/) is a mirror; it declares a `canonical` link to the Vercel site so search engines can identify the primary version.</sub>

Automated aggregator for hackathon events in Milan with **28 registered source integrations**.
Collects and deduplicates candidates, applies rules and LLM classification, routes uncertain entries to manual review, and publishes a Next.js website on Vercel with an optional GitHub Pages mirror. Telegram delivers scan summaries; the weekly email integration is implemented but stays disabled until its private services are configured.

The source count describes implemented integrations, not a guarantee that all sources are available on every scan. Always check event details with the organizer.

<br>

<p align="center">
  <img src="docs/banner.svg" alt="Upcoming Hackathons in Milan" width="100%">
</p>

<!-- HACKATHON_TABLE_START -->

> **10 hackathons** coming up in Milan · Last updated: Sep 24, 2026 17:49 CEST
>
> **[View the full website](https://hackathon-milano.vercel.app/)** for search, filters and details.

| Name | Date | Location | Source |
| --- | --- | --- | --- |
| [Milano Finanza Hackathon](https://it.linkedin.com/posts/milano-finanza_hackathon-activity-7504195623886274560-6lsh) | 28 Sep 2026 | Milano | Web search |
| [Italian Game Jam](https://italiangamejam.it/) | 3 Oct 2026 | Milano | Web search |
| [BCG Platinion Hackathon - Fighting World Hunger \| October 16-17, 2026](https://www.bcgplatinion.com/hackathon) | 16 Oct 2026 | Milano | Web search |
| [Hackathon ServiceNow Milano](https://rsvp.servicenow.com/hackathon-milano/begin) | 20 Oct 2026 | Milano | Web search |
| [Hackathon per universitari Talenti STEM per l'Innovazione Sociale](https://fondazionetriulza.org/hackathon-talenti-stem-per-linnovazione-sociale-deadline-19-ottobre/) | 29 Oct 2026 | Milano | Web search |
| [NASA Space Apps Challenge – Milano](https://www.instagram.com/milano_spaceapps/) | 14 Nov 2026 | Milano | Web search |
| [Oliver Wyman Data & Analytics Hackathon Challenge Milan](https://careers.marsh.com/global/en/event/6a8d475341b49ecd3616675a/Oliver-Wyman-Data-Analytics-Hackathon-Challenge-Milan) | 20 Nov 2026 | Milano | Web search |
| [NTT DATA IkigAIverse](https://www.bo-om.it/nttdata_hackathon/) | 3 Dec 2026 | Milano | Web search |
| [GLAM Tool Hospital/Wikimedia Hackathon, Milan 2026](https://meta.wikimedia.org/wiki/GLAM_Tool_Hospital/Wikimedia_Hackathon,_Milan_2026) | TBD | Milano | Web search |
| [Innovation Challenge 2026 – Soluzioni per evitare la disillusione dell’AI](https://polimi.it/il-politecnico/eventi?tx_filterevent_newsfilterevent%5Bcontroller%5D=News&tx_filterevent_newsfilterevent%5BcurrentPage%5D=2&cHash=5b807b8396644197677d4ce88a500271) | 21settembre2026 | Milano | Universities |

<!-- HACKATHON_TABLE_END -->

<br>

<p align="center">
  <img src="https://img.shields.io/badge/collection-daily-blue?style=for-the-badge" alt="Daily collection schedule">
  <img src="https://img.shields.io/badge/filtering-AI--assisted-purple?style=for-the-badge" alt="AI-assisted filtering">
  <img src="https://img.shields.io/badge/sources-28-green?style=for-the-badge" alt="28 registered integrations">
</p>

---

## Website

The frontend is built with **Next.js 15, React 19 and Motion**, using a responsive interface centered on finding and comparing events.

- **Discovery:** search titles, locations and complete descriptions; filter by date and source; choose chronological or alphabetical ordering and grid or list views.
- **Personal tools:** share searches through their URLs, save events locally and download a calendar entry for dated events. No account is required; saved events stay in the current browser.
- **Visual experience:** an architectural Milan scene and a radar connected to the next events. It advances every seven seconds, stops on interaction and can be resumed explicitly. Motion respects reduced-motion preferences.
- **Themes and accessibility:** System, Light and Dark themes with a persistent choice, keyboard navigation, visible focus and responsive layouts.
- **Identity and search:** an abstract radar mark with favicon/device variants, social preview artwork, Italian metadata, canonical URLs, `WebSite` structured data, `robots.txt` and a sitemap. Search results may retain older titles or icons until the next crawl.
- **Usage metrics:** optional Vercel Web Analytics for page views and estimated visitors, disabled until enabled on a free Hobby team. Local project reports stay outside Git.
- **Weekly email:** a consent-based signup with confirmation, unsubscribe support and a weekly digest of new events. The prompt currently appears to all visitors for evaluation; actual subscriptions remain disabled without complete Brevo Free/Redis configuration.

See the [newsletter setup](docs/newsletter.md) and [security policy](SECURITY.md).

---

## Architecture

```text
Collectors (28 registered integrations, parallel collection)
        │
        ▼
  4-Level Store Deduplication
    L1  SHA-256(URL) exact match + alternate_urls index
    L2  Fuzzy title (SequenceMatcher ≥ 0.75)
    L3  Same date + shared distinctive keywords
    L4  Cross-reference (title words found in another event's text)
        │
        ▼
  Keyword and Date Pre-filters
    Positive/negative patterns, junk-URL blocklist, past-event checks
        │
        ▼
  LLM Classification (Groq · GPT-OSS 120B + Qwen 3.6 27B fallback)
    Batches of 5, confidence threshold 0.7; Milan relevance checks
        ├── Uncertain candidates → Manual Review Queue
        │       data/review_queue.json + public review page
        ▼
  Post-classification Quality Gates and Semantic Deduplication
        │
        ▼
  Persistent Archive (data/events.json)
        ├── Next.js website → Vercel build
        ├── Static mirror → docs/index.html + docs/review.html
        ├── Generated README event table
        ├── Telegram scan summary (when configured)
        └── Weekly email digest (separate authorized Vercel Cron)
```

The pipeline targets in-person hackathons in Milan and the monitored surrounding area. These filters reduce irrelevant results; they do not establish that every event has been manually verified. The website reads the public archive, while email addresses and delivery state stay in private services.

<details>
<summary><strong>Registered Collectors</strong></summary>

This inventory matches `main.py::get_collectors`. Methods describe the implementations; current availability is recorded in each scan report.

#### Original Sources

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 1 | **Eventbrite** | REST API | Requires `EVENTBRITE_API_KEY` |
| 2 | **Eventbrite Web** | HTML scraping (JSON-LD) | JSON-LD fallback without an API key |
| 3 | **Web Search (DDG)** | DuckDuckGo DDGS | 22 configured queries (IT + EN + site-specific) |
| 4 | **InnovUp** | HTML scraping | innovup.net/eventi |
| 5 | **Luma** | `__NEXT_DATA__` JSON + HTML fallback | lu.ma |
| 6 | **Devpost** | HTML scraping | International listings filtered for Milan relevance |
| 7 | **PoliHub** | HTML scraping | Direct collector; results may also be discovered through web search |
| 8 | **Universities** | HTML scraping | PoliMi, Bocconi, Bicocca, Cattolica, IULM, San Raffaele |
| 9 | **Reddit** | PRAW (official API) | r/ItalyInformatica + r/italy. Requires `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |
| 10 | **Taikai** | HTML scraping | taikai.network — international tech hackathons |

#### Local and Developer Ecosystems

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 11 | **Meetup** | GraphQL API + HTML fallback | Milan geo-search (30 km). Optional `MEETUP_API_KEY` |
| 12 | **Hackathon.com** | HTML scraping | hackathon.com/city/italy/milan + /country/italy |
| 13 | **MLH** | HTML + `__NEXT_DATA__` + JSON | Major League Hacking seasons. Italy geo-filter |
| 14 | **Codemotion** | HTML scraping | community.codemotion.com — developer community events |
| 15 | **Talent Garden** | HTML scraping | TAG Milano campuses (Calabiana, Isola). IT + EN pages |
| 16 | **Cariplo Factory** | HTML scraping | cariplofactory.it/eventi — Fondazione Cariplo hub |
| 17 | **Startup Italia** | RSS + HTML fallback | startupitalia.eu — Italian startup media |

#### International Platforms

| # | Source | Method | Notes |
|---|--------|--------|-------|
| 18 | **DoraHacks** | REST API | Web3/blockchain hackathons. Italy geo-filter |
| 19 | **HackerEarth** | HTML scraping | hackerearth.com/challenges — online + onsite |
| 20 | **Devfolio** | `__NEXT_DATA__` + HTML fallback | Platform listings with an Italy geo-filter |
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

### 1. Clone and run the website

Use **Node.js 22 LTS** for the frontend, matching CI. The checked-in event archive is enough to browse locally; Python collection keys are not required.

```bash
git clone https://github.com/federicoogallo/Hackathon-MI.git
cd Hackathon-MI
npm ci
npm run dev
```

Open [localhost:3000](http://localhost:3000). For a production preview, stop the development server, then run `npm run build` and `npm run start`. `npm ci` installs the committed lockfile; see `package.json` for the current dependency versions.

### 2. Create the Python environment

Use **Python 3.12**, matching the collection workflow. From the repository directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 3. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` with the credentials needed by your integrations. Without working `GROQ_API_KEY` access, candidates requiring LLM validation cannot be published as verified events; if all classification results fail, the pipeline preserves the existing archive. Keep real credentials out of Git.

| Variable | How to obtain |
|----------|---------------|
| `EVENTBRITE_API_KEY` | [eventbrite.com/platform/api](https://www.eventbrite.com/platform/api) → create an app → copy the Private token |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com/) → API Keys → create a key for your account |
| `REDDIT_CLIENT_ID` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → create "script" app → copy the ID below the name |
| `REDDIT_CLIENT_SECRET` | Same Reddit page → copy the "secret" |
| `TELEGRAM_BOT_TOKEN` | Talk to [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → copy the token |
| `TELEGRAM_CHAT_ID` | ID of the chat authorized to receive summaries and control the bot |
| `MEETUP_API_KEY` | Optional Meetup API access; HTML fallback is available |
| `LLM_MODEL`, `LLM_MODEL_FALLBACKS` | Optional supported model IDs; defaults are in `config.py` |
| `GITHUB_REPO_URL` | Repository used for contribution links |
| `NEXT_PUBLIC_SITE_URL` | Canonical public origin; defaults to the current Vercel site |

### 4. Run the pipeline

```bash
# Run collection without Telegram notifications
python main.py --dry-run

# Full run (with Telegram notifications)
python main.py
```

**`--dry-run` still contacts sources and writes the archive, review queue, report and generated pages.** It only suppresses Telegram notifications. Use a separate checkout for experiments with disposable data.

### 5. Tests and dependency checks

```bash
npm run test:frontend
npm run build
npm run typecheck
npm audit --audit-level=moderate
python -m pytest tests/ -q
```

CI runs frontend and Python regression checks, a production build, TypeScript checks and dependency vulnerability audits. Frontend coverage includes data handling, filters, calendar exports, theme selection and the newsletter workflow. Collector, LLM and email-provider responses are mocked in tests; passing tests do not prove live-source health or inbox delivery.

Python dependencies use patched minimums and major-version bounds; they are not a full transitive lockfile. See [SECURITY.md](SECURITY.md#dependency-checks) for the Python audit command and private vulnerability reporting.

### 6. Admin workflow

The public event catalogue does not expose administrative actions. Admin commands run locally, edit JSON,
rebuild `docs/`, and can then be committed/pushed.

```bash
# Show published events
python scripts/admin.py list-events

# Show candidates waiting for manual review
python scripts/admin.py list

# Publish a candidate into data/events.json
python scripts/admin.py approve <candidate-id> --reason "Verified Milan event"

# Suppress a candidate from future queues (review queue only)
python scripts/admin.py reject <candidate-id> --reason-code not_milan --reason "Munich venue"

# Remove a candidate from review only; it may reappear on a future scan
python scripts/admin.py dismiss <candidate-id>

# Move a published event back to review
python scripts/admin.py move-to-review <identifier> --note "Check venue"

# Maintainer: remove an already published event (by id prefix, URL or title fragment)
python scripts/admin.py remove <identifier>

# Maintainer: remove and also add title to blacklist to prevent re-ingestion
python scripts/admin.py remove <identifier> --blacklist --reason-code online_only --reason "Online jam"

# Mark a high-signal admin decision as a regression case for pytest
python scripts/admin.py remove <identifier> --reason-code known_false_positive --regression
```

Admin approvals/removals/review moves rebuild the static site and README immediately. Every admin action is logged locally in `data/admin_actions.json`, which is excluded from Git and deployment. `--regression` marks a local decision for consideration; reproducible public cases are curated separately in `tests/fixtures/admin-regressions.json` without operational notes, operator details or timestamps.

The public review queue is available at `/review` on the main site and `docs/review.html` on the mirror. Visitors can open issues from the site, but only maintainers apply final actions. Review queue entries and suppression decisions are public: do not include credentials, subscriber addresses or private correspondence. See the [maintainer guide](docs/admin.md).

### 7. Pre-render the static mirror (SSG)

```bash
python scripts/build_static_site.py
```

This generates `docs/index.html`, `docs/review.html` and supporting assets, then updates the README table from `data/events.json`, without collecting new events. The Next.js site is built separately with `npm run build`. Do not hand-edit generated HTML; edit its templates or data instead. Further environment and deployment details are in [docs/setup.md](docs/setup.md).

</details>

---

<details>
<summary><strong>Deploy on GitHub Actions</strong></summary>

### 1. Configure the maintained repository

### 2. Configure GitHub Actions and Vercel

Go to **Settings → Secrets and variables → Actions → New repository secret** and add the collection and Telegram credentials required by the workflow. Enable Actions and allow the collection workflow to commit generated public data.

Import the repository into Vercel with the repository root as the project directory. `vercel.json` configures Next.js, `npm ci`, `npm run build` and the weekly newsletter cron. The canonical origin defaults to `https://hackathon-milano.vercel.app`. To override it, set `NEXT_PUBLIC_SITE_URL` to the same value in Vercel and the GitHub Actions repository variables so the website, generated pages and Telegram links stay aligned.

GitHub Actions secrets and a local Python `.env` do not automatically configure Vercel. Newsletter service credentials belong in the Vercel environment; never prefix secrets with `NEXT_PUBLIC_`.

### 3. Enable GitHub Pages (optional mirror)

The primary site is the Next.js app deployed on **Vercel** ([hackathon-milano.vercel.app](https://hackathon-milano.vercel.app/)),
which rebuilds on pushes to its connected production branch, including generated data commits.

GitHub Pages is kept as an optional static mirror. To enable it, go to **Settings → Pages** and set:

- **Source**: `Deploy from a branch`
- **Branch**: `main` · **Folder**: `/docs`

The mirror will be available at `https://<username>.github.io/<repo>/`. Its pages declare a
`canonical` link to the Vercel site, so duplicate content is attributed to the primary host.

### 4. Enable the workflow

The workflow is in [`.github/workflows/check_hackathons.yml`](.github/workflows/check_hackathons.yml):

- **Cron:** daily at **11:00 UTC** (`0 11 * * *`): 12:00 CET in winter, 13:00 CEST in summer. Scheduled runs can be delayed by GitHub Actions.
- **Manual:** from the Actions tab → Run workflow.
- Tests run before collection. Updated public data, generated mirror pages/assets and the README table are committed when they change.
- The run report is uploaded as the `hackathon-monitor-report` artifact.

The separate [test workflow](.github/workflows/tests.yml) checks pull requests and relevant code changes. The weekly email schedule is independent of the daily collection schedule.

</details>

---

<details>
<summary><strong>Telegram Bot</strong></summary>

`bot.py` runs a long-polling bot with the following commands:

| Command | Description |
|---------|-------------|
| `/scan` | Trigger a manual scan |
| `/help` | List commands |

The bot sends a **summary after each scan** with up to four new event previews, dates and locations, the number of upcoming events, source availability, elapsed time and a button opening the public calendar. Scans with no new events still send a status summary.
Full event details are available on the [main website](https://hackathon-milano.vercel.app/), the static mirror and the README table above.

Local start:

```bash
source .venv/bin/activate
python bot.py
```

Restricted to the configured `TELEGRAM_CHAT_ID` — all other messages are automatically rejected.

</details>

---

<details>
<summary><strong>Weekly Email Newsletter</strong></summary>

The newsletter integration uses **Brevo Free** for confirmation emails, subscriber contacts and weekly campaigns, and **Upstash Redis Free** for pending confirmations, rate limits, consent evidence and delivery state. **It is not active until all required services and environment variables are configured.** Without them, the interface displays a preview notice and disables email submission.

1. Create a dedicated Brevo Free account, verify an existing sender email and create a dedicated subscriber list. The website URL `hackathon-milano.vercel.app` is not an email domain you can authenticate through DNS. Brevo can rewrite a verified free-email sender to its own domain; the sender display name is **Hackathon Milano**.
2. Create Upstash Redis on its Free plan and configure private REST access. Do not enable paid upgrades or automatic billing.
3. Copy the settings from [`.env.newsletter.example`](.env.newsletter.example) into the Vercel environment (or a Git-ignored `.env.local` for development).
4. Set the sender, public owner/contact details and a random `CRON_SECRET` of at least 32 characters; enable `NEWSLETTER_ENABLED=true` only when setup is complete, then redeploy.

The integration accepts only a verified Free account with enough remaining email credits. It caps the list at 250 reserved subscriber slots and confirmation requests at 40 per rolling 24 hours, within Brevo’s 300-email daily allowance. Shared account activity and provider approval can still prevent delivery; there is no automatic paid fallback.

Signup requires explicit consent, an email link that expires after 24 hours, and a confirmation button on the website. Every digest includes an unsubscribe link. Existing unsubscribed contacts are not silently reactivated. Subscriber addresses never belong in this repository.

The current prompt mode is `NEXT_PUBLIC_NEWSLETTER_PROMPT_MODE=always` for repeat-visit evaluation. Choose `first-visit` to show it once per browser or `off` to retain only the manual signup button. This controls the invitation, not subscription consent.

The authorized Vercel Cron runs on **Mondays at 08:00 UTC** (09:00 CET / 10:00 CEST). It selects accepted events discovered or approved during the completed weekly interval and excludes dated events that have passed. No eligible new events means no digest. Delivery state prevents repeated broadcasts; uncertain provider outcomes require maintainer review instead of automatic resending.

See [docs/newsletter.md](docs/newsletter.md) for the complete variables, retention, testing and recovery procedure. Form previews and mocked tests do not verify a real email delivery.

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

3. Add parsing and failure-handling tests in `tests/test_collectors.py` or a focused test module, then run the Python suite. Use the existing HTTP utilities for retry and timeout behavior, preserve original source URLs, and avoid committing credentials or private data in fixtures.

</details>

---

<details>
<summary><strong>Project Structure</strong></summary>

```text
hackathon-monitor/
├── app/                       # Next.js pages, metadata and API routes
│   ├── page.tsx               # Public event discovery
│   ├── review/                # Public review queue
│   ├── privacy/               # Privacy and newsletter information
│   ├── newsletter/confirm/    # Explicit email confirmation
│   └── api/newsletter/        # Subscribe, confirm and authorized weekly digest
├── components/                # Search, event cards, radar, themes and newsletter UI
├── lib/                       # Frontend data, filters, SEO and newsletter logic
├── public/                    # Hero artwork and public identity assets
│   ├── brand/                 # Abstract radar SVG/ICO/PNG and Apple touch icon
│   ├── favicon.ico            # Browser fallback icon
│   └── milano-hero.webp       # Architectural hero illustration
├── package.json               # Frontend scripts and dependency constraints
├── package-lock.json          # Locked JavaScript dependency tree
├── vercel.json                # Next.js deployment and weekly cron
├── main.py                    # Pipeline orchestrator and collector registry
├── bot.py                     # Optional Telegram bot (long-polling)
├── config.py                  # Centralized Python configuration
├── models.py                  # HackathonEvent and BaseCollector
├── requirements.txt           # Python dependencies
├── .env.example               # Blank collection configuration example
├── .env.newsletter.example    # Blank private newsletter configuration example
├── LICENSE                    # All rights reserved; third-party rights preserved
├── SECURITY.md                # Vulnerability reporting and security checks
├── collectors/                # 28 registered source integrations
│   ├── eventbrite.py          # REST API
│   ├── eventbrite_web.py      # HTML / JSON-LD fallback
│   ├── web_search.py          # Web search queries
│   ├── luma.py                # Embedded JSON and HTML
│   ├── meetup.py              # GraphQL and HTML
│   └── ...                    # Complete inventory above
├── filters/
│   ├── keyword_filter.py     # Keyword, date and junk-URL checks
│   └── llm_filter.py         # Groq classifier and semantic deduplication
├── notifiers/telegram.py      # Telegram summaries
├── storage/json_store.py     # Persistence and layered deduplication
├── utils/
│   ├── admin_audit.py        # Structured admin audit and regression cases
│   ├── http.py               # HTTP retry and timeout utilities
│   ├── html_export.py        # Static mirror generator
│   ├── readme_export.py      # README table generator
│   └── review_queue.py       # Manual review persistence
├── scripts/
│   ├── admin.py              # Local maintainer entrypoint
│   ├── review_candidate.py   # Admin workflow implementation
│   ├── build_static_site.py  # Generate mirror and README from stored data
│   ├── slow_classify.py      # Classification recovery tool
│   ├── collect_only.py       # Collection diagnostics
│   ├── extract_dates.py      # Backfill dates with the classifier
│   ├── project_metrics.py    # Aggregate reports in ignored .local/metrics/
│   ├── generate-brand-assets.mjs # Generate favicon and identity variants
│   └── test-*.mjs            # Frontend and newsletter regression tests
├── data/
│   ├── events.json           # Public event archive
│   ├── review_queue.json     # Uncertain candidates
│   └── review_decisions.json # Manual approve/reject decisions
├── docs/
│   ├── index.html            # Generated GitHub Pages mirror
│   ├── review.html           # Generated review queue
│   ├── assets/               # Static mirror assets
│   ├── banner.svg            # README banner
│   ├── setup.md              # Environments and deployment
│   ├── admin.md              # Moderation and maintenance
│   ├── newsletter.md         # Email activation and operations
│   └── analytics.md          # Free usage metrics and local measurement
├── tests/                    # Python regression suite
└── .github/workflows/
    ├── check_hackathons.yml  # Daily collection and generated-data publishing
    └── tests.yml             # Frontend/Python checks and dependency audits
```

</details>

---

<details>
<summary><strong>Known Limitations</strong></summary>

- **Source coverage:** scraping can fail when websites change, block automated access or return incomplete data. Integrations such as PoliHub may be affected by access controls; web search can surface additional public pages but is not exhaustive.
- **Social platforms:** LinkedIn and Twitter/X content is discovered through web-search queries in this project; no direct event API integration is implemented for them.
- **Groq LLM:** the configured defaults are `openai/gpt-oss-120b` and the `qwen/qwen3.6-27b` fallback; legacy model IDs listed in `config.py` are ignored. Provider availability and account limits can change. Without working classification access, new candidates cannot be validated; a complete classification failure preserves the existing archive and records the issue in `data/last_report.json`.
- **Manual review**: low-confidence candidates are not published automatically; they are written to `data/review_queue.json` and can be approved or rejected with `scripts/admin.py`.
- **Run diagnostics**: `data/last_report.json` includes per-collector status, event counts, durations, and errors. GitHub Actions uploads it as the `hackathon-monitor-report` artifact.
- **Some collectors** may return errors while the remaining sources complete. A successful overall run does not imply every source was healthy.
- **Publication timing:** the Next.js site reads the archive bundled with its deployment. Data changes become visible after the production build, not immediately after a local command.
- **Newsletter:** real subscriptions and delivery require configured private services; unconfigured deployments only show the preview interface. Email-provider errors or uncertain sends can require maintainer intervention.
- **Search visibility:** metadata, canonical URLs and icons help describe the site to crawlers but do not guarantee indexing, rankings or an immediate change in the displayed search result.

</details>

---

## Project measurement

Run `python scripts/project_metrics.py` to generate aggregate archive and scan measurements in `.local/metrics/`, excluded from Git and deployment. These describe the available data, not classification accuracy or the number of people using the site.

Website traffic requires enabling **Vercel Web Analytics on Hobby** and setting `NEXT_PUBLIC_ANALYTICS_ENABLED=true` before redeployment. No visitor count is invented before data exists. See [the setup and interpretation guide](docs/analytics.md).

## Validation

Use the commands in Local Setup and the latest CI run for current results. Tests cover models, deduplication, filters, moderation, generated output, frontend behavior and newsletter logic. Source integrations and email delivery use mocks in tests; live availability and delivery require separate checks with configured services.

## Rights and contributions

Copyright © 2026 Federico Gallo. **All rights reserved.** The current original project materials are not offered under an open-source license; see [LICENSE](LICENSE). Public visibility permits inspection under GitHub’s terms, not unrestricted reuse. Third-party materials retain their own rights. This notice does not revoke any permissions previously granted for earlier revisions.

For proposed code contributions, contact the maintainer to agree on permission and terms before proceeding. Include the original event URL for data reports, and a clear description with relevant validation for code changes.

- 🔌 **Add a new source** — write a collector and open a PR
- 🐛 **Report a wrong entry** — open an issue with the event link
- 🧠 **Improve LLM filtering** — better prompts, fewer false positives
- 📍 **Spot a missing hackathon?** — [open an issue](https://github.com/federicoogallo/Hackathon-MI/issues/new?title=Missing+hackathon)

---

> [!WARNING]
> **Check the original source.** The dataset may contain inaccuracies, duplicates, missing events or incomplete dates and venues. Automated classification and manual review reduce errors but do not mean that every published event has been personally verified. Confirm registration, eligibility and current details with the organizer before making plans.

---

<div align="center">

<sub>Hackathon Milano is an independent discovery service.<br>
Event names, descriptions and linked material belong to their respective organizers.</sub>

</div>
