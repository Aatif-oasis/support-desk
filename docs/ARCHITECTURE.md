# Architecture and Build Notes

## Status

**Modules 1-18** are complete, tested, and verified against real
PostgreSQL + Redis instances in this environment — exercised live over
HTTP, WebSocket, and real file I/O end-to-end, not just unit-tested.

1. Foundation + Auth
2. Organizations, Departments, Teams, Users
3. Customers & Customer Profiles
4. Conversations & Messages + real-time WebSocket layer
5. File/Attachment Management
6. Agent Dashboard support — Quick Replies, Internal Notes, transfer notifications
7. Ticket System
8. Tags, Conversation Search, Export
9. Notifications
10. Knowledge Base
12. Automation / Workflow Engine (11: Analytics skipped per decision)
14. Webhooks (chat.created/closed, message.received/sent, customer.created/updated, ticket.created/updated — HMAC-signed, agent.online/offline deferred, no presence tracking yet)
15. Audit Logs & Admin Settings
16. Embeddable widget (vanilla JS, verified live against real DOM + real server)
17. Agent/Admin Dashboard (Next.js — login, inbox, chat, users; see dashboard/README.md)
18. Hardening pass — rate limiting, security headers, load testing (see module-18-hardening.md)

- 97/97 (plus live rate-limit & load tests, see module-18-hardening.md) automated tests passing (`tests/unit`, `tests/integration`)
- Alembic migrations generated cleanly from the models with no manual
  fixes; `alembic check` confirms no schema drift
- Module 4 was additionally verified with a **live end-to-end script**
  (`backend/scripts/live_chat_workflow_test.py`) that runs the exact
  customer→agent chat workflow against the real running server, real
  Postgres, and real Redis: customer opens a chat and sends "Hello" →
  backend persists it → agent's dashboard WebSocket receives a
  `new_conversation` push *before the agent has even opened anything* →
  agent watches the conversation and replies via REST → customer's
  WebSocket receives the reply *instantly, unprompted, no polling* → both
  messages are confirmed persisted and retrievable. Run it yourself:
  ```bash
  cd backend && python scripts/live_chat_workflow_test.py
  ```
- Module 6's transfer notification was verified the same way —
  `backend/scripts/live_transfer_notification_test.py` connects an
  agent's dashboard socket, transfers a conversation to them via REST,
  and confirms a `conversation_transferred` event arrives on their
  WebSocket in real time.
  (both scripts require the server, Postgres, and Redis all running — see below)
- Module 7 was verified live end-to-end: customer sends a message → agent
  escalates the conversation to a ticket → agent adds an internal comment
  → agent resolves it → full ticket detail with comment thread confirmed
  via REST.

### Module 7 (Ticket System) design notes

- **Agent-only, by design** — there's no public/widget endpoint. Matches
  the original spec: "Create ticket" is listed under Agent Features, not
  Customer Features. A customer never sees or creates a ticket directly.
- **`conversation_id` is nullable** — a ticket usually escalates from a
  chat, but the schema doesn't force every ticket to have started as a
  conversation, since a future channel (email) could create one directly.
- **`customer_id` is validated against the acting agent's own
  organization at creation time** — verified that an agent cannot create
  a ticket against another org's customer by guessing a UUID (404, not a
  silent cross-tenant write).
- **Ticket comments are a separate table from `ConversationNote`**
  (Module 6) — a comment is scoped to the ticket's resolution work, not
  the live chat. Never visible to the customer, same as conversation notes.
- **Ownership rule matches conversations**: an `org_admin`/`team_manager`
  can modify any ticket; a plain `agent` can only modify a ticket that's
  unassigned or assigned to them — verified live and in tests
  (`test_agent_cannot_modify_ticket_assigned_to_another_agent`).
- **`resolved_at` is managed automatically** — set when status moves to
  `resolved`/`closed`, cleared if reopened to `open`/`pending`. Not
  something the client sets directly.

