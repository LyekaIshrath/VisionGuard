from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import app_name, app_version, CORS_ALLOWED_ORIGINS, debug
from app.middleware.security import (
    SecurityHeadersMiddleware,
    CorrelationIdMiddleware,
    configure_structured_logging,
)
from app.api.auth import router as auth_router
from app.api.router import router as api_router
from app.api.monitoring import router as monitoring_router
from app.api.posture import router as posture_router
from app.api.alertness import router as alertness_router
from app.api.risk import router as risk_router
from app.api.sessions import router as sessions_router
from app.api.analytics import router as analytics_router
from app.api.user import router as user_router
from app.api.cloud import router as cloud_router
from app.api.goals import router as goals_router
from app.api.reports import router as reports_router
from app.api.notifications import router as notifications_router
from app.camera.manager import get_camera_manager

configure_structured_logging(debug=debug)

app = FastAPI(
    title=app_name,
    version=app_version,
)

# Middleware stack (outermost wraps all request/response)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Requested-With"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")
app.include_router(monitoring_router, prefix="/api/v1")
app.include_router(posture_router, prefix="/api/v1")
app.include_router(alertness_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(cloud_router, prefix="/api/v1")
app.include_router(goals_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(notifications_router)


@app.get("/health")
async def health_check():
    manager = get_camera_manager()
    cam_status = manager.status()
    return {
        "status": "READY",
        "app_name": app_name,
        "version": app_version,
        "camera_state": cam_status.get("state", "STOPPED"),
        "camera_index": cam_status.get("camera_index", 0),
    }

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
import logging

app_logger = logging.getLogger("visionguard.app")

@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception):
    """Secure top-level exception handler.
    Returns structured JSON with generic message. Never leaks tracebacks,
    filesystem paths, exception internals, credentials, or DB specifics.
    Full traceback logged securely on server-side only.
    """
    if isinstance(exc, (StarletteHTTPException, RequestValidationError)):
        # Let Starlette / FastAPI standard handlers handle HTTP status codes and validation errors
        raise exc
    app_logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

