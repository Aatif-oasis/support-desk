# Agent Dashboard

## What this is

A Next.js (App Router, TypeScript) app: login, a conversation inbox with
real-time updates, a per-conversation chat view, and a basic Users admin
page. This is the first UI an agent could actually use — everything
before this module was API-only.

## Pages

| Route | Purpose |
|---|---|
| `/login` | Calls `POST /auth/login`, stores the JWT, redirects to `/dashboard` |
| `/dashboard` | Conversation inbox — lists conversations, updates live via the agent WebSocket (new-conversation/new-message/transfer events all trigger a refresh) |
| `/dashboard/conversations/[id]` | The actual chat view — full message history, sends replies via REST, receives live pushes by "watching" the conversation on the same WebSocket proven in Module 4 |
| `/dashboard/users` | List + invite users (calls the real Module 2 endpoints) |

`lib/api-client.ts` and `lib/use-agent-socket.ts` are the only two files
that talk to the backend — every page goes through them, matching the
architecture doc's intent of a thin, typed client layer.

## How this was verified — and where verification stopped

**Real and verified:**
- `npm run build` — a genuine production build: TypeScript type-checking
  and Next.js compilation both pass cleanly across all 6 routes. This
  caught a real bug (the default `next/font/google` import failed
  because this sandbox's network can't reach `fonts.googleapis.com`) —
  fixed by dropping it.
- `npm run start` — the built app actually serves. Verified `/login` and
  `/dashboard/users` return HTTP 200 with the expected markup (a real
  `<title>Oasis Chatbot</title>`, a real `<input type="email">` in the DOM).

**Not verified, and here's why:** for the widget (Module 16), loading the
actual shipped file into `jsdom` and firing real click/input events
worked because it's plain JS with no bundler assumptions. Next.js's
Turbopack-built client bundle expects `document.currentScript` semantics
that `jsdom` doesn't fully replicate, so the same trick fails on this app
with an internal Next.js error — confirmed this is an environment
limitation, not a bug in the dashboard code, by checking the error
originates inside Next's own hydration bootstrap, not in any file written
here. Real interactive testing (actually clicking through login -> inbox
-> chat in a live session) would need a real browser engine (Playwright/
Puppeteer), which needs browser binaries this sandbox's network can't
fetch.

**What this means practically:** the code is real, builds cleanly, and is
written directly against the same REST/WebSocket contracts already
proven live in Modules 1-16 — but no one has actually clicked through it
end-to-end yet. Do that manually before trusting it in front of a real
user: `cd dashboard && npm run build && npm run start`, then open
`http://localhost:3000` in an actual browser with the backend running.

## Known gaps (deferred, not blocking)

- No loading skeletons/spinners beyond a plain "Loading..." string.
- No error boundary for a dropped WebSocket connection — if it
  disconnects, live updates silently stop until the page is refreshed.
- Users page has no pagination (fine at current scale, the same as the
  backend's own default page size).
- No Tickets, Knowledge Base, Quick Replies, or Settings UI yet — those
  backend modules exist and work (Modules 6, 7, 10) but have no dashboard
  screens. The inbox and chat view were prioritized since that's the
  core "customer messages, agent replies" workflow this whole project
  is centered on.
