# Reproducible project metrics

Measured on 2026-09-19 against clean source revision
`295ca6eef2916f60106352aeb341111b7efee04b`, Python 3.12.7.
See [machine-readable evidence](metrics/2026-09-19.json) for source hashes,
the collector registry, test modules, and the exact skipped-test reason.

| Measure | Result | What it establishes |
| --- | ---: | --- |
| Registered collector implementations | 28 | Integration scope; not 28 simultaneously healthy sources |
| Existing pytest cases collected | 250 | Includes parametrized cases |
| Existing pytest cases passed | 249 | Local regression suite, not measured production uptime |
| Skipped cases | 1 | An admin decision needs human/LLM semantics rather than a hard-filter assertion |
| Failures / errors | 0 / 0 | Result of this run |

The suite covers event models, storage/deduplication, filtering, collectors,
pipeline behavior, manual review, admin actions, and static output. Collector and
LLM tests use mocks; these counts do not establish live-source availability or
classification accuracy. Some existing parsing tests assert only return types.
No new tests were added to inflate the count, and no percent code-coverage claim
is made. `tests/test_admin_decision_regressions.py` depends on the versioned admin
corpus and the current date, so later runs may have different pass/skip counts.

## Reproduce

Use a clean checkout, install `requirements.txt`, and run:

```sh
python -m pytest tests/ -q -p no:cacheprovider --junitxml=/tmp/hackathon-tests.xml
python scripts/cv_metrics.py --junit /tmp/hackathon-tests.xml --revision "$(git rev-parse HEAD)" --output /tmp/hackathon-metrics.json
```

Supply XML produced from that same checkout, then inspect `source_sha256` before
comparing results. The metrics script uses only the standard library, reads the
collector registry with Python's AST, and parses JUnit XML. It does not import
application modules, read `.env`, call external services, or send notifications.
Without `--junit` it reports only source metrics. A failing JUnit report produces
an exit status of 1; missing or malformed inputs fail instead of inventing values.

The measured run used a `git archive HEAD` copy without local environment files.
Pre-existing uncommitted application edits were excluded from both the measurement
and this documentation commit. The original pytest run took 42.72 seconds,
including deliberate sleeps in the mocked web-search collector; this duration is
not an ingestion-performance benchmark.

## Defensible resume wording

- Built a daily Milan hackathon feed from **28 source integrations** by combining
  concurrent API/RSS/web collectors with a Next.js site and scheduled publishing.
- Guarded event publishing with **249 passing automated checks** covering parsing,
  deduplication, filters, and review workflows, with pytest running before scheduled
  ingestion and publishing.

Supporting implementation: `main.py::get_collectors`, `main.py::run_collectors`,
`storage/json_store.py::EventStore`, the `tests/` directory, and
`.github/workflows/check_hackathons.yml`. The runtime also implements model fallback
and an audit-logged manual-review queue; their presence is not evidence of a
percentage improvement in quality, savings, users, or production reliability.
