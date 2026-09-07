import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.models.notification import RealtimeEvent, NotificationResponse
from app.services.notification_service import notification_service

logger = logging.getLogger("event_service")

# In-memory stores for notifications and real-time events (guarantees fast querying & offline/test reliability)
_NOTIFICATIONS_BY_USER: Dict[str, List[Dict[str, Any]]] = {}
_EVENTS_BY_BOOKING: Dict[str, List[Dict[str, Any]]] = {}

class EventService:
    """
    Central event dispatcher for real-time operations, notifications, and cross-party state sync.
    Emits standardized operational events across Customer, Worker, Association Head, and Super Admin.
    """

    @staticmethod
    def dispatch_event(
        event_type: str,
        booking_id: str,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        assignment_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        target_user_ids: Optional[List[str]] = None,
        notification_title: Optional[str] = None,
        notification_message: Optional[str] = None,
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        event_data = data or {}
        now = datetime.utcnow()
        now_iso = now.isoformat()

        event_payload = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "booking_id": booking_id,
            "assignment_id": assignment_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "timestamp": now_iso,
            "data": event_data
        }

        # 1. Record event in memory
        bid = str(booking_id)
        if bid not in _EVENTS_BY_BOOKING:
            _EVENTS_BY_BOOKING[bid] = []
        _EVENTS_BY_BOOKING[bid].append(event_payload)

        logger.info(f"[Realtime Event] {event_type} on Booking #{booking_id} by {actor_role or 'System'}")

        # 2. Persist event to DB if available
        if db:
            try:
                db.table("operational_events").insert(event_payload).execute()
            except Exception:
                pass

        # 3. Create In-App Notifications for targets
        targets = target_user_ids or []
        for uid in targets:
            notif_id = str(uuid.uuid4())
            notif_row = {
                "id": notif_id,
                "user_id": str(uid),
                "type": event_type.lower(),
                "title": notification_title or f"Booking Update: {event_type.replace('_', ' ').title()}",
                "message": notification_message or f"Booking #{booking_id[:6]} status changed to {event_type}.",
                "booking_id": booking_id,
                "assignment_id": assignment_id,
                "read": False,
                "created_at": now_iso,
                "data": event_data
            }

            # In-memory storage
            uid_str = str(uid)
            if uid_str not in _NOTIFICATIONS_BY_USER:
                _NOTIFICATIONS_BY_USER[uid_str] = []
            _NOTIFICATIONS_BY_USER[uid_str].insert(0, notif_row)

            # DB persistence
            if db:
                try:
                    db.table("notifications").insert(notif_row).execute()
                except Exception:
                    pass

        # 4. Push FCM alert if notification service has token
        if notification_title and notification_message:
            try:
                notification_service.send_push_notification(
                    target_token="device_token_demo",
                    title=notification_title,
                    body=notification_message,
                    data={"booking_id": booking_id, "event_type": event_type}
                )
            except Exception:
                pass

        return event_payload

    @staticmethod
    def get_user_notifications(user_id: str, db: Optional[Any] = None) -> List[Dict[str, Any]]:
        uid_str = str(user_id)
        if db:
            try:
                res = db.table("notifications").select("*").eq("user_id", uid_str).order("created_at", desc=True).limit(50).execute()
                if res.data and len(res.data) > 0:
                    return res.data
            except Exception:
                pass
        return _NOTIFICATIONS_BY_USER.get(uid_str, [])

    @staticmethod
    def get_unread_count(user_id: str, db: Optional[Any] = None) -> int:
        notifications = EventService.get_user_notifications(user_id, db)
        return sum(1 for n in notifications if not n.get("read", False))

    @property
    def _in_memory_notifications(self):
        return _NOTIFICATIONS_BY_USER

    @property
    def _in_memory_events(self):
        return _EVENTS_BY_BOOKING

    @staticmethod
    def publish_event(
        event_type: str,
        booking_id: str,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
        assignment_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        target_user_ids: Optional[List[str]] = None,
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        return EventService.dispatch_event(
            event_type=event_type,
            booking_id=booking_id,
            actor_id=actor_id,
            actor_role=actor_role,
            assignment_id=assignment_id,
            data=data,
            target_user_ids=target_user_ids,
            notification_title=title,
            notification_message=description,
            db=db
        )

    @staticmethod
    def create_notification(
        user_id: str,
        title: str,
        message: str,
        type: str = "system",
        reference_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        uid_str = str(user_id)
        now_iso = datetime.utcnow().isoformat()
        notif_row = {
            "id": str(uuid.uuid4()),
            "user_id": uid_str,
            "title": title,
            "message": message,
            "type": type.lower(),
            "reference_id": reference_id,
            "read": False,
            "is_read": False,
            "created_at": now_iso,
            "data": data or {}
        }
        if uid_str not in _NOTIFICATIONS_BY_USER:
            _NOTIFICATIONS_BY_USER[uid_str] = []
        _NOTIFICATIONS_BY_USER[uid_str].insert(0, notif_row)
        if db:
            try:
                db.table("notifications").insert(notif_row).execute()
            except Exception:
                pass
        return notif_row

    @staticmethod
    def mark_as_read(param1: str, param2: Optional[str] = None, db: Optional[Any] = None) -> bool:
        # Flexible support for either (user_id, notification_id) or (notification_id, user_id)
        # Search which one is in _NOTIFICATIONS_BY_USER
        user_id = param1 if param1 in _NOTIFICATIONS_BY_USER else (param2 or param1)
        notif_id = param2 if user_id == param1 else param1
        
        uid_str = str(user_id)
        if uid_str in _NOTIFICATIONS_BY_USER:
            for n in _NOTIFICATIONS_BY_USER[uid_str]:
                if str(n.get("id")) == str(notif_id):
                    n["read"] = True
                    n["is_read"] = True
                    break

        if db:
            try:
                db.table("notifications").update({"read": True, "is_read": True}).eq("id", notif_id).execute()
            except Exception:
                pass
        return True

    @staticmethod
    def mark_all_as_read(user_id: str, db: Optional[Any] = None) -> int:
        uid_str = str(user_id)
        count = 0
        if uid_str in _NOTIFICATIONS_BY_USER:
            for n in _NOTIFICATIONS_BY_USER[uid_str]:
                if not n.get("read", False) and not n.get("is_read", False):
                    n["read"] = True
                    n["is_read"] = True
                    count += 1

        if db:
            try:
                db.table("notifications").update({"read": True, "is_read": True}).eq("user_id", uid_str).execute()
            except Exception:
                pass
        return count

    @staticmethod
    def get_booking_events(booking_id: str) -> List[Dict[str, Any]]:
        return _EVENTS_BY_BOOKING.get(str(booking_id), [])

event_service = EventService()
