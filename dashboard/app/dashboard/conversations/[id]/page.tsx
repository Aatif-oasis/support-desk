"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  AgentSummary,
  ConversationDetail,
  Message,
  closeConversation,
  createTicket,
  getConversation,
  listAgents,
  markConversationRead,
  sendAgentMessage,
  transferConversation,
} from "@/lib/api-client";
import { useAgentSocket } from "@/lib/use-agent-socket";
import { clockTime, dayLabel, fullTimestamp, isDifferentDay } from "@/lib/format-time";

export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const conversationId = params.id;

  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [agentNames, setAgentNames] = useState<Record<string, string>>({});
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferTo, setTransferTo] = useState("");
  const [transferring, setTransferring] = useState(false);
  const [customerReadAt, setCustomerReadAt] = useState<string | null>(null);
  const [supervisor, setSupervisor] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  // Raising a ticket is how a chat turns into follow-up work once the
  // customer has gone. It starts from here rather than from the tickets
  // page because this is where the agent already has the context.
  const [ticketOpen, setTicketOpen] = useState(false);
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketDetail, setTicketDetail] = useState("");
  const [ticketPriority, setTicketPriority] = useState("medium");
  const [ticketSaving, setTicketSaving] = useState(false);
  const [ticketDone, setTicketDone] = useState<string | null>(null);

  function addMessageIfNew(prev: ConversationDetail, incoming: Message) {
    if (prev.messages.some((m) => m.id === incoming.id)) return prev;
    return { ...prev, messages: [...prev.messages, incoming] };
  }

  const { watch, unwatch } = useAgentSocket((event) => {
    if (event.type === "new_message" && event.conversation_id === conversationId && event.message) {
      const incoming = event.message as unknown as Message;
      if (!incoming.id) return;
      setConversation((prev) => (prev ? addMessageIfNew(prev, incoming) : prev));
    }
    if (
      event.type === "supervisor_viewing" &&
      event.conversation_id === conversationId &&
      typeof event.viewer_name === "string"
    ) {
      // Ephemeral on purpose: it tells the agent someone senior is
      // looking right now, then gets out of the way.
      setSupervisor(event.viewer_name);
      setTimeout(() => setSupervisor(null), 30000);
    }
    if (
      event.type === "read_receipt" &&
      event.conversation_id === conversationId &&
      event.by === "customer"
    ) {
      setCustomerReadAt(typeof event.at === "string" ? event.at : null);
    }
    if (event.type === "conversation_transferred" && event.conversation_id === conversationId) {
      getConversation(conversationId).then(setConversation).catch(() => undefined);
    }
  });

  // Opening the chat is what "reading" means here, so tell the server as
  // soon as the page mounts and again whenever a new message arrives
  // while the agent is still looking at it.
  useEffect(() => {
    if (!conversation) return;
    markConversationRead(conversationId).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, conversation?.messages.length]);

  useEffect(() => {
    getConversation(conversationId)
      .then((data) => {
        setConversation(data);
        setCustomerReadAt(data.customer_last_read_at);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load this conversation")
      );

    listAgents()
      .then((list: AgentSummary[]) => {
        const nameMap: Record<string, string> = {};
        list.forEach((a) => {
          nameMap[a.id] = a.full_name;
        });
        setAgentNames(nameMap);
        // Suspended accounts are filtered out here as well as rejected by
        // the server — offering a name that will fail is worse than not
        // offering it.
        setAgents(list.filter((a) => a.status !== "suspended"));
      })
      .catch(() => undefined);

    watch(conversationId);
    return () => unwatch(conversationId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    listRef.current?.scrollTo(0, listRef.current.scrollHeight);
  }, [conversation?.messages.length]);

  async function handleSend() {
    const content = draft.trim();
    if (!content || sending) return;
    setDraft("");
    setSending(true);
    try {
      const message = await sendAgentMessage(conversationId, content);
      setConversation((prev) => (prev ? addMessageIfNew(prev, message) : prev));
      setError(null);
    } catch (err) {
      // Put the text back rather than losing what the agent typed.
      setDraft(content);
      setError(err instanceof Error ? err.message : "That message didn't send. Try again.");
    } finally {
      setSending(false);
    }
  }

  async function handleTransfer(agentId: string | null) {
    if (!conversation) return;
    setTransferring(true);
    try {
      const updated = await transferConversation(conversationId, agentId);
      setConversation((prev) => (prev ? { ...prev, ...updated } : prev));
      setTransferOpen(false);
      setTransferTo("");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not transfer this conversation");
    } finally {
      setTransferring(false);
    }
  }

  async function handleRaiseTicket(e: React.FormEvent) {
    e.preventDefault();
    if (!conversation || !ticketSubject.trim() || !ticketDetail.trim()) return;
    setTicketSaving(true);
    try {
      const ticket = await createTicket({
        customer_id: conversation.customer_id,
        conversation_id: conversation.id,
        subject: ticketSubject.trim(),
        description: ticketDetail.trim(),
        priority: ticketPriority,
      });
      setTicketDone(ticket.id);
      setTicketOpen(false);
      setTicketSubject("");
      setTicketDetail("");
      setTicketPriority("medium");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not raise the ticket");
    } finally {
      setTicketSaving(false);
    }
  }

  async function handleClose() {
    try {
      const updated = await closeConversation(conversationId);
      setConversation((prev) => (prev ? { ...prev, ...updated } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not close this conversation");
    }
  }

  if (error && !conversation) {
    return (
      <div className="page">
        <Link href="/dashboard" className="back-link">
          Back to conversations
        </Link>
        <div className="alert alert-error">{error}</div>
      </div>
    );
  }

  if (!conversation) return <div className="page">Loading conversation…</div>;

  const assignedName = conversation.assigned_agent_id
    ? agentNames[conversation.assigned_agent_id] || "another agent"
    : null;

  return (
    <div className="chat">
      <div className="chat-head">
        <div>
          <Link href="/dashboard" className="back-link">
            Back to conversations
          </Link>
          <div className="chat-customer">{conversation.customer_name || "Unnamed visitor"}</div>
          <div className="chat-contact">
            {conversation.customer_phone || "No phone given"}
            {conversation.customer_email ? `, ${conversation.customer_email}` : ""}
          </div>
          <div className="chat-meta">
            <span className={conversation.status === "closed" ? "pill" : "pill pill-open"}>
              {conversation.status}
            </span>
            <span>{assignedName ? `With ${assignedName}` : "Not yet claimed"}</span>
            {conversation.messages.length > 0 && (
              <span title={fullTimestamp(conversation.messages[0].created_at)}>
                Started {dayLabel(conversation.messages[0].created_at).toLowerCase()} at{" "}
                {clockTime(conversation.messages[0].created_at)}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          <button className="btn btn-quiet" onClick={() => setTransferOpen((v) => !v)}>
            Transfer
          </button>
          <button className="btn btn-quiet" onClick={() => setTicketOpen((v) => !v)}>
            Raise a ticket
          </button>
          {conversation.status !== "closed" && (
            <button className="btn btn-quiet" onClick={handleClose}>
              Close chat
            </button>
          )}
        </div>
      </div>

      {transferOpen && (
        <div className="ticket-form">
          <div className="controls">
            <label className="field" style={{ marginBottom: 0 }}>
              Hand this chat to
              <select value={transferTo} onChange={(e) => setTransferTo(e.target.value)}>
                <option value="">Choose someone</option>
                {agents
                  .filter((a) => a.id !== conversation.assigned_agent_id)
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.full_name}
                    </option>
                  ))}
              </select>
            </label>

            <button
              className="btn"
              disabled={!transferTo || transferring}
              onClick={() => handleTransfer(transferTo)}
            >
              {transferring ? "Transferring" : "Transfer"}
            </button>

            {/* The other half of a transfer: letting go without picking a
                person, so an agent going off shift can put the chat back
                where anyone can claim it. */}
            {conversation.assigned_agent_id && (
              <button
                className="btn btn-quiet"
                disabled={transferring}
                onClick={() => handleTransfer(null)}
              >
                Return to queue
              </button>
            )}

            <button className="btn btn-quiet" onClick={() => setTransferOpen(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {ticketDone && (
        <div className="alert alert-info" style={{ margin: "12px 24px 0" }}>
          Ticket raised.{" "}
          <Link href={`/dashboard/tickets/${ticketDone}`} style={{ textDecoration: "underline" }}>
            Open it
          </Link>
        </div>
      )}

      {ticketOpen && (
        <form onSubmit={handleRaiseTicket} className="ticket-form">
          <label className="field">
            What needs following up?
            <input
              value={ticketSubject}
              onChange={(e) => setTicketSubject(e.target.value)}
              placeholder="Refund not received for order 4821"
              required
            />
          </label>

          <label className="field">
            Details
            <input
              value={ticketDetail}
              onChange={(e) => setTicketDetail(e.target.value)}
              placeholder="What you promised the customer, and what happens next"
              required
            />
          </label>

          <div className="controls">
            <label className="field" style={{ marginBottom: 0 }}>
              Priority
              <select value={ticketPriority} onChange={(e) => setTicketPriority(e.target.value)}>
                <option value="low">low</option>
                <option value="medium">medium</option>
                <option value="high">high</option>
                <option value="urgent">urgent</option>
              </select>
            </label>
            <button type="submit" className="btn" disabled={ticketSaving}>
              {ticketSaving ? "Raising" : "Raise ticket"}
            </button>
            <button
              type="button"
              className="btn btn-quiet"
              onClick={() => setTicketOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {supervisor && (
        <div className="alert alert-info" style={{ margin: "12px 24px 0", marginBottom: 0 }}>
          {supervisor} is viewing this conversation.
        </div>
      )}

      {error && (
        <div className="alert alert-error" style={{ margin: "12px 24px 0", marginBottom: 0 }}>
          {error}
        </div>
      )}

      <div ref={listRef} className="thread">
        {/* Only the last outgoing message carries the receipt. Marking
            every one "Seen" is noise: the thread is read top to bottom, so
            the last one tells you about all of them. */}
        {conversation.messages.map((m, index) => {
          const previous = index > 0 ? conversation.messages[index - 1] : null;
          const isLastAgentMessage =
            m.sender_type === "agent" &&
            !conversation.messages.slice(index + 1).some((later) => later.sender_type === "agent");
          const seen =
            isLastAgentMessage &&
            !!customerReadAt &&
            new Date(customerReadAt).getTime() >= new Date(m.created_at).getTime();
          // A date heading only when the day actually changes, so a chat
          // that happened in one sitting isn't broken up by noise.
          const showDay = !previous || isDifferentDay(previous.created_at, m.created_at);

          if (m.sender_type === "system") {
            return (
              <div key={m.id}>
                {showDay && <div className="day-divider">{dayLabel(m.created_at)}</div>}
                <div className="system-line" title={fullTimestamp(m.created_at)}>
                  {m.content}
                  <span className="system-time">{clockTime(m.created_at)}</span>
                </div>
              </div>
            );
          }

          return (
            <div key={m.id}>
              {showDay && <div className="day-divider">{dayLabel(m.created_at)}</div>}
              <div
                className={m.sender_type === "agent" ? "bubble-row bubble-row-agent" : "bubble-row"}
              >
                <div className="bubble-group">
                  <div
                    className={
                      m.sender_type === "agent" ? "bubble bubble-agent" : "bubble bubble-customer"
                    }
                  >
                    {m.content}
                  </div>
                  <div className="bubble-time" title={fullTimestamp(m.created_at)}>
                    {clockTime(m.created_at)}
                    {isLastAgentMessage && (
                      <span className={seen ? "receipt receipt-seen" : "receipt"}>
                        {seen ? "Seen" : "Sent"}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="composer">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Write a reply"
          aria-label="Write a reply"
        />
        <button className="btn" onClick={handleSend} disabled={sending}>
          {sending ? "Sending" : "Send"}
        </button>
      </div>
    </div>
  );
}
