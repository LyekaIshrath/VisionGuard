"""VisionGuard Application Configuration.

Centralized configuration for VisionGuard API, MongoDB persistence,
and server-side authentication.
"""

import os
import json
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

app_name = "VisionGuard API"
app_version = "1.0.0"
debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# Database & Authentication Configuration (MongoDB)
MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "visionguard")
JWT_SECRET: str = os.getenv("JWT_SECRET", "visionguard-secret-key-development-minimum-32-chars-long")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# CORS - Development localhost ports safely supported without wildcard
DEV_VITE_PORTS = [5173, 5174, 5175, 5176, 5177, 5178, 5179, 4173, 4174, 4175, 8000, 3000]

_CORS_ENV = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _CORS_ENV:
    try:
        CORS_ALLOWED_ORIGINS: List[str] = json.loads(_CORS_ENV)
    except Exception:
        CORS_ALLOWED_ORIGINS = [o.strip() for o in _CORS_ENV.split(",") if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = []
    for port in DEV_VITE_PORTS:
        CORS_ALLOWED_ORIGINS.append(f"http://localhost:{port}")
        CORS_ALLOWED_ORIGINS.append(f"http://127.0.0.1:{port}")


def is_database_configured() -> bool:
    """Return True since MongoDB is configured as authoritative persistence."""
    return bool(MONGODB_URI and MONGODB_DATABASE)


def is_cloud_configured() -> bool:
    return is_database_configured()


def get_settings() -> Dict[str, Any]:
    return {
        "app_name": app_name,
        "app_version": app_version,
        "debug": debug,
        "database_configured": is_database_configured(),
        "mongodb_uri": MONGODB_URI,
        "mongodb_database": MONGODB_DATABASE,
    }


class Settings:
    @property
    def MONGODB_URI(self) -> str:
        return MONGODB_URI

    @property
    def MONGODB_DATABASE(self) -> str:
        return MONGODB_DATABASE

    @property
    def JWT_SECRET(self) -> str:
        return JWT_SECRET

    @property
    def JWT_ALGORITHM(self) -> str:
        return JWT_ALGORITHM

    @property
    def CORS_ALLOWED_ORIGINS(self) -> List[str]:
        return CORS_ALLOWED_ORIGINS

    @property
    def app_name(self) -> str:
        return app_name

    @property
    def app_version(self) -> str:
        return app_version

    @property
    def debug(self) -> bool:
        return debug

    def is_cloud_configured(self) -> bool:
        return is_cloud_configured()

    def is_database_configured(self) -> bool:
        return is_database_configured()


config = Settings()