### Module 5 (Attachments) design notes

- **Storage is abstracted** (`app/modules/attachments/storage.py`) behind
  a `save`/`read`/`delete` interface. `LocalDiskStorage` is what runs
  today (files under `backend/uploads/{organization_id}/`); swapping to
  S3/GCS later means writing one new class with the same three methods —
  nothing in the service or router layer needs to change.
- An attachment always belongs to exactly one Message (not directly to a
  Conversation) — matches how the message list already renders
  everything in order.
- `MAX_UPLOAD_SIZE_BYTES` defaults to 20MB (`app/core/config.py`) — files
  over that limit are rejected with 422 before ever touching disk.
- Verified live: a real binary file uploaded by a customer was confirmed
  byte-identical after download by both the customer and an agent; a
  spoofed `external_id` on download was rejected (403); an empty upload
  was rejected (422).

### Module 6 (Agent Dashboard support) design notes

- **Quick Replies** are pure templates (`title` + `content`) — an agent
  fetches the org's list and sends the content as a normal message via
  the existing `POST /conversations/{id}/messages`. There's no separate
  "send a quick reply" endpoint; that would just be a second way to do
  the same write.
- **Conversation Notes** are a distinct table from `Customer.notes`
  (Module 3). Customer notes are about the *person*, across every
  conversation they've ever had. Conversation notes are scoped to *one
  specific chat* — e.g. "escalated to billing, waiting on their reply."
  Verified live that a note added to a conversation never shows up in
  that conversation's `messages` list — the customer-facing thread and
  the internal note thread are fully separate, by table, not just by a
  visibility flag on one shared table.
- **Transfer notification** closes the gap flagged after Module 4: when
  `PATCH /conversations/{id}` changes `assigned_agent_id`, a
  `conversation_transferred` event now publishes to the org-wide agent
  channel with the new and previous assignee IDs, so every connected
  dashboard can highlight it for the right agent.

## Real bugs the live testing caught in this project

- **Redis client / event-loop binding.** The module-level `redis_client`
  singleton in `app/core/redis.py` is fine in production (one process, one
  long-lived event loop) but broke under pytest-asyncio, which gives each
  test function its own event loop — the singleton stayed bound to
  whichever loop existed when the module was first imported. Fixed by
  having the test `client` fixture override `get_redis` with a
  connection created fresh per test. Worth remembering if you ever see
  `RuntimeError: Future attached to a different loop` elsewhere.

## API Surface So Far

| Module | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `/login`, `/refresh`, `/logout`, `POST /auth/api-keys` |
| Organizations (Super Admin only) | `GET /organizations`, `GET/{id}`, `PATCH /{id}`, `PATCH /{id}/status` |
| Departments | `GET`, `POST`, `GET/{id}`, `PATCH/{id}`, `DELETE/{id}` |
| Teams | `GET`, `POST`, `GET/{id}`, `PATCH/{id}`, `DELETE/{id}`, `POST/{id}/members`, `DELETE/{id}/members/{user_id}`, `GET/{id}/members` |
| Users | `GET`, `POST` (invite), `GET/{id}`, `PATCH/{id}`, `DELETE/{id}` (deactivate), `POST/{id}/roles` |
| Customers — public (no auth) | `POST /public/{org_slug}/customers/identify` |
| Customers — agent-facing | `GET /customers`, `GET/{id}`, `PATCH/{id}`, `POST/{id}/notes` |
| Conversations — public (no auth) | `POST /public/{org_slug}/conversations` (start chat), `POST /public/{org_slug}/conversations/{id}/messages`, `WS /public/{org_slug}/conversations/{id}/ws` |
| Conversations — agent-facing | `GET /conversations`, `GET/{id}`, `POST/{id}/messages`, `PATCH/{id}` (assign/status), `POST/{id}/notes`, `GET/{id}/notes`, `WS /conversations/ws/agent` |
| Attachments — public (no auth) | `POST /public/{org_slug}/conversations/{id}/attachments`, `GET /public/{org_slug}/conversations/attachments/{id}/download` |
| Attachments — agent-facing | `POST /conversations/{id}/attachments`, `GET /conversations/attachments/{id}/download` |
| Quick Replies | `GET`, `POST` (org_admin), `PATCH/{id}` (org_admin), `DELETE/{id}` (org_admin) |
| Tickets | `GET`, `POST`, `GET/{id}`, `PATCH/{id}`, `POST/{id}/comments`, `GET/{id}/comments` |

