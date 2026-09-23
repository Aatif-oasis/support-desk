# Embeddable Chat Widget

## What this is

A single vanilla-JS file (`oasis-chatbot-widget.js`) — no framework, no
build step for the business embedding it. Matches the architecture
decision in the main docs: the widget must run correctly regardless of
what the host site is built with, so it can't depend on React/Vue/etc.

## Embedding it

```html
<script
  src="https://your-cdn.example.com/oasis-chatbot-widget.js"
  data-org-slug="acme-corp"
  data-api-base="https://api.youroasis_chatbot.example.com"
></script>
```

That's the entire integration. It renders a chat bubble, and on first
message:
1. Calls the public `/identify` endpoint (Module 3) with browser/locale/page context
2. Starts a conversation (Module 4)
3. Opens a WebSocket to receive agent replies live — the same real-time
   layer proven in Module 4's live test, now driven from an actual
   browser-equivalent environment instead of a Python script

Visitor identity is a `localStorage`-persisted `external_id`, generated
client-side — never a login, matches how Module 3's identify endpoint
was designed.

## How it was verified

`test_widget_live.js` loads the **actual shipped file** — not a
reimplementation — into a real DOM via `jsdom`, using Node's native
`fetch` and `WebSocket` (both real network calls to the real running
server). It then:
1. Dispatches a real click event on the bubble (exactly what a browser does)
2. Types into the real `<input>` and dispatches a real click on Send
3. Confirms the customer's own message renders in the DOM
4. Fetches the conversation via the real agent-facing REST API and posts
   a reply **as if from the dashboard**
5. Waits for the **widget's own WebSocket `onmessage` handler** —
   unmodified — to receive and render that reply

Run it yourself (needs the backend server, Postgres, and Redis running,
plus one registered org — see the main dev docs):

```bash
cd widget
npm install         # installs jsdom (dev-only, not shipped)
node test_widget_live.js
```

## Known gaps (deferred, not blocking)

- No typing indicators, read receipts, or reconnect-on-drop logic for the
  WebSocket — if it disconnects, the customer has to reopen the panel.
- No visual "agent is typing" state.
- Styling is inline and minimal — intentionally, since Module 17 (the
  dashboard) is where visual polish work belongs; this widget's job was
  to prove the wiring, not the design.
- `demo.html` needs `data-org-slug` set to a real registered org's slug
  before it'll work against a live backend.
