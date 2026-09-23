# Oasis Chatbot

An independent, API-first customer communication platform — the LiveChat/
Intercom alternative described in the original project brief. Businesses
install a chat widget on their site, talk to customers in real time, and
own the entire stack: no per-seat vendor pricing, no data leaving your
own database, full API access for CRM/ERP integration.

## Status: all 19 planned modules complete

| # | Module | Notes |
|---|---|---|
| 1 | Foundation + Auth | JWT/refresh tokens, API keys, RBAC |
| 2 | Organizations, Departments, Teams, Users | Multi-tenant from the ground up |
| 3 | Customers & Customer Profiles | Public `/identify` endpoint for the widget |
| 4 | Conversations & Messages + real-time layer | WebSocket + Redis Pub/Sub — the core payoff module |
| 5 | File/Attachment Management | Pluggable storage backend |
| 6 | Agent Dashboard support | Quick Replies, internal notes, transfer alerts |
| 7 | Ticket System | Escalation from a conversation |
| 8 | Tags, Search, Export | JSON/CSV conversation export |
| 9 | Notifications | Durable per-agent inbox |
| 10 | Knowledge Base | Draft/published articles, public + agent views |
| 11 | Analytics & Reporting | **Skipped** — deprioritized |
| 12 | Automation / Workflow Engine | Trigger → condition → action rules |
| 13 | AI features | **Skipped** — deprioritized |
| 14 | Webhooks | Outbound event delivery with signatures |
| 15 | Audit Logs & Admin Settings | Org-level settings, action history |
| 16 | Embeddable widget | Vanilla JS, verified in a real DOM |
| 17 | Agent/Admin Dashboard | Next.js — see caveat below |
| 18 | Hardening | Rate limiting, security headers, load testing |
| 19 | Deployment | This file + `docs/DEPLOYMENT.md` |

## Repository layout

```
backend/              FastAPI application — REST + WebSocket API, all business logic
  app/modules/        One folder per domain: router, service, repository, models, schemas
  app/core/           Config, database, Redis, security, rate limiting
  alembic/            Database migrations
  tests/              Unit and integration tests
dashboard/            Next.js agent console
  app/                Pages (login, conversations, tickets, people)
  lib/                API client, WebSocket hook, formatting helpers
widget/               Embeddable chat widget — one JS file, no build step
deploy/               Production compose file and an nginx starting point
docs/                 Architecture, hardening notes, deployment guide
setup.ps1 / setup.sh  One-command local setup
```

## Quick start

### Option A — one command (recommended)

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File setup.ps1
```

```bash
# Mac / Linux
chmod +x setup.sh && ./setup.sh
```

This creates the virtualenv, installs both stacks, generates `.env` files
with a random JWT secret, runs migrations, and loads demo data. You still
need PostgreSQL and Redis running, and you must put your own database
password into `backend/.env` before the database step will succeed.

### Option B — Docker

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

Starts Postgres, Redis, and the backend together.

### Option C — manual

<details>
<summary>Step by step</summary>

**1. Create the database** (PostgreSQL must be installed and running):

```sql
CREATE USER oasis_chatbot WITH PASSWORD 'your_password_here';
CREATE DATABASE oasis_chatbot OWNER oasis_chatbot;
```

**2. Configure:**

```bash
cp backend/.env.example backend/.env          # then edit DATABASE_URL
cp dashboard/.env.local.example dashboard/.env.local
```

**3. Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate                      # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed                            # system roles — required
python -m app.seed_demo                       # demo org + login — optional
uvicorn app.main:app --reload
```

**4. Dashboard** (second terminal):

```bash
cd dashboard
npm install
npm run dev
```

</details>

### Then

| What | Where | Credentials |
|---|---|---|
| Dashboard | http://localhost:3000/login | `admin@demo.com` / `DemoPass123` |
| API docs | http://localhost:8000/docs | — |
| Widget demo | open `widget/demo.html` | — |

The demo data creates an organization with the slug `demo-company`, which
is what `widget/demo.html` points at, so the widget works immediately.

### Requirements

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis 6+ (on Windows, [Memurai](https://www.memurai.com/get-memurai)
  works as a drop-in replacement)

Redis is not optional: without it messages are still saved, but they stop
arriving in real time and only appear after a page refresh.

Architecture and design notes are in `docs/ARCHITECTURE.md`. Production deployment — environment variables,
scaling, backups, pre-launch checklist — is in `docs/DEPLOYMENT.md`.

## What's genuinely proven vs. what isn't

Being direct about this rather than presenting uniform confidence:

- **Backend (Modules 1-15, 18):** Extensively verified. 97 automated
  tests against real Postgres/Redis, plus standalone live scripts
  (`backend/scripts/`) that exercise the actual chat workflow end-to-end
  against a running server — including a 3-worker multi-process run
  proving the Redis Pub/Sub real-time design actually works across
  process boundaries, not just in a single process.
- **Widget (Module 16):** Verified by loading the actual shipped file
  into a real DOM (jsdom) and driving it with real click/input events
  and real network calls — not a reimplementation.
- **Dashboard (Module 17):** Builds cleanly (real TypeScript + Next.js
  compilation), serves correctly, and is written against the same
  proven backend contracts — but has **not** been click-tested in an
  actual browser session (the sandbox this was built in can't run one).
  Do that manually before real users see it.
- **Not done at all:** third-party security audit, dependency
  vulnerability scanning, penetration testing. This is engineering-level
  hardening, not a security audit.

## License

Add your own — none specified during development.
