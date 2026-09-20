# Security

Security fixes target the current `main` branch. The web app uses Node.js 22 or
newer; the monitoring workflow uses Python 3.12. Install JavaScript dependencies
with `npm ci` so deployments use the reviewed lockfile.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/federicoogallo/Hackathon-MI/security/advisories/new)
when it is available. If reporting is unavailable, contact the maintainer through
their [GitHub profile](https://github.com/federicoogallo) to arrange a private
channel. Do not post credentials, personal data, or exploit details in public
issues.

Include the affected route or file, reproduction steps, expected impact, and a
redacted example. There is no guaranteed response time or bug-bounty program.

## Credentials and deployment

- Keep credentials in local `.env` files, GitHub Actions secrets, or the hosting
  provider's environment settings. Only blank example files belong in Git.
- Variables starting with `NEXT_PUBLIC_` are included in browser code. Never use
  that prefix for provider tokens, signing secrets, or database credentials.
- Rotate a credential immediately if it is exposed. Deleting a file from the
  latest commit does not remove it from Git history or cached copies.
- The Python admin server binds to `127.0.0.1` and must remain local. The public
  review page does not grant administrative access.
- Subscriber addresses and newsletter delivery state belong in the configured
  private data store, never in this repository or generated public assets.

## Dependency checks

CI runs frontend tests, a production build, TypeScript checks, Python tests, and
dependency vulnerability audits. Run the checks locally with:

```sh
npm ci
npm run test:frontend
npm run build
npm run typecheck
npm audit --audit-level=moderate
python -m pytest tests/ -q
python -m pip install pip-audit
python -m pip_audit --local
```

The scoped PostCSS override in `package.json` supplies security fixes while the
supported Next.js 15 release still pins an older PostCSS version. Recheck this
override when upgrading Next.js. Python requirements set patched minimums and
major-version bounds; they are not a complete transitive lockfile.

Automated advisory and credential scans reduce risk but do not prove that a
project is vulnerability-free. Review new APIs, authorization changes, and
external integrations separately before release.
