# Security policy

Please report suspected vulnerabilities privately to the repository owner. Do not
include real credentials or personal data in public issues.

## Deployment requirements

- Place the application behind an HTTPS reverse proxy or CDN with TLS, connection
  timeouts, rate limiting, and a Web Application Firewall policy.
- Set `POEM_TRUST_PROXY_HEADERS=1` only when the proxy removes client supplied
  `X-Forwarded-*` values and sets trusted replacements.
- Set `POEM_FORCE_SECURE_COOKIES=1` for public HTTPS deployments.
- The built-in access confirmation is not a CAPTCHA. Use Cloudflare Turnstile,
  hCaptcha, or comparable edge protection before exposing expensive endpoints.
