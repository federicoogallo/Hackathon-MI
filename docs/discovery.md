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

## Optional API access

**Eventbrite:** the general event-search endpoint was [retired in December 2019](https://www.eventbrite.com/platform/docs/by-date). The API integration now reads only public, live events from explicitly configured organizations authorized by the token. Set `EVENTBRITE_API_KEY` and comma-separated numeric `EVENTBRITE_ORGANIZATION_IDS` only if you already have that access. Organization IDs are not public organizer-profile IDs. Private, unlisted, invitation-only and draft records are excluded. The separate web collector remains the route for general public discovery; a token alone cannot restore global search.

**Reddit:** the optional collector requires existing approved API access, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` and `REDDIT_USER_AGENT` identifying the actual application/account. It stops on access denial and rate limits. Reddit's [October 2026 migration announcement](https://support.reddithelp.com/hc/en-us/articles/54353370049684-Changelog-October-8-2026) schedules RSS removal for November 13, 2026, closes new public API requests on October 31, and ends remaining public API access in March 2027. Treat this integration as transitional; there is no anonymous RSS fallback and this repository does not implement the Developer Platform migration.

Public listing APIs used by Devpost, HackerEarth and Unstop are separate from these credentialed integrations. Websites can still block collection or change their schemas. Access-denied pages and unrecognized layouts must remain visible in diagnostics; they do not establish an empty event calendar.

Search queries also cover official pages from PoliHub, Comune di Milano, DoraHacks and Unstop. Indexed snippets may provide complementary discovery when direct collection is unavailable, but are attributed to `web_search` and do not change the blocked source's status or guarantee complete coverage.

## Private traces

`CANDIDATE_AUDIT_DIR` defaults to `.local/discovery/`; an empty value disables trace files. The latest 30 scans retain bounded source excerpts, URLs without query parameters/credentials, source dates, classification reasons and per-stage outcomes. Files are created with owner-only permissions. These are operational records, not public event data.

The aggregate Actions report remains uploaded by the workflow. Raw traces are neither committed nor uploaded; on ephemeral runners they disappear after the job. Retaining them across CI runs requires a separately configured private destination. Do not include API keys, operator details or subscriber information, and do not add these traces to the public workflow's artifact or auto-commit paths.

## Verification and coverage

Run the offline regression suite with `python -m pytest tests/ -q`. It covers schema changes, publication/event dates, false-positive exclusions, event identity, malformed/reordered LLM responses and review persistence. Requests and LLM responses in these tests are mocked.

The BAINSA/Anthropic accessibility case is represented by fixtures testing identity, dates and venue evidence. Some fixtures deliberately synthesize structured markup around verified historical facts: they do not claim that the real source exposed that markup or was indexed before the event. Finding a post-event recap is not evidence of timely discovery.

For a meaningful coverage estimate, maintain an independently reviewed sample of real events and known false positives. Measure:

- events found before registration closes, divided by eligible events in that sample;
- correct publications divided by reviewed publications;
- losses at each collection/filter/publication stage;
- discovery lead time and source failures over time.

Keep evaluation cases separate from cases used to tune rules. A passing regression suite and a larger raw-event count do not establish complete coverage of the web.
