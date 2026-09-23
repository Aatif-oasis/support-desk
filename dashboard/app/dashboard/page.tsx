"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AgentSummary,
  ConversationSummary,
  CurrentUser,
  getCurrentUser,
  listAgents,
  listConversations,
  transferConversation,
} from "@/lib/api-client";
import { useAgentSocket } from "@/lib/use-agent-socket";
import { fullTimestamp, isIdle, relativeTime, stopwatch } from "@/lib/format-time";

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [suspendedAgents, setSuspendedAgents] = useState<Set<string>>(new Set());
  const [claiming, setClaiming] = useState<string | null>(null);

  // A chat left behind by someone who has been suspended belongs to nobody
  // in practice: it shows as assigned, so no agent can open it, and the
  // customer waits. Supervisors get a one-click way to pull it back.
  async function claimStranded(conversationId: string) {
    if (!me) return;
    setClaiming(conversationId);
    try {
      await transferConversation(conversationId, me.id);
      await refresh();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not take this conversation");
    } finally {
      setClaiming(null);
    }
  }

  // Plain agents see the whole board but may only open their own chats and
  // unclaimed ones. Supervisors can open anything.
  function canOpen(assignedAgentId: string | null): boolean {
    if (!me) return true;
    if (me.roles.some((r) => r === "org_admin" || r === "team_manager")) return true;
    return assignedAgentId === null || assignedAgentId === me.id;
  }

  async function refresh() {
    try {
      const convData = await listConversations();
      setConversations(convData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load conversations");
      return;
    }

    // Names are a nice-to-have, so a failure here must never blank the
    // conversation list.
    try {
      const agents = await listAgents();
      const nameMap: Record<string, string> = {};
      const suspended = new Set<string>();
      agents.forEach((a: AgentSummary) => {
        nameMap[a.id] = a.full_name;
        if (a.status === "suspended") suspended.add(a.id);
      });
      setAgentNames(nameMap);
      setSuspendedAgents(suspended);
    } catch {
      // Leave whatever names we already had.
    }
  }

  useEffect(() => {
    setMe(getCurrentUser());
    refresh().finally(() => setLoading(false));
  }, []);

  // Ticks every second so the waiting stopwatch actually counts. The
  // relative timestamps elsewhere only change once a minute, but they
  // cost nothing to re-render alongside it.
  const [, forceTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  useAgentSocket((event) => {
    if (event.type === "new_conversation") {
      setNotice("A new chat just came in.");
      refresh();
      setTimeout(() => setNotice(null), 4000);
    }
    if (event.type === "new_message" || event.type === "conversation_transferred") {
      refresh();
    }
  });

  const waiting = conversations.filter((c) => !c.assigned_agent_id).length;

  if (loading) return <div className="page">Loading conversations…</div>;

  return (
    <div className="page">
      <div className="page-head">
        <h2>Conversations</h2>
        {conversations.length > 0 && (
          <span className="count">
            {waiting > 0
              ? `${waiting} waiting for someone`
              : "Everyone has been picked up"}
          </span>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-info">{notice}</div>}

      {conversations.length === 0 && !error ? (
        <div className="panel">
          <p className="empty">
            <strong>No chats yet</strong>
            When someone opens the chat widget on your website, they show up here
            straight away — no refresh needed.
          </p>
        </div>
      ) : (
        <div className="panel">
          {conversations.map((c) => {
            const assigned = c.assigned_agent_id
              ? agentNames[c.assigned_agent_id] || "another agent"
              : null;
            const openable = canOpen(c.assigned_agent_id);
            const rowClass = [
              "row",
              !c.assigned_agent_id ? "row-waiting" : "",
              openable ? "row-open" : "row-locked",
            ]
              .filter(Boolean)
              .join(" ");

            const body = (
              <div className="row-body">
                <div className="row-top">
                  <div className="row-name">
                    {c.customer_name || "Unnamed visitor"}
                    {c.customer_phone && <span className="row-phone">{c.customer_phone}</span>}
                  </div>
                  {c.last_message_at && (
                    <span className="row-time" title={fullTimestamp(c.last_message_at)}>
                      {relativeTime(c.last_message_at)}
                    </span>
                  )}
                </div>
                <div className="row-meta">
                  {c.assigned_agent_id ? (
                    <>
                      <span className={c.status === "closed" ? "pill" : "pill pill-open"}>
                        {c.status}
                      </span>
                      <span>With {assigned}</span>
                      {/* Quiet marker, not an alarm: a chat can sit idle
                          simply because the customer is reading a reply. */}
                      {c.status !== "closed" && isIdle(c.last_message_at) && (
                        <span className="pill">Idle</span>
                      )}
                    </>
                  ) : (
                    <span className="pill pill-waiting">
                      Waiting {stopwatch(c.last_message_at)}
                    </span>
                  )}
                  {!openable && <span>Locked — another agent is handling this</span>}
                  {c.assigned_agent_id && suspendedAgents.has(c.assigned_agent_id) && (
                    <span className="pill pill-urgent">Agent no longer active</span>
                  )}
                </div>
              </div>
            );

            // Rows an agent can't open are still listed, so the board answers
            // "is this customer already being helped?" without sending anyone
            // to a permissions error to find out.
            const stranded =
              !!c.assigned_agent_id && suspendedAgents.has(c.assigned_agent_id);
            const canClaim =
              stranded &&
              !!me?.roles.some((r) => r === "org_admin" || r === "team_manager");

            if (canClaim) {
              return (
                <div key={c.id} className={`${rowClass} row-open`}>
                  {body}
                  <button
                    className="btn btn-quiet"
                    style={{ flexShrink: 0, alignSelf: "center" }}
                    disabled={claiming === c.id}
                    onClick={() => claimStranded(c.id)}
                  >
                    {claiming === c.id ? "Taking" : "Take over"}
                  </button>
                </div>
              );
            }

            return openable ? (
              <Link key={c.id} href={`/dashboard/conversations/${c.id}`} className={rowClass}>
                {body}
              </Link>
            ) : (
              <div
                key={c.id}
                className={rowClass}
                title="This conversation is assigned to another agent"
              >
                {body}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
