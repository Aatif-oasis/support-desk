"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  AgentSummary,
  TicketDetail,
  addTicketComment,
  getTicket,
  listAgents,
  updateTicket,
} from "@/lib/api-client";
import { fullTimestamp } from "@/lib/format-time";

const STATUSES = ["open", "pending", "resolved", "closed"];
const PRIORITIES = ["low", "medium", "high", "urgent"];

export default function TicketDetailPage() {
  const params = useParams<{ id: string }>();
  const ticketId = params.id;

  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTicket(ticketId)
      .then(setTicket)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load this ticket")
      );

    listAgents()
      .then((agents: AgentSummary[]) => {
        const map: Record<string, string> = {};
        agents.forEach((a) => {
          map[a.id] = a.full_name;
        });
        setAgentNames(map);
      })
      .catch(() => undefined);
  }, [ticketId]);

  async function change(changes: { status?: string; priority?: string }) {
    if (!ticket) return;
    setSaving(true);
    try {
      const updated = await updateTicket(ticketId, changes);
      setTicket({ ...ticket, ...updated });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That change didn't save");
    } finally {
      setSaving(false);
    }
  }

  async function postComment(e: React.FormEvent) {
    e.preventDefault();
    const text = comment.trim();
    if (!text || !ticket) return;
    setSaving(true);
    try {
      const created = await addTicketComment(ticketId, text);
      setTicket({ ...ticket, comments: [...ticket.comments, created] });
      setComment("");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That note didn't save");
    } finally {
      setSaving(false);
    }
  }

  if (error && !ticket) {
    return (
      <div className="page">
        <Link href="/dashboard/tickets" className="back-link">
          Back to tickets
        </Link>
        <div className="alert alert-error">{error}</div>
      </div>
    );
  }

  if (!ticket) return <div className="page">Loading ticket…</div>;

  return (
    <div className="page">
      <Link href="/dashboard/tickets" className="back-link">
        Back to tickets
      </Link>

      <div className="page-head">
        <h2>{ticket.subject}</h2>
      </div>

      <div className="row-meta" style={{ marginBottom: 18 }}>
        <span>{ticket.customer_name || "Unnamed visitor"}</span>
        {ticket.customer_phone && <span>{ticket.customer_phone}</span>}
        {ticket.conversation_id && (
          <Link
            href={`/dashboard/conversations/${ticket.conversation_id}`}
            style={{ color: "var(--accent)" }}
          >
            Open the chat this came from
          </Link>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="panel" style={{ padding: 20, marginBottom: 18 }}>
        <div className="controls">
          <label className="field" style={{ marginBottom: 0 }}>
            Status
            <select
              value={ticket.status}
              disabled={saving}
              onChange={(e) => change({ status: e.target.value })}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>

          <label className="field" style={{ marginBottom: 0 }}>
            Priority
            <select
              value={ticket.priority}
              disabled={saving}
              onChange={(e) => change({ priority: e.target.value })}
            >
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>

          <div className="field" style={{ marginBottom: 0 }}>
            Assigned to
            <div className="static-value">
              {ticket.assigned_agent_id
                ? agentNames[ticket.assigned_agent_id] || "another agent"
                : "Nobody yet"}
            </div>
          </div>
        </div>

        <p className="ticket-description">{ticket.description}</p>
      </div>

      <h3 style={{ marginBottom: 10 }}>Notes</h3>

      <div className="panel" style={{ marginBottom: 16 }}>
        {ticket.comments.length === 0 ? (
          <p className="empty">
            <strong>No notes yet</strong>
            Notes are for your team — the customer never sees them.
          </p>
        ) : (
          ticket.comments.map((c) => (
            <div key={c.id} className="note">
              <div className="note-head">
                {agentNames[c.author_user_id] || "An agent"}, {fullTimestamp(c.created_at)}
              </div>
              <div>{c.text}</div>
            </div>
          ))
        )}
      </div>

      <form onSubmit={postComment} className="composer" style={{ padding: 0, border: "none" }}>
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Add a note for your team"
          aria-label="Add a note for your team"
        />
        <button type="submit" className="btn" disabled={saving}>
          {saving ? "Saving" : "Add note"}
        </button>
      </form>
    </div>
  );
}
