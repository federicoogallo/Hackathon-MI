# Hackathon Milano

Find upcoming hackathons in Milan, compare dates and sources, and save the events you want to attend.

**[Explore the website](https://hackathon-mi-ten.vercel.app/)** · [Report an event](https://github.com/federicoogallo/Hackathon-MI/issues/new)

The public site combines a Next.js interface with a Python collection pipeline. Events are collected from public platforms, communities and institutions, deduplicated, then checked with rules and an LLM. Uncertain candidates go to a separate review queue; maintainers can approve or reject them.

## Website features

- Search across event titles, locations and descriptions, with date and source filters.
- Shareable search URLs, grid and list views, and chronological or alphabetical ordering.
- Saved events stored in your browser and calendar downloads for dated events.
- Light, dark and system themes, with a persistent preference.
- An interactive Milan scene connected to upcoming events. The radar advances every seven seconds, pauses on interaction and respects reduced-motion preferences.
- Responsive layouts, keyboard navigation and visible links to each original source.
- Weekly email signup with confirmation and unsubscribe support, available when the private delivery services are configured. See [newsletter setup](docs/newsletter.md).

No account is required to browse or save events. Saved events and theme preferences stay on the current browser; they are not synchronized between devices. Newsletter signup is optional; the current prompt is shown to all visitors for evaluation.

## Upcoming events

This table is generated from the same archive used by the website. Always check the original event page for registration, eligibility and current details.

<!-- HACKATHON_TABLE_START -->

> **9 hackathons** coming up in Milan · Last updated: Sep 20, 2026 12:15 CEST
>
> **[View the full website](https://hackathon-mi-ten.vercel.app/)** for search, filters and details.

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

<!-- HACKATHON_TABLE_END -->

## Run the website locally

Use Node.js 22 LTS and npm. The checked-in event archive is enough to run the website; collection API keys are not required.

```bash
git clone https://github.com/federicoogallo/Hackathon-MI.git
cd Hackathon-MI
npm ci
npm run dev
```

Open [localhost:3000](http://localhost:3000). To test a production build, run `npm run build` followed by `npm run start`.

## How data reaches the site

```text
Source collectors → deduplication → rules and LLM classification
                                      ├─ uncertain → review queue
                                      └─ accepted → event archive
                                                         ├─ Next.js website
                                                         ├─ static mirror and README
                                                         └─ Telegram scan summary
```

The daily [collection workflow](.github/workflows/check_hackathons.yml) runs at **11:00 UTC**: 12:00 in Milan during standard time, 13:00 during daylight saving time. It tests the pipeline before collecting and commits updated public data and generated pages. GitHub Actions can delay scheduled jobs.

The primary site is deployed on Vercel from this repository. The optional [GitHub Pages mirror](https://federicoogallo.github.io/Hackathon-MI/) uses a separate static template and points its canonical URLs to the primary site.

- [Pipeline setup and deployment](docs/setup.md)
- [Event review and maintenance](docs/admin.md)
- [Frontend design and accessibility](design-system/README.md)
- [Security and vulnerability reporting](SECURITY.md)

## Project structure

| Path | Purpose |
| --- | --- |
| `app/`, `components/`, `lib/` | Next.js pages, UI and frontend data handling |
| `public/` | Website images and icons |
| `collectors/`, `filters/` | Source integrations and event classification |
| `storage/`, `notifiers/` | Archive persistence and Telegram notifications |
| `main.py`, `bot.py`, `config.py` | Pipeline, optional Telegram bot and configuration |
| `data/` | Versioned public event data and moderation decisions |
| `utils/`, `scripts/` | Exporters and maintainer tools |
| `docs/` | Maintainer documentation and generated static mirror |
| `tests/`, `scripts/test-*.mjs` | Python and frontend regression checks |

## Validation

```bash
npm run test:frontend
npm run build
npm run typecheck
```

For the Python pipeline, install `requirements.txt` in a Python 3.12 virtual environment and run:

```bash
python -m pytest tests/ -q
```

The tests exercise parsing, deduplication, filtering, review actions, generated output and frontend behavior. CI also runs JavaScript and Python dependency vulnerability audits; see [security checks](SECURITY.md#dependency-checks) for local commands. External collector and LLM responses are mocked in the regression suite; passing tests do not establish live-source availability or classification accuracy.

## Contributing

Report missing or incorrect events through [GitHub issues](https://github.com/federicoogallo/Hackathon-MI/issues), including the original source URL. For code changes, open a pull request with a clear description and relevant validation.

To add a source, implement `BaseCollector` from `models.py`, register it in `main.py::get_collectors`, and add representative parsing and failure-handling tests. Keep credentials in local environment files or deployment secrets. Do not include personal subscriber data in the repository or public issues.

## Data limitations

The archive is collected and filtered automatically. Sources can change, become unavailable or publish incomplete information; dates, venues and eligibility may be missing or wrong. Manual review helps resolve uncertain cases but does not mean every published event has been checked by a person. Events without a confirmed date remain visible with an explicit unknown-date label.

The website is an independent discovery service. Event names, descriptions and linked material belong to their respective organizers; registration takes place on the original event website.