### How the real-time layer works

```
Agent's browser  <--WS--  connection_manager (local)  <--pub/sub--  Redis  <--pub/sub--  connection_manager (local)  --WS-->  Customer's browser
                                    ^                                                              ^
                                    |                                                              |
                        agent-side FastAPI process                                     (could be a different process —
                                                                                          this is what makes it scale
                                                                                          horizontally, see architecture doc)
```

Every write (`POST .../messages`) publishes to Redis; every process
(there's one in dev, but the design doesn't assume that) runs a
background listener (started in `main.py`'s `lifespan`) that re-broadcasts
whatever it receives to whichever local WebSocket connections it's
holding. This is why a customer's reply shows up on an agent's socket
even though they're on completely separate connections — neither knows
about the other directly, Redis is the only thing connecting them.

Two channel families:
- `conversation:{id}` — full message content, for whoever has that
  specific chat open (customer widget, or an agent who sent `{"action":
  "watch", "conversation_id": ...}`)
- `org-agents:{organization_id}` — lightweight notifications (new
  conversation alerts, message previews) for every agent's dashboard,
  regardless of which chat they currently have open

### Known gaps (intentionally deferred)

- No typing indicators, read receipts, or online/offline status — those
  are separate line items in the original Chat Features list, not part
  of any module built so far.
- No rate limiting on the public endpoints (same caveat as Module 3's
  identify endpoint).

## Running Locally (Docker — recommended)

```bash
docker compose up --build
```

This starts Postgres, Redis, and the backend, runs migrations, seeds system
roles/permissions, and starts the API with hot reload at `http://localhost:8000`.

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- Health check: http://localhost:8000/api/health

## Running Locally (without Docker)

Requires Postgres 16+ and Redis running locally.

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # edit DATABASE_URL / REDIS_URL if needed

alembic upgrade head
python -m app.seed

uvicorn app.main:app --reload
```

## Running Tests

```bash
cd backend
pytest tests/ -v
```

Tests run against an in-memory SQLite database via fixtures in
`tests/conftest.py` — no external services required. This is what CI uses.

## Creating a New Migration

After changing any model in `app/modules/*/models.py`:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

Always review the autogenerated migration file before committing — Alembic
autogenerate is a starting point, not a guarantee (it won't detect some
column-level changes like check constraints).

## Adding a New Module

Follow the pattern established by `app/modules/auth/`:

1. `models.py` — SQLAlchemy models, inheriting `AuditMixin` or the
   tenant-scoped pattern (`organization_id` FK + index)
2. `schemas.py` — Pydantic request/response models
3. `repository.py` — subclass `BaseRepository`, add entity-specific queries
4. `service.py` — business logic, raises `app.core.exceptions.DomainError`
   subclasses (never raw `HTTPException`)
5. `router.py` — FastAPI routes, thin — delegates to the service
6. Register the router in `app/main.py`
7. Import the models in `alembic/env.py` so migrations pick them up
8. Write tests in `tests/unit/` and `tests/integration/`

## Known Environment Gotcha

`passlib[bcrypt]` 1.7.4 is incompatible with `bcrypt` >= 4.1 (passlib's
internal backend self-test raises `ValueError: password cannot be longer
than 72 bytes` even for short passwords). `requirements.txt` pins
`bcrypt==4.0.1` to avoid this — don't upgrade bcrypt without re-verifying
password hashing still works.
