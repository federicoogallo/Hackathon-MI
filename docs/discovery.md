# Discovery and diagnostics

The monitor searches for in-person hackathons in Milan and the surrounding monitored area. Its registered integrations are an inventory, not proof that every source is available or that every relevant event has been found.

## Candidate flow

1. Collect source records in parallel. Search queries use the current and following year and include university associations and organizers.
2. Inspect at most eight promising search results on known official domains. The budget rotates daily, with space reserved for community announcements. Other domains and social results remain snippet candidates. Fetching does not execute JavaScript, authenticate or bypass access controls.
3. Bind structured `Event` evidence to the candidate's identity before accepting dates or venues. Article publication timestamps go to `published_at`; they never substitute for event dates. Missing facts remain missing.
4. Merge compatible same-event records before filtering, independently of collector completion order. Similar generic descriptions are insufficient; contradictory dates or editions prevent a merge. The URL-based ID cannot store simultaneous editions on the exact same URL: one complete record of the latest explicit edition is retained, without importing the earlier edition's details.
5. Apply manual rejections, keyword/date checks, validated LLM classification and deterministic quality gates. A model can classify or select existing source facts; it cannot invent factual fields or force a duplicate merge without matching identity.
6. Keep uncertain, insufficient-evidence and failed-classification candidates in review. Previously collected facts survive a weaker rediscovery. Decisions and known event expiry remove pending entries; undated entries expire after 60 days from first queueing.

Specific exclusions for known false positives still apply. Keywords such as “winners” or an introductory workshop do not by themselves invalidate a concrete future hackathon announcement, but recaps, unrelated workshops, remote-only events and wrong locations remain subject to rejection.

The date guard also checks explicit Italian/English event-date announcements in source titles and snippets, including events earlier in the current year. It runs before classification and again before publication. Recognized dates without a year, invalid dates and conflicting dates cannot be automatically approved: an LLM approval is overridden and the candidate is queued for review. Discovery timestamps, publication timestamps, application deadlines and model explanations never supply an event date or a missing year. Structured event dates take precedence over incidental prose; reviewed multi-day events stay in the archive through their documented end date. Unsupported text is not proof of a future event and remains subject to the existing classifier and quality checks; this guard is not a general natural-language date parser.

## Source health

`data/last_report.json` includes per-source request issues, durations and counts:

| Status | Meaning |
| --- | --- |
| `healthy` | Records returned with no recorded errors |
| `empty` | No records and no recorded errors; this is not proof that the parser is correct |
| `degraded` | Some requests/data succeeded, but at least one error occurred |
| `blocked` | No records and only access/rate-limit errors; includes HTTP 200 verification pages |
| `disabled` | Optional integration not configured, missing a dependency or requiring approved access |
| `failed` | No successful request/data and a recorded failure |

HTTP errors are tracked even when a collector handles them and returns an empty list. Non-HTTP integrations and parsers should call `utils.collector_health.record_issue` for their own failures. Source availability remains dependent on upstream APIs, markup and access policies; failed endpoints must be investigated rather than silently considered healthy.

The report separates `attempted_at`, `classification_completed`, `classification_errors` and candidate-stage counts. A partial classification failure does not prevent valid results from continuing, but marks the report degraded. A total source/classifier failure does not advance the archive's previous successful check timestamp.

Telegram lists partial sources separately from blocked, failed and disabled ones. A partial source may still contribute valid candidates. The exact DDGS empty-result exception is treated as a query without matches; transport errors, timeouts and rate limits remain failures.

Check the live integrations without invoking classification, modifying the catalog or sending messages:

```bash
python scripts/check_sources.py --save
python scripts/check_sources.py universities eventbrite_web devpost
```

`--save` writes an owner-only aggregate report to ignored `.local/audit/`; it contains counts and sanitized diagnostics, not candidate content. Exit code 1 means at least one source is partial, blocked or failed. Disabled integrations are reported but do not cause failure by themselves. Results depend on the network and time of execution; local access does not prove that GitHub-hosted runners have the same access.

## Scan metrics and alerts

Scans append their recorded outcome to `data/metrics/scans.jsonl`, committed with the public data. It holds aggregates only: per-source status, record count and issue kinds (no request details or endpoints), stage counts, review-queue and archive size, duration, status, pipeline commit and classifier usage (calls, prompt/completion tokens and response time per model, fallback calls, rate-limit retries, failed calls, unclassified candidates, prompt version). `--dry-run` computes alerts without appending.

