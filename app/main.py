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
)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cooperative_gig_platform")

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
        allow_origins=["*"],  # Open for mobile / frontend prototypes
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "status_code": 500,
                "error": "Internal Server Error",
                "detail": str(exc),
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

    return application

app = create_application()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
