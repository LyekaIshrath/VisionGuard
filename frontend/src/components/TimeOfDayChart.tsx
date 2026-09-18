import React from "react";
import { TimeOfDayBucket } from "../types";

interface Props {
  data: TimeOfDayBucket[];
}

export const TimeOfDayChart: React.FC<Props> = ({ data }) => {
  if (!data || data.length === 0) {
    return <div className="chart-empty-state">No time-of-day exposure data available.</div>;
  }

  const maxExposure = Math.max(...data.map((d) => d.monitored_exposure_seconds), 3600);

  const getIcon = (bucket: string) => {
    switch (bucket) {
      case "MORNING": return "🌅";
      case "AFTERNOON": return "☀️";
      case "EVENING": return "🌆";
      case "NIGHT": return "🌙";
      default: return "⏱️";
    }
  };

  return (
    <div className="time-of-day-chart">
      <div className="tod-grid">
        {data.map((item) => {
          const hours = (item.monitored_exposure_seconds / 3600).toFixed(1);
          const barWidthPct = Math.min(100, Math.round((item.monitored_exposure_seconds / maxExposure) * 100));

          return (
            <div key={item.bucket} className="tod-card">
              <div className="tod-card-header">
                <span className="tod-icon">{getIcon(item.bucket)}</span>
                <div className="tod-title-col">
                  <span className="tod-label">{item.label}</span>
                  <span className="tod-exposure">{hours} hrs monitored</span>
                </div>
              </div>

              <div className="tod-bar-wrapper">
                <div
                  className={`tod-progress-bar ${item.bucket.toLowerCase()}`}
                  style={{ width: `${barWidthPct}%` }}
                />
              </div>

              <div className="tod-card-footer">
                <span className="tod-events-count">{item.risk_event_count} risk events</span>
                <span className="tod-rate">
                  {item.events_per_monitored_hour !== null
                    ? `${item.events_per_monitored_hour} / hr`
                    : "insufficient data"}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