A successful publication is recorded after both `events.json` and `review_queue.json` are saved. An unexpected error before an outcome is recorded produces a line with status `crashed` and the exception type (`error`), without collection counts or source results; such lines neither extend nor interrupt a source's silence. A data-contract failure records `contract_failed_preserved`. The workflow has a separate metrics persistence step that also runs after a failed scan or a later build/upload failure, committing available metrics without publishing the other changed data files. A terminated runner or an unavailable Git remote can still prevent persistence.

Alerts compare the scan with the previous lines:

| Alert | Condition |
| --- | --- |
| Silent source | No records for 3 consecutive scans, after at least 3 of the 14 scans before the silence had records. Disabled integrations are excluded. |
| Source back | A source that was silent in the previous scan has records again. |
| Volume drop | Raw records below half the median of the previous 14 scans (at least 5 needed). |
| Fallback model | A fallback model answered at least one call. |
| Classifier errors | Calls failed on every model, or candidates were left unclassified. |

An alert is reported in full, as a log warning, a workflow annotation and a Telegram line, when it starts, when a source comes back, and as a reminder every 7 scans while it lasts. In the scans between, the Telegram summary names it in one line ("Ancora attivi, già segnalati") and the log keeps an info line.

`scripts/backfill_scan_metrics.py fetch` downloads, with the `gh` CLI, the reports, logs and commits GitHub Actions still keeps (90 days by default) into ignored `.local/ci-history/`; `build` merges them into the metrics file, keeping existing lines, and prints the alerts that would have been reported. Only runs with available reports can be reconstructed. Backfilled lines (`origin: backfill`) take per-source counts from the uploaded reports and classifier trouble from the logs; tokens and per-model calls were not logged before, so they stay unknown. Replaying 1 August to 1 November 2026 reports 22 alerts out of 113 active across the 94 scans: Regione Lombardia and Camera di Commercio silent from 17 October (blocked since the 15th), Codemotion failing from 21 October, Taikai silent from 14 August and back on 17 September, a sparse HackerEarth silence back on 21 September, one fallback call on 22 August and one unclassified candidate on 31 October; the rest are reminders every seven scans.

Each classified record carries `provenance`: the model that answered (empty when no model did), a hash of the system prompt and candidate layout (`prompt_version`), the classification time and the pipeline commit. Records classified before this field existed have none.

## Data files

`events.json`, `review_queue.json` and `review_decisions.json` are read before collection starts. Existing files must contain their expected `events`, `candidates` or `decisions` collection. Invalid JSON, missing collection keys, malformed records or decision entries, and missing or duplicate record IDs stop the scan with `CorruptDataFile` (exit code 1 and a `crashed` metrics line). A genuinely absent file can initialize an empty dataset. A damaged existing file is never silently read as empty, which could erase records or ignore manual rejections. Restore it, for example from Git history, before running again.

The pipeline, review scripts and admin server write each JSON file, including the run report, to a temporary file in the same folder and then rename it over the target. Each replacement is atomic: readers see a complete old or new file.

Pipeline publication coordinates the archive and review queue with the ignored journal `data/.publication-transaction.json`. The journal preserves the previous state before replacement. A failed publication rolls back the pair; if the process stops before that finishes, the next scan recovers the previous state before loading data or collecting sources. Keep a pending journal until recovery succeeds. The journal and temporary files are local recovery data and must not enter public artifacts. Writers must be serialized, as they are in the scheduled workflow. This recovery protocol does not make both renames simultaneous: a concurrent reader can briefly observe a new archive with an old queue. It protects against process interruptions, not power loss or operating-system crashes, and does not provide database-style reader isolation.

## Data contracts

Before a scan replaces `events.json` or `review_queue.json`, `utils/data_contracts.py` checks:

- every record has the fields and types of `HackathonEvent.to_dict`, an `http(s)` URL, an ID equal to the hash of that URL, a confidence between 0 and 1 and a known review status;
- IDs are unique, an alternate URL is never another archived event's URL, and no record has more than 25 alternate URLs (the warning starts above 10);
- no published event is past, except through a reviewed end date;
- queued candidates are unpublished, undecided, still current, `needs_review` and carry `queued_at`;
- this scan's automatic publications have an event date the code reads as future.

