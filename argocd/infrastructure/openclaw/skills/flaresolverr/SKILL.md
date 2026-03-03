---
name: flaresolverr
description: Bypass Cloudflare and anti-bot protection when fetching web pages. Use when web_fetch or the browser tool fails due to Cloudflare challenges, CAPTCHA walls, or bot detection (403/503 errors, "Just a moment..." pages). Routes requests through FlareSolverr proxy at http://flaresolverr.servarr.svc.cluster.local:8191 to solve challenges and retrieve page content.
metadata: {"openclaw": {"always": true}}
---

# FlareSolverr

FlareSolverr is a proxy server that solves Cloudflare and other anti-bot challenges, returning the page content and cookies once the challenge is solved.

**Endpoint:** `http://flaresolverr.servarr.svc.cluster.local:8191`

## When to Use

Use FlareSolverr when a URL returns:
- Cloudflare "Just a moment..." challenge pages
- HTTP 403 or 503 from Cloudflare
- Bot detection / CAPTCHA blocks

Normal `web_fetch` or `browser` calls should still be tried first. Fall back to FlareSolverr only when they fail due to anti-bot protection.

## Usage

Send a POST request to `/v1`:

```bash
curl -s -X POST http://flaresolverr.servarr.svc.cluster.local:8191/v1 \
  -H "Content-Type: application/json" \
  -d '{
    "cmd": "request.get",
    "url": "https://example.com",
    "maxTimeout": 60000
  }'
```

### Response

```json
{
  "status": "ok",
  "solution": {
    "url": "https://example.com",
    "status": 200,
    "response": "<html>...</html>",
    "cookies": [...],
    "userAgent": "..."
  }
}
```

Extract the page content from `solution.response`. Use `solution.cookies` and `solution.userAgent` if you need to make follow-up requests with the same session.

### Session-based requests (optional)

For sites requiring persistent sessions across multiple requests:

```bash
# Create a session
curl -s -X POST http://flaresolverr.servarr.svc.cluster.local:8191/v1 \
  -H "Content-Type: application/json" \
  -d '{"cmd": "sessions.create", "session": "my-session"}'

# Use the session
curl -s -X POST http://flaresolverr.servarr.svc.cluster.local:8191/v1 \
  -H "Content-Type: application/json" \
  -d '{"cmd": "request.get", "url": "https://example.com", "session": "my-session", "maxTimeout": 60000}'

# Destroy when done
curl -s -X POST http://flaresolverr.servarr.svc.cluster.local:8191/v1 \
  -H "Content-Type: application/json" \
  -d '{"cmd": "sessions.destroy", "session": "my-session"}'
```

## Notes

- `maxTimeout` is in milliseconds; 60000 (60s) is a safe default for most sites
- FlareSolverr runs a real browser internally — responses may take 10–30 seconds
- Only available within the cluster (`servarr` namespace)
