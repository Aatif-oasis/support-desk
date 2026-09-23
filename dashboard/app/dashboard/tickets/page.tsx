"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AgentSummary,
  Ticket,
  listAgents,
  listTickets,
} from "@/lib/api-client";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "pending", label: "Pending" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

// Priority is the one thing worth colouring: an urgent ticket sitting in a
// long list is the failure this page exists to prevent.
export function priorityClass(priority: string): string {
  if (priority === "urgent" || priority === "high") return "pill pill-urgent";
  return "pill";
}

export default function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh(nextStatus: string) {
    try {
      setTickets(await listTickets({ status: nextStatus || undefined }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load tickets");
    }
  }

  useEffect(() => {
    listAgents()
      .then((agents: AgentSummary[]) => {
        const map: Record<string, string> = {};
        agents.forEach((a) => {
          map[a.id] = a.full_name;
        });
        setAgentNames(map);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh(status).finally(() => setLoading(false));
  }, [status]);

  const urgent = tickets.filter(
    (t) => (t.priority === "urgent" || t.priority === "high") && t.status !== "closed"
  ).length;

  return (
    <div className="page">
      <div className="page-head">
        <h2>Tickets</h2>
        {tickets.length > 0 && (
          <span className="count">
            {urgent > 0 ? `${urgent} need attention` : "Nothing urgent"}
          </span>
        )}
      </div>

      <div className="filters">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            className={status === f.value ? "chip chip-on" : "chip"}
            onClick={() => setStatus(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <p className="count">Loading tickets…</p>
      ) : tickets.length === 0 ? (
        <div className="panel">
          <p className="empty">
            <strong>No tickets here</strong>
            Tickets are raised from a conversation when something needs following up
            after the chat ends. Open a chat and choose “Raise a ticket”.
          </p>
        </div>
      ) : (
        <div className="panel">
          {tickets.map((t) => (
            <Link key={t.id} href={`/dashboard/tickets/${t.id}`} className="row row-open">
              <div className="row-body">
                <div className="row-name">{t.subject}</div>
                <div className="row-meta">
                  <span className={priorityClass(t.priority)}>{t.priority}</span>
                  <span className="pill">{t.status}</span>
                  <span>{t.customer_name || "Unnamed visitor"}</span>
                  {t.assigned_agent_id && (
                    <span>With {agentNames[t.assigned_agent_id] || "another agent"}</span>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
