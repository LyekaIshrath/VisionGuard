from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/system/status", summary="Return the state of required application services")
async def system_status():
    return {
        "camera": "NOT_CONFIGURED",
        "ai_services": "NOT_CONFIGURED",
        "state": "STOPPED",
        "app_name": "VisionGuard API",
        "version": "0.1.0",
    }