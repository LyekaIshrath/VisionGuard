import React, { useState, useMemo } from "react";
import { formatSafeTime, formatSafeDate } from "./ReportFormatters";
import { TimelineEvent } from "./reportTypes";

interface SessionTimelineProps {
  timeline?: TimelineEvent[];
  startedAt?: string;
  endedAt?: string;
}

type TimelineFilter = "ALL" | "ACTIVITY" | "PRESENCE" | "RISK";

export const SessionTimeline: React.FC<SessionTimelineProps> = ({
  timeline = [],
}) => {
  const [activeFilter, setActiveFilter] = useState<TimelineFilter>("ALL");

  // Normalize event category & friendly display name
  const categorizedEvents = useMemo(() => {
    return timeline.map((ev, index) => {
      const rawType = (ev.type || ev.event_type || "").toUpperCase();
      const rawCat = (ev.category || "").toUpperCase();

      let category: "ACTIVITY" | "PRESENCE" | "RISK" | "SYSTEM" = "SYSTEM";
      let displayName = rawType.replace(/_/g, " ");
      let badgeClass = "timeline-badge-system";

      if (
        rawType.startsWith("STATE_") ||
        rawType.includes("ENGAGED") ||
        rawType.includes("OBSERVING") ||
        rawType.includes("ATTENTION")
      ) {
        category = "ACTIVITY";
        badgeClass = "timeline-badge-activity";
        if (rawType === "STATE_ENGAGED") displayName = "Engaged";
        else if (rawType === "STATE_OBSERVING") displayName = "Observing";
        else if (rawType === "STATE_ATTENTION_AWAY") displayName = "Attention Away";
        else if (rawType === "STATE_AWAY") displayName = "Away";
      } else if (
        rawType.includes("PERSON_") ||
        rawType.includes("PRESENCE") ||
        rawType === "STATE_AWAY"
      ) {
        category = "PRESENCE";
        badgeClass = "timeline-badge-presence";
        if (rawType === "PERSON_DETECTED") displayName = "Person Detected";
        else if (rawType === "PERSON_LEFT") displayName = "Person Away";
        else if (rawType === "PERSON_RETURNED") displayName = "Person Returned";
      } else if (
        rawType.includes("RISK") ||
        rawType.includes("POSTURE_") ||
        rawType.includes("DROWSINESS") ||
        rawCat === "POSTURE" ||
        rawCat === "ALERTNESS"
      ) {
        category = "RISK";
        badgeClass = "timeline-badge-risk";
        if (rawType === "POSTURE_RISK_START") displayName = "Posture Risk Started";
        else if (rawType === "POSTURE_RISK_RESOLVED") displayName = "Posture Risk Resolved";
      } else if (rawType === "SESSION_START" || rawType === "SESSION_STOP") {
        category = "SYSTEM";
        badgeClass = "timeline-badge-system";
        if (rawType === "SESSION_START") displayName = "Session Started";
        else if (rawType === "SESSION_STOP") displayName = "Session Ended";
      }

      // Extract details or reasons if available
      const reasons: string[] =
        ev.metadata?.reasons ||
        ev.data?.reasons ||
        (ev.reason ? [ev.reason] : []) ||
        [];

      return {
        id: ev.event_id || `ev-${index}`,
        timestamp: ev.timestamp,
        rawType,
        category,
        displayName,
        badgeClass,
        reasons,
      };
    });
  }, [timeline]);

  const filteredEvents = useMemo(() => {
    if (activeFilter === "ALL") return categorizedEvents;
    return categorizedEvents.filter((ev) => ev.category === activeFilter);
  }, [categorizedEvents, activeFilter]);

  return (
    <section className="report-section-root">
      <div className="report-section-header flex-between">
        <div className="report-section-title-group">
          <h2 className="report-section-title">Session Timeline</h2>
          <span className="report-section-subtitle">
            Chronological log of persisted state transitions and events ({categorizedEvents.length} events recorded)
          </span>
        </div>

        {/* Filter Buttons */}
        <div className="timeline-filter-group" role="tablist" aria-label="Timeline Filters">
          {(["ALL", "ACTIVITY", "PRESENCE", "RISK"] as TimelineFilter[]).map((f) => (
            <button
              key={f}
              type="button"
              className={`timeline-filter-btn ${activeFilter === f ? "active" : ""}`}
              onClick={() => setActiveFilter(f)}
            >
              {f === "ALL" ? "All Events" : f.charAt(0) + f.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="report-card">
        {filteredEvents.length === 0 ? (
          <div className="report-empty-state">
            {timeline.length === 0
              ? "No timeline events were recorded for this session."
              : `No ${activeFilter.toLowerCase()} events recorded for this session.`}
          </div>
        ) : (
          <div className="timeline-chronological-list">
            {filteredEvents.map((ev, idx) => (
              <div key={ev.id} className="timeline-event-row">
                <div className="timeline-time-col">
                  <span className="timeline-timestamp">{formatSafeTime(ev.timestamp, true)}</span>
                  <span className="timeline-date-mini">{formatSafeDate(ev.timestamp)}</span>
                </div>

                <div className="timeline-indicator-col">
                  <div className={`timeline-node ${ev.badgeClass}`} />
                  {idx < filteredEvents.length - 1 && <div className="timeline-connector-line" />}
                </div>

                <div className="timeline-content-col">
                  <div className="timeline-content-header">
                    <span className="timeline-event-title">{ev.displayName}</span>
                    <span className={`timeline-category-tag ${ev.badgeClass}`}>
                      {ev.category}
                    </span>
                  </div>
                  {ev.reasons.length > 0 && (
                    <div className="timeline-reasons-list">
                      {ev.reasons.map((r, rIdx) => (
                        <span key={rIdx} className="timeline-reason-pill">
                          {r.replace(/_/g, " ")}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
