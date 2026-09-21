import React, { useState } from "react";
import { RiskEvent } from "../types";
import { StatusBadge } from "./StatusBadge";

interface EventTimelineProps {
  events: RiskEvent[];
  onClearHistory: () => void;
}

function formatSafeTime(timestamp?: string | number | Date | null): string {
  if (!timestamp) return "--";
  try {
    const d = new Date(timestamp);
    return isNaN(d.getTime()) ? "--" : d.toLocaleTimeString();
  } catch {
    return "--";
  }
}

export const EventTimeline: React.FC<EventTimelineProps> = ({
  events,
  onClearHistory,
}) => {
  const [showAll, setShowAll] = useState(false);
  const displayLimit = 5;

  // Most recent first
  const reversedEvents = [...events].reverse();
  const visibleEvents = showAll ? reversedEvents : reversedEvents.slice(0, displayLimit);

  const formatReasonCodes = (reasons: string[]) => {
    if (!reasons || reasons.length === 0) return "Normal";
    return reasons.map((r) => r.replace(/_/g, " ").toLowerCase()).join(", ");
  };

  return (
    <section className="dashboard-card events-card" id="events-section" aria-label="Recent Risk Events History">
      <div className="card-header">
        <div className="card-title-group">
          <h2 className="card-title">RECENT RISK EVENTS</h2>
          <span className="card-subtitle">Meaningful Lifecycle Escalation &amp; Resolution History</span>
        </div>
        <div className="card-header-actions">
          {events.length > displayLimit && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setShowAll(!showAll)}
            >
              {showAll ? "Show Recent" : `View All (${events.length})`}
            </button>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={onClearHistory}
            disabled={events.length === 0}
            title="Clears event history log and alert cooldowns. Does not alter ongoing physical risk."
          >
            Clear History
          </button>
        </div>
      </div>

      <div className="events-body">
        {events.length === 0 ? (
          <div className="events-empty-state">
            <p>No risk events recorded yet.</p>
            <span className="empty-subtext">Events are generated on meaningful domain escalation or resolution.</span>
          </div>
        ) : (
          <div className="events-table-wrapper">
            <table className="events-table">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Category</th>
                  <th scope="col">Event / Signals</th>
                  <th scope="col">Level</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {visibleEvents.map((ev) => (
                  <tr key={ev.event_id} className={`event-row event-${ev.status.toLowerCase()}`}>
                    <td className="cell-time">{formatSafeTime(ev.timestamp)}</td>
                    <td className="cell-category">
                      <span className={`category-tag ${ev.category.toLowerCase()}`}>{ev.category}</span>
                    </td>
                    <td className="cell-event">
                      <div className="event-cell-content">
                        <span className="event-msg">{ev.message}</span>
                        {ev.reason_codes && ev.reason_codes.length > 0 && (
                          <span className="event-reasons">{formatReasonCodes(ev.reason_codes)}</span>
                        )}
                      </div>
                    </td>
                    <td className="cell-level">
                      <StatusBadge type="risk" value={ev.risk_level} />
                    </td>
                    <td className="cell-status">
                      <StatusBadge type="event" value={ev.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card-footer">
        <span className="footer-disclaimer">
          Clearing history resets the event ring buffer and rate-limiting cooldowns. It does not alter ongoing active risk state.
        </span>
      </div>
    </section>
  );
};
