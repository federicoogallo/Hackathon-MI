# Weekly email

The newsletter sends newly discovered, upcoming hackathons to confirmed subscribers once a week. It is separate from the Telegram scan summaries.

The signup interface can be previewed without email credentials, but real subscriptions and delivery require the private services below. Without complete configuration, the form displays an explicit preview notice and disables email submission. No subscriber list is included in the repository.

## Services and configuration

1. Configure a sending domain in Resend and complete the domain verification it requires. Choose a recognizable sender on that domain.
2. Create a dedicated Resend segment for confirmed newsletter subscribers and record its ID. Do not import unconfirmed addresses or reuse a segment with unrelated contacts.
3. Create an Upstash Redis database and obtain its REST endpoint and token. Pending email confirmations and rate limits belong in this private store, not Git or public JSON files.
4. Add the variables from [`.env.newsletter.example`](../.env.newsletter.example) to the appropriate Vercel environment. Use separate credentials or resources for testing when available.
5. Set `NEWSLETTER_ENABLED=true` only when the configuration and public contact details are complete, then redeploy.

| Variable | Purpose |
| --- | --- |
| `RESEND_API_KEY` | Server-side Resend API access |
| `RESEND_SEGMENT_ID` | Segment containing confirmed subscribers |
| `NEWSLETTER_FROM` | Sender identity using a verified domain |
| `NEWSLETTER_CONTACT_EMAIL` | Public contact address for newsletter inquiries |
| `NEWSLETTER_OWNER` | Public identity responsible for the newsletter |
| `UPSTASH_REDIS_REST_URL` | Private Redis REST endpoint |
| `UPSTASH_REDIS_REST_TOKEN` | Server-side Redis credential |
| `CRON_SECRET` | Random secret of at least 32 characters, used for cron authorization and keyed identifiers |
| `NEWSLETTER_ENABLED` | Enables configured signup and delivery |
| `NEXT_PUBLIC_NEWSLETTER_PROMPT_MODE` | `always` for repeat-visit evaluation, `first-visit` for once per browser, `off` to disable automatic prompting |
| `NEXT_PUBLIC_SITE_URL` | Public origin used in confirmation and website links |

Set credentials in Vercel environment settings, never in variables prefixed `NEXT_PUBLIC_`. For local development, copy the needed values into a Git-ignored `.env.local`. The Python `.env` file and GitHub Actions secrets do not automatically configure Vercel.

The API requires an HTTPS Redis endpoint, a valid contact email and a secret at least 32 characters long. The canonical site must use HTTPS in production; development also permits HTTP on localhost. Confirmation links use that configured origin. A production preview on a different origin must use matching configuration to accept signup requests.

## Subscriber flow

A visitor enters an email address and checks the consent box. The server validates and rate-limits the request, then sends a confirmation link. The link expires after 24 hours. The address joins the subscriber segment only after confirmation; opening the site or dismissing the prompt does not subscribe anyone.

Confirmation links use `/newsletter/confirm#token=…`: the token is carried in the URL fragment rather than the server request URL. Loading the confirmation page does not subscribe the visitor; the visitor presses the confirmation button, which submits the token by POST. This also avoids activating a subscription when an email scanner opens the link automatically. Do not share confirmation links, even though the token is not part of the initial request URL.

The prompt is temporarily configured for all visitors with `NEXT_PUBLIC_NEWSLETTER_PROMPT_MODE=always`, so the interface can be evaluated on repeat visits. It opens after a short delay, unless the page is hidden or the visitor is using an input. Change this to `first-visit` and redeploy when first-visit behavior is desired. That choice uses local browser storage; it cannot recognize the same person on another browser or after clearing site data. `off` leaves only the page's manual signup button. These settings change prompt visibility, not consent requirements or who receives email.

Confirmed subscribers receive the weekly digest through Resend. Delivery uses its unsubscribe mechanism. If an existing Resend contact is globally unsubscribed, confirmation returns an instruction to contact the maintainer; the application does not silently reactivate it.

Signup is limited to five requests per connection per hour and twenty per day, with a one-hour cooldown per address and a service-wide cap of one hundred confirmation emails per day. Responses avoid exposing whether an address is already subscribed. IP-derived identifiers use HMAC; raw IP addresses are not stored in Redis. Outside Vercel, requests share a conservative rate-limit bucket because forwarded IP headers are not trusted.

## Weekly delivery

Vercel Cron is scheduled for Mondays at **08:00 UTC**: 09:00 in Milan during standard time, 10:00 during daylight saving time. Selection uses the latest completed weekly interval ending on Monday at 08:00 UTC, so a delayed invocation uses the same interval. The digest includes accepted events newly discovered or newly approved during that interval, excluding dated events that have already passed in `Europe/Rome`. Events with no confirmed date remain explicitly labeled as such. If no eligible new events exist, no digest is sent.

Set `CRON_SECRET` to a strong random value and keep the delivery endpoint private to authorized requests. Check production deployment and cron logs after activation; previewing the signup form does not verify email delivery, domain reputation or inbox placement.

The route is `/api/newsletter/weekly`; authorization uses `Authorization: Bearer <CRON_SECRET>`. It reads the event archive bundled with the deployment, so newly committed data must be deployed before it is available to the digest. Successfully submitted event IDs are retained in private delivery state to avoid repeating them in later digests. Older timestamps without a timezone are interpreted as UTC, matching the earlier GitHub Actions archives.

### Delivery state and recovery

The server records the weekly job before creating a Resend draft and records the send attempt before submitting it. Repeated invocations reuse the saved state. A provider response indicating that the broadcast is queued, scheduled, sending or sent is treated as accepted for delivery; it does not prove receipt by every subscriber.

When creation or sending has an uncertain outcome, automatic retries stop with `needs_review` rather than creating another broadcast. An unresolved previous job also blocks subsequent weeks. Inspect the private Redis weekly record, the saved broadcast ID when available and the corresponding broadcast in Resend. Reconcile the provider's actual status before changing stored job state or initiating any new send. Do not delete uncertain state just to rerun the cron: the provider may already have accepted the message.

## Private data and retention

Unconfirmed requests and completed-token markers expire from Redis after 24 hours. Rate-limit counters and address cooldowns expire within 24 hours. Confirmed addresses and unsubscribe status are managed in Resend. Redis also retains consent evidence identified by a keyed HMAC of the address for 365 days; this evidence records confirmation and the version of the consent text without storing the address in clear text. HMAC identifiers are still related to a subscriber and must be treated as private data. Weekly delivery records and sent-event identifiers have no automatic expiry and do not contain subscriber addresses.

Keep the public privacy page and the configured owner/contact information aligned with the actual service settings. Resend contact retention, provider logs and backups are governed by the provider configuration and policies; expiration of a pending Redis entry does not erase a delivered confirmation email or provider records.

## Verification before activation

- Use an address you control to verify the confirmation email and link expiry behavior.
- Confirm that an unverified address does not receive the digest.
- Check the sender, event links, layout and unsubscribe action in a delivered email.
- Verify that a repeat invocation does not create duplicate deliveries for the same digest.
- Confirm that subscriber addresses and tokens are absent from repository files and application logs.

The repository contains no subscriber list. Do not paste API credentials, confirmation tokens or subscriber exports into GitHub issues.
