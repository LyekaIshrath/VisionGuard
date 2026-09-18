import uuid
from typing import List, Dict, Any, Optional
from app.intelligence.models import (
    Insight, InsightType, AnalyticsOverview, DailyTrendItem, TimeOfDayBucket, CoverageLevel
)

class DeterministicInsightEngine:
    """
    Generates deterministic, rule-based wellness insights.
    Zero LLM dependencies. Grounds every claim in verified metrics.
    Requires minimum threshold of data before claiming statistical patterns.
    """
    @staticmethod
    def generate_insights(
        overview: AnalyticsOverview,
        trends: List[DailyTrendItem],
        time_of_day: List[TimeOfDayBucket]
    ) -> List[Insight]:
        insights: List[Insight] = []

        # Threshold 1: Insufficient total monitoring (< 3600 seconds / 1 hour)
        if overview.total_monitored_seconds < 3600.0:
            insights.append(Insight(
                id="insufficient-data",
                type=InsightType.INSUFFICIENT_DATA,
                title="More Observation Time Needed",
                description="VisionGuard requires at least 1 hour of active monitoring across multiple sessions to detect meaningful patterns.",
                metric_reference="total_monitored_seconds",
                recommended_action="Keep VisionGuard active during your normal desk work to build your baseline."
            ))
            return insights

        # Coverage Notice
        if (overview.coverage.posture.data_quality == CoverageLevel.PARTIAL or
            overview.coverage.alertness.data_quality == CoverageLevel.PARTIAL):
            insights.append(Insight(
                id="partial-coverage-notice",
                type=InsightType.INFORMATIONAL,
                title="Historical Coverage Notice",
                description="Some earlier sessions lack explicit valid observation exposure. Rate metrics strictly reflect sessions with complete exposure telemetry.",
                metric_reference="coverage.posture.data_quality",
                recommended_action=None
            ))

        # Rule 1: Time of day - Afternoon Dip
        tod_map = {b.bucket: b for b in time_of_day}
        morning = tod_map.get("MORNING")
        afternoon = tod_map.get("AFTERNOON")
        if (morning and afternoon and
            morning.monitored_exposure_seconds >= 1800.0 and
            afternoon.monitored_exposure_seconds >= 1800.0 and
            morning.events_per_monitored_hour is not None and
            afternoon.events_per_monitored_hour is not None):
            
            if afternoon.events_per_monitored_hour >= 1.5 * max(morning.events_per_monitored_hour, 0.5) and afternoon.risk_event_count >= 3:
                pct_diff = round((afternoon.events_per_monitored_hour - morning.events_per_monitored_hour) / max(morning.events_per_monitored_hour, 0.5) * 100)
                insights.append(Insight(
                    id="afternoon-risk-dip",
                    type=InsightType.ATTENTION_PATTERN,
                    title="Afternoon Ergonomic Dip",
                    description=f"Your risk event rate is {pct_diff}% higher in the afternoon ({afternoon.events_per_monitored_hour}/hr) than the morning ({morning.events_per_monitored_hour}/hr).",
                    metric_reference="time_of_day.afternoon",
                    recommended_action="Schedule a brief standing break or posture reset around 14:00."
                ))
            elif morning.events_per_monitored_hour <= 0.5 and morning.monitored_exposure_seconds >= 3600.0:
                insights.append(Insight(
                    id="strong-morning-ergonomics",
                    type=InsightType.POSITIVE_PATTERN,
                    title="Strong Morning Posture Stability",
                    description=f"You maintain excellent ergonomic alignment during morning hours with only {morning.events_per_monitored_hour} events/hr.",
                    metric_reference="time_of_day.morning",
                    recommended_action="Notice your physical desk setup in the morning and try to preserve that posture all day."
                ))

        # Rule 2: Posture Quality Achievement
        if overview.good_posture_percentage is not None:
            if overview.good_posture_percentage >= 80.0:
                insights.append(Insight(
                    id="posture-high-quality",
                    type=InsightType.POSITIVE_PATTERN,
                    title="Outstanding Posture Alignment",
                    description=f"You spent {overview.good_posture_percentage}% of your valid observation time in good ergonomic posture.",
                    metric_reference="good_posture_percentage",
                    recommended_action="Great job! Continue keeping your monitor at eye level and shoulders relaxed."
                ))
            elif overview.good_posture_percentage < 50.0:
                insights.append(Insight(
                    id="posture-needs-focus",
                    type=InsightType.ATTENTION_PATTERN,
                    title="Frequent Slouching Detected",
                    description=f"Good posture accounted for only {overview.good_posture_percentage}% of valid observation time.",
                    metric_reference="good_posture_percentage",
                    recommended_action="Check your chair height and lumbar support. Ensure feet are flat on the floor."
                ))

        # Rule 3: Trend Trajectory (comparing first half of days vs second half of days)
        active_days = [t for t in trends if t.total_monitored_seconds >= 600.0 and t.good_posture_percentage is not None]
        if len(active_days) >= 4:
            mid = len(active_days) // 2
            first_half_avg = sum(d.good_posture_percentage for d in active_days[:mid]) / mid
            second_half_avg = sum(d.good_posture_percentage for d in active_days[mid:]) / (len(active_days) - mid)
            delta = second_half_avg - first_half_avg
            if delta >= 10.0:
                insights.append(Insight(
                    id="trend-improving",
                    type=InsightType.POSITIVE_PATTERN,
                    title="Ergonomic Habit Improving",
                    description=f"Your average good posture percentage improved by {round(delta, 1)}% across recent active monitoring days.",
                    metric_reference="daily_trends.good_posture_percentage",
                    recommended_action="Your conscious adjustments are paying off. Keep up the consistent awareness."
                ))
            elif delta <= -10.0:
                insights.append(Insight(
                    id="trend-declining",
                    type=InsightType.ATTENTION_PATTERN,
                    title="Posture Fatigue Accumulation",
                    description=f"Good posture percentage declined by {round(abs(delta), 1)}% across recent sessions.",
                    metric_reference="daily_trends.good_posture_percentage",
                    recommended_action="Cumulative fatigue may be settling in. Prioritize micro-breaks every 30 minutes."
                ))

        # Rule 4: Night-time Alertness Strain
        night = tod_map.get("NIGHT")
        if night and night.monitored_exposure_seconds >= 1800.0 and night.events_per_monitored_hour is not None:
            if night.events_per_monitored_hour >= 3.0:
                insights.append(Insight(
                    id="night-strain",
                    type=InsightType.ATTENTION_PATTERN,
                    title="Late-Night Visual Fatigue",
                    description=f"You experience {night.events_per_monitored_hour} risk events/hr during late-night sessions (22:00 - 06:00).",
                    metric_reference="time_of_day.night",
                    recommended_action="Avoid prolonged late-night screen sessions to protect circadian alignment and eye health."
                ))

        return insights
