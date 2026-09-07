import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.routes import (
    health_router,
    auth_router,
    workers_router,
    bookings_router,
    matching_router,
    ratings_router,
    admin_router,
    verification_router,
    tariffs_router,
    bulk_bookings_router,
    notifications_router,
    payments_router,
    invoices_router,
    complaints_router,
    association_router,
    analytics_router,
    ml_router,
)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cooperative_gig_platform")

import time
import uuid

def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ----------------------------------------------------------------------
    # CORS Configuration
    # ----------------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ----------------------------------------------------------------------
    # Request ID & Performance Timing Middleware
    # ----------------------------------------------------------------------
    @application.middleware("http")
    async def request_id_and_timing_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time-Ms"] = str(process_time_ms)
        return response

    # ----------------------------------------------------------------------
    # Exception Handlers
    # ----------------------------------------------------------------------
    @application.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "status_code": exc.status_code,
                "error": exc.detail,
                "path": str(request.url.path)
            }
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "status_code": 422,
                "error": "Validation Error",
                "details": exc.errors(),
                "path": str(request.url.path)
            }
        )

    @application.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception on {request.url.path}: {str(exc)}", exc_info=True)
        # Sanitized response: avoid leaking database schemas, connection strings or traces
        is_dev = settings.ENVIRONMENT == "development"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "status_code": 500,
                "error": "Internal Server Error",
                "detail": str(exc) if is_dev else "An unexpected error occurred. Please contact support.",
                "path": str(request.url.path)
            }
        )

    # ----------------------------------------------------------------------
    # Routers Registration
    # ----------------------------------------------------------------------
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(workers_router)
    application.include_router(bookings_router)
    application.include_router(matching_router)
    application.include_router(ratings_router)
    application.include_router(admin_router)
    application.include_router(verification_router)
    application.include_router(tariffs_router)
    application.include_router(bulk_bookings_router)
    application.include_router(notifications_router)
    application.include_router(payments_router)
    application.include_router(invoices_router)
    application.include_router(complaints_router)
    application.include_router(association_router)
    application.include_router(analytics_router)
    application.include_router(ml_router)

    return application

app = create_application()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
