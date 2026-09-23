import { useEffect, useRef, useState } from "react";
import { API_BASE, getToken } from "./api-client";

export interface AgentSocketEvent {
  type: string;
  conversation_id?: string;
  message?: { sender_type: string; content: string; created_at: string };
  [key: string]: unknown;
}

const RECONNECT_DELAY_MS = 3000;

export function useAgentSocket(onEvent: (event: AgentSocketEvent) => void) {
  const socketRef = useRef<WebSocket | null>(null);
  const pendingActionsRef = useRef<string[]>([]);
  const watchedRef = useRef<Set<string>>(new Set());
  const closedByUsRef = useRef(false);
  const onEventRef = useRef(onEvent);
  const [connected, setConnected] = useState(false);

  // Keep the latest callback without tearing down the socket on every render.
  onEventRef.current = onEvent;

  useEffect(() => {
    closedByUsRef.current = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      // Read the token at connect time, not once at mount: the access token
      // is short-lived, so a reconnect after a refresh needs the new one.
      const token = getToken();
      if (!token) return;

      const wsBase = API_BASE.replace(/^http/, "ws");
      const socket = new WebSocket(`${wsBase}/api/v1/conversations/ws/agent?token=${token}`);
      socketRef.current = socket;

      socket.onopen = () => {
        setConnected(true);
        // Re-subscribe to whatever this session was watching before the
        // drop, otherwise an open conversation silently stops updating.
        for (const conversationId of watchedRef.current) {
          socket.send(JSON.stringify({ action: "watch", conversation_id: conversationId }));
        }
        for (const action of pendingActionsRef.current) {
          socket.send(action);
        }
        pendingActionsRef.current = [];
      };

      socket.onclose = () => {
        setConnected(false);
        if (!closedByUsRef.current) {
          reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };

      socket.onmessage = (event) => {
        try {
          onEventRef.current(JSON.parse(event.data));
        } catch {
          // Ignore malformed frames rather than crashing the dashboard.
        }
      };
    }

    connect();

    return () => {
      closedByUsRef.current = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);

  function sendOrQueue(payload: string) {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(payload);
    } else {
      pendingActionsRef.current.push(payload);
    }
  }

  function watch(conversationId: string) {
    watchedRef.current.add(conversationId);
    sendOrQueue(JSON.stringify({ action: "watch", conversation_id: conversationId }));
  }

  function unwatch(conversationId: string) {
    watchedRef.current.delete(conversationId);
    sendOrQueue(JSON.stringify({ action: "unwatch", conversation_id: conversationId }));
  }

  return { connected, watch, unwatch };
}
