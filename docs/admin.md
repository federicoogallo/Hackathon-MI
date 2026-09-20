# Event review and maintenance

The public website provides discovery and contribution links. Publishing, rejecting or removing events is a maintainer operation performed against the repository's JSON data.

## Review candidates

Activate the Python environment described in [setup](setup.md), then inspect the current archive and review queue:

```bash
python scripts/admin.py list-events
python scripts/admin.py list
```

Check the original source, date, venue and participation requirements before deciding. Uncertain candidates are stored in `data/review_queue.json` and appear in the public review page; being in that queue does not mean an event is confirmed.

```bash
python scripts/admin.py approve <candidate-id> --reason "Date and Milan venue confirmed on the organizer's page"
python scripts/admin.py reject <candidate-id> --reason-code not_milan --reason "The venue is outside the monitored area"
python scripts/admin.py dismiss <candidate-id>
```

`reject` records a decision to suppress the candidate from future review queues. `dismiss` only removes the current queue entry; the candidate may appear again on a later scan.

## Correct published events

An identifier can be an ID prefix, URL or title fragment:

```bash
python scripts/admin.py move-to-review <identifier> --note "Confirm the venue before publishing"
python scripts/admin.py remove <identifier> --reason "Event cancelled by the organizer"
python scripts/admin.py remove <identifier> --blacklist --reason-code online_only --reason "Fully online event"
```

Use `--blacklist` only when future matching entries should also be excluded. Review command options with `python scripts/admin.py <command> --help`.

Actions rebuild the static pages and README table where applicable. The Next.js site reflects committed data after its next deployment. Inspect the diff before committing: a local maintainer action does not itself publish a Vercel deployment.

## Public audit data

Actions are recorded in `data/admin_actions.json` with a reason and a stable reason code. Review decisions and blacklist entries are also versioned. These files are public: keep reasons factual and avoid personal information, credentials, subscriber addresses or private correspondence.

For a decision that captures a useful regression case, supported commands accept `--regression`. Reserve this for behavior that can be checked reproducibly; some editorial judgments require human review rather than an automated filter assertion.

## Adding a collector

1. Implement `BaseCollector` and return `HackathonEvent` instances with the original source URL.
2. Register the collector in `main.py::get_collectors`.
3. Add representative tests for parsing, missing fields and source failures.
4. Run the Python test suite before submitting a pull request.

Use the existing HTTP utilities for retry and timeout behavior. Do not commit captured responses containing credentials or personal information. Source integration tests use mocks, so also document any live-source behavior that was verified separately.
