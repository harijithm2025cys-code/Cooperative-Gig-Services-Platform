from app.routes.auth import router as auth_router
from app.routes.workers import router as workers_router
from app.routes.bookings import router as bookings_router
from app.routes.matching import router as matching_router
from app.routes.ratings import router as ratings_router
from app.routes.admin import router as admin_router
from app.routes.health import router as health_router
from app.routes.verification import router as verification_router
from app.routes.tariffs import router as tariffs_router
from app.routes.bulk_bookings import router as bulk_bookings_router
from app.routes.notifications import router as notifications_router
from app.routes.payments import router as payments_router
from app.routes.invoices import router as invoices_router
from app.routes.complaints import router as complaints_router
from app.routes.association import router as association_router
from app.routes.analytics import router as analytics_router
from app.routes.ml import router as ml_router
from app.routes.chat import router as chat_router

__all__ = [
    "auth_router",
    "workers_router",
    "bookings_router",
    "matching_router",
    "ratings_router",
    "admin_router",
    "health_router",
    "verification_router",
    "tariffs_router",
    "bulk_bookings_router",
    "notifications_router",
    "payments_router",
    "invoices_router",
    "complaints_router",
    "association_router",
    "analytics_router",
    "ml_router",
    "chat_router",
]


