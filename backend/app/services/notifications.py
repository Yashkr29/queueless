"""Notification service. The DB row + WebSocket message is the system of record; FCM push is a best-effort
extra channel that only activates when FCM_CREDENTIALS_FILE is configured and the user registered a device."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DeliveryStatus, Notification, PushDevice
from ..realtime import Outbox

log = logging.getLogger("queueless.notify")
_fcm_ready: bool | None = None


def _init_fcm() -> bool:
    global _fcm_ready
    if _fcm_ready is None:
        path = get_settings().fcm_credentials_file
        if not path:
            _fcm_ready = False
        else:
            try:
                import firebase_admin
                from firebase_admin import credentials
                firebase_admin.initialize_app(credentials.Certificate(path))
                _fcm_ready = True
            except Exception:
                log.exception("FCM initialisation failed; push disabled")
                _fcm_ready = False
    return _fcm_ready


def _push(db: Session, user_id: int, title: str, body: str) -> bool:
    if not _init_fcm():
        return False
    tokens = db.scalars(select(PushDevice.fcm_token).where(PushDevice.user_id == user_id)).all()
    if not tokens:
        return False
    try:
        from firebase_admin import messaging
        for t in tokens:
            messaging.send(messaging.Message(notification=messaging.Notification(title=title, body=body), token=t))
        return True
    except Exception:
        log.exception("FCM send failed")
        return False


def notify(db: Session, outbox: Outbox, user_id: int, ntype: str, title: str, message: str, token_id: int | None = None) -> Notification:
    n = Notification(user_id=user_id, token_id=token_id, notification_type=ntype, title=title, message=message,
                     delivery_status=DeliveryStatus.pending)
    db.add(n)
    db.flush()
    n.delivery_status = DeliveryStatus.sent if _push(db, user_id, title, message) else DeliveryStatus.pending
    outbox.to_user(user_id, {"type": "notification", "notification": {
        "notification_id": n.notification_id, "notification_type": ntype, "title": title, "message": message,
        "token_id": token_id, "created_at": n.created_at}})
    return n
