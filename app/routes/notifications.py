from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user
from app.models.notification import (
    NotificationResponse,
    NotificationListResponse,
    NotificationMarkReadRequest
)
from app.services.event_service import event_service

router = APIRouter(prefix="/notifications", tags=["In-App Notifications"])

@router.get("/", response_model=NotificationListResponse)
def get_my_notifications(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieve notification feed for current authenticated user.
    """
    user_id = str(current_user.get("id"))
    notifs = event_service.get_user_notifications(user_id=user_id, db=db)
    unread = sum(1 for n in notifs if not n.get("read", False))

    formatted = [
        NotificationResponse(
            id=str(n["id"]),
            user_id=str(n["user_id"]),
            type=n.get("type", "system"),
            title=n.get("title", "Update"),
            message=n.get("message", ""),
            booking_id=str(n["booking_id"]) if n.get("booking_id") else None,
            assignment_id=str(n["assignment_id"]) if n.get("assignment_id") else None,
            read=bool(n.get("read", False)),
            created_at=n.get("created_at"),
            data=n.get("data")
        )
        for n in notifs
    ]

    return NotificationListResponse(
        total=len(formatted),
        unread_count=unread,
        notifications=formatted
    )

@router.get("/unread-count")
def get_unread_notification_count(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Fast query for unread badge count.
    """
    user_id = str(current_user.get("id"))
    unread = event_service.get_unread_count(user_id=user_id, db=db)
    return {"unread_count": unread}

@router.patch("/{notification_id}/read")
def mark_notification_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Mark a specific notification as read.
    """
    user_id = str(current_user.get("id"))
    success = event_service.mark_as_read(user_id=user_id, notification_id=notification_id, db=db)
    return {"success": success, "notification_id": notification_id, "read": True}

@router.post("/mark-all-read")
def mark_all_notifications_as_read(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Mark all unread notifications as read.
    """
    user_id = str(current_user.get("id"))
    count = event_service.mark_all_as_read(user_id=user_id, db=db)
    return {"success": True, "marked_count": count}
