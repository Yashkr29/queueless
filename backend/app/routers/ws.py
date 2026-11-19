import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..db import SessionLocal
from ..models import Role
from ..realtime import hub
from ..security import user_from_token

router = APIRouter()
log = logging.getLogger("queueless.ws")


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """First-message auth: the client must send {"type":"auth","token":"<JWT>"} within 5 s.
    (Query-string tokens would end up in proxy/access logs, so we do not accept them.)"""
    await ws.accept()
    try:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=5)
        if msg.get("type") != "auth":
            raise ValueError("auth required")
        with SessionLocal() as db:
            user = user_from_token(db, str(msg.get("token", "")))
            if not user:
                raise ValueError("bad token")
            uid, staff = user.user_id, user.role in (Role.staff, Role.admin)
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect, RuntimeError):
        await ws.close(code=4401)
        return
    hub.register(ws, uid, staff)
    await ws.send_json({"type": "ready", "staff": staff})
    try:
        while True:
            text = await ws.receive_text()
            if text == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("websocket error")
    finally:
        hub.disconnect(ws, uid)
