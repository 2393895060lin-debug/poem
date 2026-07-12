# Security policy

Please do not disclose suspected vulnerabilities in public issues. Send the affected
URL, a reproducible description, and any proof-of-concept privately to the repository
owner instead. Do not include real credentials or personal data in a report.

## Deployment requirements

- Put the application behind an HTTPS reverse proxy or CDN that enforces TLS, request
  timeouts, and a Web Application Firewall/rate limit policy.
- Set `POEM_TRUST_PROXY_HEADERS=1` only when the reverse proxy removes client supplied
  `X-Forwarded-*` headers and sets its own trusted values.
- Set `POEM_FORCE_SECURE_COOKIES=1` on HTTPS deployments.
- Keep the repository private while removing accidental sensitive history; changing
  Git history requires coordination with every contributor and fork owner.

The built-in access checkbox is not a CAPTCHA and must not be treated as bot protection.
Use Cloudflare Turnstile, hCaptcha, or a comparable service at the proxy/application
layer before exposing expensive endpoints broadly.
