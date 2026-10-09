# Event pages and source review

The website publishes native event pages at `/hackathon/<slug>` for events with enough documented information. These pages use the manually maintained registry in [`data/event_details.json`](../data/event_details.json), separate from the automatically collected archive in [`data/events.json`](../data/events.json).

A new collection result does not automatically receive an event page. The classifier can help identify and classify candidates; it does not supply facts for this registry. Do not use LLM-generated descriptions, inferred dates or assumed venues to complete a page.

## When to add a page

Check the organizer's event page and, when relevant, its linked program or rules. Confirm that the information concerns the correct edition, year and city: a page covering several locations or previous editions is not sufficient on its own.

Add a registry entry only when the event's dates, location and organizer are documented, and at least three useful facts have identifiable sources. Useful facts include the intended participants, team size, schedule, registration process or cost. There is no requirement to turn the information into a long article.

Keep uncertain or unavailable details explicit. For example, a known city does not establish a street address, and a date does not establish an exact start time. If two official sources disagree, record the discrepancy and mark the affected information as requiring confirmation instead of choosing an unsupported value. When dates or the location cannot be established, leave the event without a dedicated page until the information is sufficient.

## Registry fields

`data/event_details.json` is an array of entries. Each entry has these fields:

| Field | Content |
| --- | --- |
| `id` | The event ID from the collected archive. Keep it stable so the registry and calendar refer to the same event. |
| `slug` | The stable URL segment: lowercase letters, numbers and single hyphens, up to 120 characters. Use a distinct slug for each edition. |
| `title` | A clear event title identifying the relevant edition where needed. |
| `url` | The official event page linked as the main destination. |
| `sourceLabel` | A readable name for the main source or organizer. |
| `checkedAt` | The date the sources were actually checked, in `YYYY-MM-DD` format. It is not the date of a build or automated scan. |
| `startDate`, `endDate` | Documented event dates in `YYYY-MM-DD` format. Use the same date for a one-day event; the end must not precede the start. |
| `location` | The documented location displayed to visitors. Include a venue or address only when supported by the source. |
| `organizer` | The documented organizer or organizers. |
| `facts` | At least three objects containing `label`, `value` and `sourceUrl`. Each URL must support its corresponding fact. |
| `missing` | An array naming information still unavailable or requiring confirmation. Use an empty array if none is identified. |
| `venue` | Optional structured venue object, containing `name`, `streetAddress`, `addressLocality` and `addressCountry`. Omit it when the complete venue information is not documented. |

The main `url` identifies the event's source. Each `facts[].sourceUrl` provides more specific attribution where needed, such as a linked regulation PDF. A fact should be a concise, faithful description of the source; a source link alone does not validate its content.

Keep existing slugs when correcting titles, dates or venues, so shared event links remain stable. Do not recycle a past edition's slug for a new edition.

## Updating and validating

1. Read the current official sources and compare them with the entry. Check the edition and city again when the organizer reuses a landing page.
2. Update only the supported values and their source links. Add unresolved details to `missing`, or remove them when a source confirms them.
3. Set `checkedAt` to the actual review date. An automated collection run must not advance this date.
4. Run the frontend checks and a production build locally:

   ```bash
   npm run test:frontend
   npm run build
   npm run typecheck
   ```

The build validates the registry's required fields, unique IDs and slugs, dates, source URLs and minimum number of sourced facts. Invalid registry entries stop the build. This checks the data format and completeness; it cannot establish that an organizer's page is accurate or that its contents still match the entry. Source review remains necessary.

Local edits and builds do not publish changes. Publication follows the repository's normal commit, push and deployment procedure, with any approval required for the current task.

## Documented exclusions

[`data/event_exclusions.json`](../data/event_exclusions.json) records entries excluded from the public calendar after source review. Each exclusion contains:

| Field | Content |
| --- | --- |
| `id` | The affected archive event ID. |
| `reason` | A concise, factual explanation of the exclusion. |
| `sourceUrl` | The source supporting that decision. |
| `checkedAt` | The actual review date, in `YYYY-MM-DD` format. |

Use this record when an archive entry is not a valid upcoming event, for example when the source is a retrospective project report presented as a new event. Do not infer a future edition from an old page. Keep operational notes and private correspondence out of these public files.

## After an event ends

An event disappears from the upcoming calendar after its end date. Its dedicated page remains at the same URL with a concluded state, preserving the source links and documented information. Do not delete or repurpose a valid page simply because the event has passed.

Canonical URLs, metadata and the sitemap help search engines discover and understand these pages. They do not guarantee indexing, rankings or rich results.
