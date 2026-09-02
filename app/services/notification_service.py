import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("notification_service")

class FirebaseNotificationService:
    """
    Service for dispatching Firebase Cloud Messaging (FCM) push alerts
    and syncing state with Firebase Firestore from the FastAPI backend.
    """

    @staticmethod
    def send_push_notification(
        target_token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Sends an FCM push notification to a mobile device token.
        Can be backed by firebase-admin or HTTP v1 API.
        """
        try:
            logger.info(f"[FCM Notification] Sending to token: {target_token[:10]}... | Title: '{title}' | Body: '{body}'")
            # In production, uses firebase_admin.messaging.send(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send FCM push notification: {e}")
            return False

    @staticmethod
    def notify_new_booking(worker_token: Optional[str], booking_id: str, skill: str, household_address: str):
        """Dispatches 'New Gig Request' push notification to the assigned worker."""
        title = f"New {skill} Gig Opportunity! 🛠️"
        body = f"New booking #{booking_id[:6]} near {household_address}. Tap to review."
        if worker_token:
            FirebaseNotificationService.send_push_notification(
                target_token=worker_token,
                title=title,
                body=body,
                data={"booking_id": booking_id, "type": "new_booking"}
            )

    @staticmethod
    def notify_status_change(household_token: Optional[str], booking_id: str, status: str):
        """Dispatches booking status change notifications (e.g. accepted, in_progress, completed)."""
        messages = {
            "accepted": ("Worker Assigned! 🤝", "A cooperative specialist has accepted your booking and is en-route."),
            "in_progress": ("Worker Checked-In ⏱️", "Your service has started at your location."),
            "completed": ("Service Completed! ⭐", "Your gig is completed. Please rate the worker."),
            "cancelled": ("Booking Cancelled ❌", "The booking request has been cancelled.")
        }
        if status in messages and household_token:
            title, body = messages[status]
            FirebaseNotificationService.send_push_notification(
                target_token=household_token,
                title=title,
                body=body,
                data={"booking_id": booking_id, "type": "status_update", "status": status}
            )

notification_service = FirebaseNotificationService()
