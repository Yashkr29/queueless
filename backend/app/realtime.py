"""In-process WebSocket hub + outbox.

DB code never awaits: it appends messages to an `Outbox`, and the endpoint flushes it as a BackgroundTask
AFTER the transaction committed, so clients never see state that was rolled back.
Single-process only. Horizontal scaling needs pub/sub (Supabase Realtime / Redis) behind `Hub.publish`.
"""
import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import WebSocket

log = logging.getLogger("queueless.ws")


@dataclass
class Outbox:
    messages: list[tuple[str, int | None, dict]] = field(default_factory=list)   # (audience, user_id, payload)

    def to_user(self, user_id: int, payload: dict) -> None:
        self.messages.append(("user", user_id, payload))

    def to_staff(self, payload: dict) -> None:
        self.messages.append(("staff", None, payload))


class Hub:
    def __init__(self) -> None:
        self.users: dict[int, set[WebSocket]] = defaultdict(set)
        self.staff: set[WebSocket] = set()

    def register(self, ws: WebSocket, user_id: int, is_staff: bool) -> None:
        """Called after the socket was accepted AND authenticated (first-message JWT auth, see routers/ws.py)."""
        self.users[user_id].add(ws)
        if is_staff:
            self.staff.add(ws)

    def disconnect(self, ws: WebSocket, user_id: int) -> None:
        self.users[user_id].discard(ws)
        self.staff.discard(ws)
        if not self.users[user_id]:
            self.users.pop(user_id, None)

    async def _send(self, ws: WebSocket, text: str) -> None:
        try:
            await asyncio.wait_for(ws.send_text(text), timeout=3)
        except Exception:
            self.staff.discard(ws)
            for conns in self.users.values():
                conns.discard(ws)

    async def flush(self, outbox: Outbox) -> None:
        for audience, user_id, payload in outbox.messages:
            text = json.dumps(payload, default=str)
            targets = list(self.staff) if audience == "staff" else list(self.users.get(user_id, ()))
            await asyncio.gather(*(self._send(w, text) for w in targets))


hub = Hub()


async def flush_outbox(outbox: Outbox) -> None:
    try:
        await hub.flush(outbox)
    except Exception:
        log.exception("websocket flush failed")
