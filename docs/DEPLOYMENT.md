# Oasis Chatbot — Deployment Guide (Module 19)

## Topology

```
                         ┌────────────┐
   Browser (widget) ───► │            │
   Browser (dashboard)──►│   nginx    │ (TLS termination, WS upgrade)
                         └─────┬──────┘
                               │
                     ┌─────────┴─────────┐
                     │   backend (N      │  each worker independently
                     │   uvicorn workers)│  subscribes to Redis Pub/Sub
                     └───┬───────────┬───┘
                         │           │
                   ┌─────▼───┐  ┌────▼────┐
                   │Postgres │  │  Redis  │
                   └─────────┘  └─────────┘
```

Four independently deployable pieces:
1. **Backend** (`backend/`) — FastAPI, this guide's main focus
2. **Widget** (`widget/oasis-chatbot-widget.js`) — one static file, goes on a CDN
3. **Dashboard** (`dashboard/`) — Next.js, deployed like any Next.js app
4. **Postgres + Redis** — managed services recommended over self-hosting

## Environment variables (backend)

All in `app/core/config.py`. **Every one of these must be set to a real
value in production** — the defaults are dev-only and the app will
refuse to start with the default `JWT_SECRET_KEY` outside debug mode
(Module 18's startup guard).

| Variable | Production example | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | |
| `DEBUG` | `false` | Must be false for the JWT secret guard to activate |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` | Use a managed Postgres if possible |
| `REDIS_URL` | `redis://host:6379/0` | Needed for real-time chat AND rate limiting — not optional |
| `JWT_SECRET_KEY` | (random, ≥32 bytes) | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ALLOWED_ORIGINS` | `["https://app.yourdomain.com"]` | Your dashboard's real origin, not `*` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Shorter = more secure, more refresh traffic |
| `WEB_CONCURRENCY` | `4` (or `2 × CPU cores`) | See "Scaling" below — this is new for this module |

## Database migrations

**Never run migrations automatically on every container start in
production** (the dev `docker-compose.yml` does this for convenience —
`deploy/docker-compose.prod.yml` deliberately does the same via the startup
command since Alembic migrations are idempotent and safe to re-run, but
seed data is NOT auto-applied in prod, see below).

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend alembic upgrade head
```

Seed data (system roles/permissions — required before the first
`/auth/register` call will work) is a **one-time, deliberate** step, not
part of every deploy:

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend python -m app.seed
```

## Scaling — verified, not just recommended

Module 18's load test found ~580-740ms p50 latency under 50-100
concurrent requests on a **single** worker process. This module verified
the fix: running `uvicorn --workers 3` and re-running the full live chat
workflow test **5 times in a row** — with a customer's WebSocket
connection and an agent's reply landing on different worker processes
purely by chance of which one picked up each request — confirmed the
message still delivered correctly every single time. That's the direct
payoff of building the real-time layer on Redis Pub/Sub back in Module 4:
scaling out workers doesn't require re-architecting anything.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Start at `2 × CPU cores` and measure — `WEB_CONCURRENCY` in
`deploy/docker-compose.prod.yml` controls this.

**Scaling to multiple separate machines** (not just multiple workers on
one host) works the same way — every instance connects to the same
Redis, so the pub/sub fan-out is identical whether workers are processes
on one box or on ten. Nothing in the application code changes; only the
load balancer configuration in front of them does.

## Widget deployment

`widget/oasis-chatbot-widget.js` is one static file with no build step.
Upload it to any CDN/static host (S3+CloudFront, Cloudflare, Vercel,
etc.) and give each customer the embed snippet with their org's real
slug and your backend's real URL:

```html
<script
  src="https://cdn.yourdomain.com/oasis-chatbot-widget.js"
  data-org-slug="their-actual-slug"
  data-api-base="https://api.yourdomain.com"
></script>
```

## Dashboard deployment

Standard Next.js production deploy:

```bash
cd dashboard
npm install
NEXT_PUBLIC_API_BASE=https://api.yourdomain.com npm run build
npm run start   # or deploy the .next output to Vercel/similar
```

`NEXT_PUBLIC_API_BASE` is baked into the client bundle at build time
(confirmed in Module 17 — verified it's present in the built JS chunks),
so it must be set correctly **before** `npm run build`, not just at
runtime.

## Backups

- **Postgres**: standard `pg_dump`/point-in-time-recovery via your
  managed provider, or `pg_dump` on a cron against the container if
  self-hosting. Nothing app-specific here — it's one normalized schema.
- **Redis**: `redis-server --appendonly yes` is already set in
  `deploy/docker-compose.prod.yml`. Redis here is real-time plumbing and rate-
  limit counters, not a system of record — losing it loses in-flight
  WebSocket routing state (recoverable: clients reconnect) and resets
  rate-limit windows, not any conversation/message/customer data (that's
  all in Postgres).
- **Uploaded attachments**: currently local disk (`uploads_data` volume)
  per Module 5's design — back this volume up like any other stateful
  data, or migrate to S3-backed storage (the `storage.py` abstraction
  from Module 5 was built specifically so this swap doesn't touch
  business logic).

## Pre-launch checklist

- [ ] `JWT_SECRET_KEY` set to a real random value, not the default
- [ ] `DEBUG=false`, `ENVIRONMENT=production`
- [ ] `ALLOWED_ORIGINS` set to your real dashboard domain, not a wildcard
- [ ] TLS configured (deploy/nginx.conf.example is a starting point, not a
      finished config — you must add your real certs)
- [ ] `alembic upgrade head` run against the real production database
- [ ] `python -m app.seed` run **once** against the real production database
- [ ] `WEB_CONCURRENCY` set to something greater than 1
- [ ] Postgres and Redis backup strategy actually tested (restore, not
      just backup) at least once
- [ ] Rate limit numbers (Module 18) reviewed against your expected real
      traffic — the defaults were tuned for "reasonable," not for your
      specific customer base
- [ ] Manually clicked through the dashboard in a real browser end-to-end
      (flagged in Module 17 as unverified in this sandbox — do this
      before real users see it)

## What's still explicitly out of scope

Carried over honestly from Module 18, still true: no automated
dependency vulnerability scanning, no third-party security audit, no
WAF/DDoS layer, no per-org configurable rate limits. This guide gets a
working deployment running correctly — it does not replace a real
security review before handling sensitive customer data at scale.
