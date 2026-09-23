"""
Purely local bookkeeping: which WebSocket objects on THIS process are
listening to which conversation, and which agents on THIS process are
connected for org-wide notifications. This class never talks to Redis —
app/websockets/pubsub.py is the bridge that makes broadcasts here reach
every process, not just the one that received the originating HTTP request.
"""
import uuid

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._conversation_sockets: dict[uuid.UUID, set[WebSocket]] = {}
        self._agent_sockets: dict[uuid.UUID, set[WebSocket]] = {}

    # ---------- Conversation rooms (customer widget + agents viewing a chat) ----------

    def join_conversation(self, conversation_id: uuid.UUID, websocket: WebSocket) -> None:
        self._conversation_sockets.setdefault(conversation_id, set()).add(websocket)

    def leave_conversation(self, conversation_id: uuid.UUID, websocket: WebSocket) -> None:
        sockets = self._conversation_sockets.get(conversation_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                del self._conversation_sockets[conversation_id]

    async def broadcast_to_conversation(self, conversation_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._conversation_sockets.get(conversation_id, ())):
            try:
                await websocket.send_json(payload)
            except Exception:
                # A dead socket here just means it hasn't been cleaned up by
                # its own disconnect handler yet — never let one bad
                # connection break delivery to everyone else in the room.
                self.leave_conversation(conversation_id, websocket)

    # ---------- Org-wide agent notification channel (dashboard badges) ----------

    def join_org_agents(self, organization_id: uuid.UUID, websocket: WebSocket) -> None:
        self._agent_sockets.setdefault(organization_id, set()).add(websocket)

    def leave_org_agents(self, organization_id: uuid.UUID, websocket: WebSocket) -> None:
        sockets = self._agent_sockets.get(organization_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                del self._agent_sockets[organization_id]

    async def broadcast_to_org_agents(self, organization_id: uuid.UUID, payload: dict) -> None:
        for websocket in list(self._agent_sockets.get(organization_id, ())):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.leave_org_agents(organization_id, websocket)


# Process-wide singleton — every router/service imports this same instance.
connection_manager = ConnectionManager()
