import os
import json
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Automatically load environment variables from .env files
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

app_name = "VisionGuard API"
app_version = "1.0.0"
debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# Supabase SaaS Configuration
SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY: Optional[str] = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_JWT_SECRET: Optional[str] = os.getenv("SUPABASE_JWT_SECRET")


# CORS - Mission 09: explicit allowlist; never wildcard in production
_CORS_ENV = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _CORS_ENV:
    try:
        CORS_ALLOWED_ORIGINS: List[str] = json.loads(_CORS_ENV)
    except Exception:
        CORS_ALLOWED_ORIGINS = [o.strip() for o in _CORS_ENV.split(",") if o.strip()]
else:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

def is_cloud_configured() -> bool:
    """Return True if basic Supabase credentials are configured."""
    url = os.getenv("SUPABASE_URL") or SUPABASE_URL
    key = os.getenv("SUPABASE_ANON_KEY") or SUPABASE_ANON_KEY or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or SUPABASE_SERVICE_ROLE_KEY
    return bool(url and key)


def get_settings() -> Dict[str, Any]:
    return {
        "app_name": app_name,
        "app_version": app_version,
        "debug": debug,
        "cloud_configured": is_cloud_configured(),
        "supabase_url": os.getenv("SUPABASE_URL") or SUPABASE_URL,
    }


class Settings:
    @property
    def SUPABASE_URL(self) -> Optional[str]:
        return os.getenv("SUPABASE_URL") or SUPABASE_URL

    @property
    def SUPABASE_ANON_KEY(self) -> Optional[str]:
        return os.getenv("SUPABASE_ANON_KEY") or SUPABASE_ANON_KEY

    @property
    def SUPABASE_SERVICE_ROLE_KEY(self) -> Optional[str]:
        return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or SUPABASE_SERVICE_ROLE_KEY

    @property
    def SUPABASE_JWT_SECRET(self) -> Optional[str]:
        return os.getenv("SUPABASE_JWT_SECRET") or SUPABASE_JWT_SECRET

    @property
    def CORS_ALLOWED_ORIGINS(self):
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

config = Settings()
