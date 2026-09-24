# Setup and deployment

The public Next.js website reads the versioned event archive at build time. The Python pipeline collects and reviews data separately; it does not need to run inside the web server.

## Website

Use Node.js 22 LTS, matching the frontend CI workflow. Install with the committed lockfile:

```bash
npm ci
npm run dev
```

For a production check, stop the development server before running:

```bash
npm run test:frontend
npm run build
npm run typecheck
npm run start
```

`NEXT_PUBLIC_SITE_URL` sets the canonical public origin. Its default is `https://hackathon-milano.vercel.app`. If using a custom domain, set the same value in Vercel and the GitHub Actions repository variable `NEXT_PUBLIC_SITE_URL` before rebuilding both outputs. Local builds read the same environment variable. Leave it unset to use the default. Public environment variables must never contain secrets.

CI runs the frontend checks and audits the installed dependencies. Python dependencies use patched minimum versions and major-version bounds rather than a complete lockfile. See [security checks](../SECURITY.md#dependency-checks) for both audit commands.

## Python pipeline

Use Python 3.12, matching the collection workflow:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Configure only the integrations you need. `config.py` reads the local `.env`; keep that file outside Git.

| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEY` | LLM event classification; needed to validate new candidates |
| `LLM_MODEL`, `LLM_MODEL_FALLBACKS` | Optional supported model IDs; defaults are defined in `config.py` |
| `EVENTBRITE_API_KEY` | Eventbrite API collector; the separate web collector can run without it |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Reddit API collector |
| `MEETUP_API_KEY` | Optional Meetup API access |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional scan summaries and authorized bot commands |
| `GITHUB_REPO_URL` | Repository used by generated contribution links |
| `NEXT_PUBLIC_SITE_URL` | Canonical website origin and notification destination |

Run the pipeline:

```bash
python -m pytest tests/ -q
python main.py --dry-run
```

**`--dry-run` suppresses Telegram notifications but still contacts sources and writes the archive, review queue, report and generated pages.** Use a separate checkout when trying collection or classification changes against disposable data. Run `python main.py` to include configured Telegram notifications.

Without a working LLM key, candidates requiring classification cannot be published as verified events. If all classification results fail, the pipeline preserves the previously stored archive and records a diagnostic status instead of replacing it with an empty result.

## Automated collection

The [collection workflow](../.github/workflows/check_hackathons.yml) supports manual runs and a daily schedule at 11:00 UTC. In `Europe/Rome`, that is 12:00 during standard time and 13:00 during daylight saving time. Scheduled jobs are not guaranteed to start at the exact minute.

Set the required API credentials in **GitHub → Settings → Secrets and variables → Actions**. The workflow runs tests, collects events, rebuilds static output and commits the resulting public data. Review the workflow's explicit `file_pattern` before adding any new generated files.

Per-source status, durations and failures are written to `data/last_report.json`. This local runtime file is ignored by Git and uploaded as the `hackathon-monitor-report` Actions artifact. Some source integrations can fail while the rest of the scan completes; inspect this report when diagnosing coverage.

## Web deployment

Import the repository into Vercel with the repository root as the project directory. `vercel.json` configures Next.js, `npm ci`, and `npm run build`. Production deployments should track the intended Git branch so new data commits trigger a rebuild.

Weekly email requires additional private services and environment variables; follow [newsletter setup](newsletter.md). Browsing and saved events do not require those services.

The website supplies canonical links, Italian metadata, `WebSite` structured data, branded icons, social preview images, `robots.txt` and a sitemap. These describe the site to crawlers; they do not guarantee a particular ranking, title or appearance in search results. Keep the canonical host consistent across deployments and the static mirror. Search engines can continue to show older titles and icons until they crawl the site again.

The optional GitHub Pages mirror is generated separately:

```bash
python scripts/build_static_site.py
```

This refreshes `docs/index.html`, `docs/review.html`, supporting assets and the generated README table from stored data, without collecting new events. Do not hand-edit generated pages. To publish the mirror, select **GitHub → Settings → Pages → Deploy from a branch → main → /docs**. The mirror points canonical links to the primary Vercel site.

## Usage metrics

Website analytics are optional and disabled by default. Follow [the free Analytics setup](analytics.md) to enable page views and estimated visitors on Vercel Hobby. Local project measurements are generated under ignored `.local/metrics/`; do not add reports or runtime audit logs to the public repository.

## Optional Telegram bot

```bash
python bot.py
```

The long-polling bot accepts `/scan` and `/help` for the configured `TELEGRAM_CHAT_ID`. A scan collects and writes data, and can send a summary. Keep one bot process active for a given token and do not expose its token in logs, issues or URLs shared with others.
