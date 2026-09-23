# Hardening Pass

## What was done

1. **Rate limiting** — Redis fixed-window limiter (`app/core/rate_limit.py`),
   applied to every public unauthenticated endpoint flagged as a gap
   throughout this project:
   - `/customers/identify` — 30/min per IP
   - `/conversations` (start) — 10/min per IP
   - `/conversations/{id}/messages` (public) — 60/min per IP
   - `/knowledge-base/articles` (public) — 60/min per IP
   - `/conversations/{id}/attachments` (public upload) — 20/min per IP

   Authenticated agent/admin endpoints are deliberately NOT rate-limited —
   they're already gated by a valid JWT, and throttling a legitimate
   org_admin's own dashboard would just create false positives.

2. **Security headers** — `X-Content-Type-Options: nosniff`,
   `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`
   on every response; `Strict-Transport-Security` added when not in debug mode.

3. **Startup safety guard** — the app now refuses to start if
   `JWT_SECRET_KEY` is still the default placeholder while running in a
   non-debug environment. Every issued token is forgeable with the
   default secret, so this is a hard stop, not a warning.

## A real bug this pass caught

The rate limiter's first draft imported the module-level `redis_client`
singleton directly instead of going through the `get_redis` dependency.
This is the **exact same class of bug** found earlier with the pub/sub
Redis client (see Modules 1-17 docs) — it broke the automated test suite,
because tests couldn't override it, and every test in the run shared one
physical set of rate-limit counters. Fixed by routing it through
`Depends(get_redis)` like everything else, and disabling rate limiting
entirely in the test `client` fixture (rate-limit *behavior* itself is
verified live below, not via the unit/integration suite, since the suite
legitimately needs to exceed production-scale limits within one run).

## Live verification

**Rate limiting, sequential:** fired 35 rapid `/identify` calls (limit
30/min) — exactly 30 returned 200, the rest 429.

**Rate limiting, under real concurrency:** `scripts/load_test.py` fired
50 *concurrent* conversation-start requests against a 10/min limit —
exactly 10 succeeded, 40 got 429. This matters because a naive
read-then-increment rate limiter can race under concurrency and let more
through than the limit; Redis `INCR` is atomic, and the result confirms
it held exactly at the limit even with 50 requests landing at once.

**Security headers:** confirmed present on a real response via `curl -I`.

**Startup guard:** confirmed the app raises and refuses to start when
`DEBUG=false` and the JWT secret is left at its default.

Run the load test yourself (needs the server, Postgres, and Redis running):
```bash
cd backend && python scripts/load_test.py
```

## Honest finding: latency under load

The load test also measured real latency, and it's worth reporting
plainly rather than only reporting pass/fail: under 50-100 concurrent
requests against the single-process dev server used throughout this
project, **p50 latency was ~580-740ms and p95 was ~715-895ms** — noticeably
slower than the near-instant single-request latency seen in every
earlier module's smoke tests. This is expected from a single `uvicorn`
worker process with no connection pooling tuning handling 50-100
simultaneous requests, not a sign of a code-level bug (all requests
still completed correctly, just slower under contention). Before real
traffic:
- Run multiple `uvicorn`/`gunicorn` worker processes (see deployment docs)
- Tune the SQLAlchemy async engine's connection pool size
  (`app/core/database.py` — currently pool defaults, untuned)
- Consider a proper load balancer in front of multiple backend instances,
  which is exactly what the architecture doc's Redis Pub/Sub design was
  built to support from Module 4 onward

## Known gaps still not addressed

- No automated dependency vulnerability scanning (e.g. `pip-audit`,
  `npm audit` as a CI step) — not run in this pass.
- No penetration testing or third-party security audit — this was a
  self-review, not an external one.
- Rate limits are hardcoded per-endpoint, not configurable per-org or
  per-plan tier — fine for now, a real product would likely want
  higher limits for paying customers.
- No WAF / DDoS protection layer — that's an infrastructure concern
  (e.g. Cloudflare in front of the deployment), not application code.
