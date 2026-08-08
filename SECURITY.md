# Security policy

## Supported versions

We aim to support the latest tagged release. Older versions may not receive fixes.

## Runtime security controls

Elpis treats network, source, and model-provider inputs as hostile:

- Admin authentication uses salted PBKDF2-SHA256 password hashes. Legacy database
  plaintext credentials are upgraded after successful verification; environment
  credentials are not copied into SQLite. Login failures are throttled per client
  for a bounded window.
- Outbound HTTP fetches accept only HTTP(S) URLs without embedded credentials,
  reject private, loopback, link-local, reserved, and unspecified targets, and
  re-check DNS resolution before every request and redirect. Failed DNS lookups
  are rejected. Feed, article, website, podcast, and discovery fetches do not
  follow redirects without validating the destination.
- OPML and other uploaded XML is size-limited and parsed with external entity and
  DTD declarations rejected.
- Article titles and bodies are serialized as explicitly marked untrusted JSON
  data in summarization and relevance-ranking prompts. Provider responses are
  parsed and sanitized before persistence; hidden reasoning is not published.
- Anonymous publication reads are intentionally narrow. Administrative and
  operational APIs, including source configuration and digest controls, require
  the admin session or bearer credential. Public discovery is bounded and
  rate-limited.
- Secrets such as provider keys, session keys, and proxy credentials are redacted
  from browser payloads and network error messages.

### Deployment assumptions and residual risks

Run Elpis behind TLS and an authenticated reverse proxy when it is reachable
outside a trusted private network. Set `DIGEST_PWA_SESSION_SECRET` and
`CONDENSEIT_AUTH_PASSWORD` (or configure an admin password through the UI) before
exposing the service. Use an egress proxy or firewall policy when DNS rebinding
protection must cover infrastructure-specific resolver behavior. Keep the
application and dependencies updated.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

Instead, contact the repository maintainers through a private channel (for example
GitHub Security Advisories for this repository, if enabled).

Include:

- A short description of the issue and its impact
- Steps to reproduce (if safe to share)
- Any suggested fix or patch (optional)

We will acknowledge receipt as soon as we can and work on a coordinated disclosure.
