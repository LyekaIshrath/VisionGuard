from __future__ import annotations

from typing import Protocol, Optional

from ..human_state.models import HumanState


class HumanAnalyzer(Protocol):
    def analyze(self, frame: bytes) -> HumanState:
        """Analyze a camera frame and return human state.

        Returns a HumanState with only fields that have been calculated.
        Uncalculated fields must be None/optional.
        """
        ...


class PostureAnalyzer(Protocol):
    def analyze_posture(self, state: HumanState) -> HumanState:
        """Analyze posture and update human state.

        Returns updated HumanState with posture fields populated if available.
        """

    @property
    def requires_pose(self) -> bool:
        """Whether this analyzer requires pose detection."""


class DrowsinessAnalyzer(Protocol):
    def analyze_drowsiness(self, state: HumanState) -> HumanState:
        """Analyze drowsiness and update human state.

        Returns updated HumanState with alertness/eye fields populated if available.
        """

    @property
    def requires_eye_state(self) -> bool:
        """Whether this analyzer requires eye state detection."""


class MovementAnalyzer(Protocol):
    def analyze_movement(self, state: HumanState) -> HumanState:
        """Analyze movement and update human state.

        Returns updated HumanState with movement/risk fields populated if available.
        """
        ...


class RiskAnalyzer(Protocol):
    def analyze_risk(self, state: HumanState) -> HumanState:
        """Analyze risk and update human state.

        Returns updated HumanState with risk_level and risk_score populated if available.
        """
        ...