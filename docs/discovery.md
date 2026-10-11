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
| `blocked` | All recorded attempts were blocked by HTTP access/rate limits |
| `disabled` | Integration unavailable because required configuration/dependency is missing |
| `failed` | No successful request/data and a recorded failure |

HTTP errors are tracked even when a collector handles them and returns an empty list. Non-HTTP integrations and parsers should call `utils.collector_health.record_issue` for their own failures. Source availability remains dependent on upstream APIs, markup and access policies; failed endpoints must be investigated rather than silently considered healthy.

The report separates `attempted_at`, `classification_completed`, `classification_errors` and candidate-stage counts. A partial classification failure does not prevent valid results from continuing, but marks the report degraded. A total source/classifier failure does not advance the archive's previous successful check timestamp.

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
