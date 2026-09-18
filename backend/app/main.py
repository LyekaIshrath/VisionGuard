from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import app_name, app_version
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

app = FastAPI(
    title=app_name,
    version=app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/health")
async def health_check():
    return {
        "status": "READY",
        "app_name": app_name,
        "version": app_version,
    }

