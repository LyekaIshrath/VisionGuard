from typing import Optional
from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    """Authenticated user context derived from cryptographically verified token."""
    id: str
    email: Optional[str] = None
    role: Optional[str] = "authenticated"
    raw_token: Optional[str] = None

    @property
    def token(self) -> str:
        return self.raw_token or ""
