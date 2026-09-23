"use client";

import { useEffect, useState } from "react";
import {
  ApiKeyCreated,
  ApiKeySummary,
  WEBHOOK_EVENTS,
  WebhookSubscription,
  WebhookSubscriptionCreated,
  createApiKey,
  createWebhook,
  deleteWebhook,
  listApiKeys,
  listWebhooks,
  revokeApiKey,
} from "@/lib/api-client";
import { fullTimestamp, relativeTime } from "@/lib/format-time";

/**
 * Self-service integrations: an org admin mints their own API key and
 * webhook here, without asking the platform owner to do it for them.
 * Both secrets (the API key, the webhook signing secret) are shown
 * exactly once, at creation — the server never returns them again, so
 * this screen is the only chance to copy them down.
 */
export default function IntegrationsPage() {
  return (
    <div className="page">
      <div className="page-head">
        <h2>Integrations</h2>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 13.5, marginTop: -8, marginBottom: 20 }}>
        Connect your own CRM or support tool directly to this workspace — no need to ask us to
        set it up.
      </p>

      <ApiKeysPanel />
      <WebhooksPanel />
    </div>
  );
}

function SecretReveal({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <div className="alert alert-info" style={{ marginBottom: 16 }}>
      <strong>{label}</strong>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
        <code
          style={{
            flex: 1,
            fontSize: 12.5,
            wordBreak: "break-all",
            background: "var(--surface)",
            padding: "6px 10px",
            borderRadius: 6,
          }}
        >
          {value}
        </code>
        <button className="btn btn-quiet" onClick={copy} type="button">
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <p style={{ fontSize: 12.5, marginTop: 8, marginBottom: 0 }}>
        Shown once. Copy it now — this page will not show it again.
      </p>
    </div>
  );
}

function ApiKeysPanel() {
  const [keys, setKeys] = useState<ApiKeySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<ApiKeyCreated | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      setKeys(await listApiKeys());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load API keys");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await createApiKey(name.trim());
      setJustCreated(created);
      setName("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the key");
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(key: ApiKeySummary) {
    if (!confirm(`Revoke "${key.name}"? Anything still using it will stop working immediately.`)) {
      return;
    }
    setBusyId(key.id);
    try {
      await revokeApiKey(key.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revoke that key");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="panel" style={{ padding: 20, marginBottom: 24 }}>
      <h3 style={{ marginTop: 0 }}>API keys</h3>
      <p style={{ color: "var(--muted)", fontSize: 13.5 }}>
        Use a key to read and reply to conversations from your own application. Each key only
        reaches this workspace's data — never another organization's.
      </p>

      {error && <div className="alert alert-error">{error}</div>}
      {justCreated && (
        <SecretReveal label={`API key: ${justCreated.name}`} value={justCreated.api_key} />
      )}

      <form onSubmit={handleCreate} className="filters" style={{ marginBottom: 16 }}>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder='Key name (e.g. "Our CRM")'
          required
          minLength={2}
          className="date-input"
          style={{ minWidth: 220 }}
        />
        <button className="btn" type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create key"}
        </button>
      </form>

      {loading ? (
        <p className="empty">Loading…</p>
      ) : keys.length === 0 ? (
        <p className="empty">No API keys yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Created</th>
              <th>Last used</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id}>
                <td>{k.name}</td>
                <td style={{ whiteSpace: "nowrap", color: "var(--muted)" }}>
                  {fullTimestamp(k.created_at)}
                </td>
                <td style={{ whiteSpace: "nowrap", color: "var(--muted)" }}>
                  {k.last_used_at ? relativeTime(k.last_used_at) : "Never"}
                </td>
                <td>
                  <button
                    className="btn btn-quiet"
                    disabled={busyId === k.id}
                    onClick={() => handleRevoke(k)}
                  >
                    Revoke
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function WebhooksPanel() {
  const [hooks, setHooks] = useState<WebhookSubscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<WebhookSubscriptionCreated | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      setHooks(await listWebhooks());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load webhooks");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function toggleEvent(event: string) {
    setEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    );
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (events.length === 0) {
      setError("Pick at least one event to subscribe to.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const created = await createWebhook(url.trim(), events);
      setJustCreated(created);
      setUrl("");
      setEvents([]);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the webhook");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(hook: WebhookSubscription) {
    if (!confirm("Remove this webhook? It will stop receiving events immediately.")) return;
    setBusyId(hook.id);
    try {
      await deleteWebhook(hook.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove that webhook");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="panel" style={{ padding: 20 }}>
      <h3 style={{ marginTop: 0 }}>Webhooks</h3>
      <p style={{ color: "var(--muted)", fontSize: 13.5 }}>
        Get a signed HTTP call the moment something happens here — a new chat, a reply, a closed
        ticket — instead of polling for it.
      </p>

      {error && <div className="alert alert-error">{error}</div>}
      {justCreated && (
        <SecretReveal label="Signing secret" value={justCreated.secret} />
      )}

      <form onSubmit={handleCreate} style={{ marginBottom: 16 }}>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://your-app.example.com/webhooks/chat-support"
          required
          className="date-input"
          style={{ width: "100%", marginBottom: 10, boxSizing: "border-box" }}
        />
        <div className="filters" style={{ marginBottom: 10 }}>
          {WEBHOOK_EVENTS.map((event) => (
            <label
              key={event}
              className={events.includes(event) ? "chip chip-on" : "chip"}
              style={{ cursor: "pointer" }}
            >
              <input
                type="checkbox"
                checked={events.includes(event)}
                onChange={() => toggleEvent(event)}
                style={{ display: "none" }}
              />
              {event}
            </label>
          ))}
        </div>
        <button className="btn" type="submit" disabled={creating}>
          {creating ? "Creating…" : "Add webhook"}
        </button>
      </form>

      {loading ? (
        <p className="empty">Loading…</p>
      ) : hooks.length === 0 ? (
        <p className="empty">No webhooks yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>URL</th>
              <th>Events</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {hooks.map((h) => (
              <tr key={h.id}>
                <td style={{ fontFamily: "monospace", fontSize: 12.5 }}>{h.url}</td>
                <td style={{ fontSize: 12.5, color: "var(--muted)" }}>
                  {h.events.join(", ")}
                </td>
                <td>
                  <span className={h.is_active ? "pill pill-open" : "pill pill-urgent"}>
                    {h.is_active ? "active" : "inactive"}
                  </span>
                </td>
                <td>
                  <button
                    className="btn btn-quiet"
                    disabled={busyId === h.id}
                    onClick={() => handleDelete(h)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
