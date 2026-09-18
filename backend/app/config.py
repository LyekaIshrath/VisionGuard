import os
from typing import Optional, Dict, Any

app_name = "VisionGuard API"
app_version = "0.1.0"
debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# Supabase SaaS Configuration
SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY: Optional[str] = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_JWT_SECRET: Optional[str] = os.getenv("SUPABASE_JWT_SECRET")


def is_cloud_configured() -> bool:
    """Return True if basic Supabase credentials are configured."""
    return bool(SUPABASE_URL and (SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY))


def get_settings() -> Dict[str, Any]:
    return {
        "app_name": app_name,
        "app_version": app_version,
        "debug": debug,
        "cloud_configured": is_cloud_configured(),
        "supabase_url": SUPABASE_URL,
    }


class Settings:
    @property
    def SUPABASE_URL(self) -> Optional[str]:
        return SUPABASE_URL

    @property
    def SUPABASE_ANON_KEY(self) -> Optional[str]:
        return SUPABASE_ANON_KEY

    @property
    def SUPABASE_SERVICE_ROLE_KEY(self) -> Optional[str]:
        return SUPABASE_SERVICE_ROLE_KEY

    @property
    def SUPABASE_JWT_SECRET(self) -> Optional[str]:
        return SUPABASE_JWT_SECRET

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