A violation stops the scan: the previous files stay on disk, the report records `contract_failed_preserved` with the violations, Telegram reports the interruption and the command exits with an error, so the workflow commits only the scan's metrics line. The report's archive, queue and publication counts describe the files left on disk; what the scan would have written is under `proposed`. Contract and alias diagnostics use record IDs to keep the report and annotations compact; the Telegram summary and local runs add titles to contract violations. This is an aggregate reporting convention, not a claim that web-source candidate titles are private. The test suite applies the same checks to the committed files as of their own `last_check`. On the 101 archive versions committed between August and October 2026, the only violation is the alias corruption of one record, which the ceiling would have stopped on 9 September 2026 (26 aliases; 99 by late October).

## Optional API access

**Eventbrite:** the general event-search endpoint was [retired in December 2019](https://www.eventbrite.com/platform/docs/by-date). The API integration now reads only public, live events from explicitly configured organizations authorized by the token. Set `EVENTBRITE_API_KEY` and comma-separated numeric `EVENTBRITE_ORGANIZATION_IDS` only if you already have that access. Organization IDs are not public organizer-profile IDs. Private, unlisted, invitation-only and draft records are excluded. The separate web collector remains the route for general public discovery; a token alone cannot restore global search.

**Reddit:** the optional collector requires existing approved API access, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` and `REDDIT_USER_AGENT` identifying the actual application/account. It stops on access denial and rate limits. Reddit's [October 2026 migration announcement](https://support.reddithelp.com/hc/en-us/articles/54353370049684-Changelog-October-8-2026) schedules RSS removal for November 13, 2026, closes new public API requests on October 31, and ends remaining public API access in March 2027. Treat this integration as transitional; there is no anonymous RSS fallback and this repository does not implement the Developer Platform migration.

Public listing APIs used by Devpost, HackerEarth and Unstop are separate from these credentialed integrations. Websites can still block collection or change their schemas. Access-denied pages and unrecognized layouts must remain visible in diagnostics; they do not establish an empty event calendar.

Search queries also cover official pages from PoliHub, Comune di Milano, DoraHacks and Unstop. Indexed snippets may provide complementary discovery when direct collection is unavailable, but are attributed to `web_search` and do not change the blocked source's status or guarantee complete coverage.

## Private traces

The catalogue (`events.json`), review queue (`review_queue.json`) and review/suppression decisions (`review_decisions.json`) intentionally publish information about events found on public web sources. An uncertain or rejected classification does not make that source information private. Public review entries and decisions must not contain credentials, subscriber addresses, private correspondence or operator details.

`CANDIDATE_AUDIT_DIR` defaults to `.local/discovery/`; an empty value disables trace files. The latest 30 scans retain bounded source excerpts, URLs without query parameters/credentials, source dates, classification reasons and per-stage outcomes. Files are created with owner-only permissions. These are operational records, not public event data.

The aggregate Actions report remains uploaded by the workflow. Raw diagnostic traces, local evaluation corpora and responses under `eval/`, credentials, and local operational notes are neither committed nor uploaded. On ephemeral runners local traces disappear after the job; retaining them across CI runs requires a separately configured private destination. Do not include API keys, operator details or subscriber information in trace content, and do not add local traces or evaluation files to the public workflow's artifact or auto-commit paths.

Actions logs are public and intentionally include web-source candidate titles and classification reasons, including rejected candidates. Some later filters also log titles. These lines can inform local classifier evaluation; they do not make the local corpus, annotations or raw model responses public. Credentials and other private operational data must stay out of these logs.

## Verification and coverage

Run the offline regression suite with `python -m pytest tests/ -q`. It covers schema changes, publication/event dates, false-positive exclusions, event identity, malformed/reordered LLM responses and review persistence. Requests and LLM responses in these tests are mocked.

The BAINSA/Anthropic accessibility case is represented by fixtures testing identity, dates and venue evidence. Some fixtures deliberately synthesize structured markup around verified historical facts: they do not claim that the real source exposed that markup or was indexed before the event. Finding a post-event recap is not evidence of timely discovery.

For a meaningful coverage estimate, maintain an independently reviewed sample of real events and known false positives. Measure:

- events found before registration closes, divided by eligible events in that sample;
- correct publications divided by reviewed publications;
- losses at each collection/filter/publication stage;
- discovery lead time and source failures over time.

Keep evaluation cases separate from cases used to tune rules. A passing regression suite and a larger raw-event count do not establish complete coverage of the web.
