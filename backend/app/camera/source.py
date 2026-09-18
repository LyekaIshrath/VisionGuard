from __future__ import annotations

from typing import Protocol, Optional

from ..human_state.models import HumanState


class CameraSource(Protocol):
    def start(self) -> None:
        """Start the camera source."""

    def read(self) -> Optional[bytes]:
        """Read a frame from the camera source.

        Returns raw frame bytes or None if no frame available.
        """

    def stop(self) -> None:
        """Stop the camera source."""

    def health(self) -> str:
        """Return health status: READY, NOT_CONFIGURED, or UNAVAILABLE."""
        ...