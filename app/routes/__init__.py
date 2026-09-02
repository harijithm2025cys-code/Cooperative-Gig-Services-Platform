from app.routes.auth import router as auth_router
from app.routes.workers import router as workers_router
from app.routes.bookings import router as bookings_router
from app.routes.matching import router as matching_router
from app.routes.ratings import router as ratings_router
from app.routes.admin import router as admin_router
from app.routes.health import router as health_router

__all__ = [
    "auth_router",
    "workers_router",
    "bookings_router",
    "matching_router",
    "ratings_router",
    "admin_router",
    "health_router",
]
