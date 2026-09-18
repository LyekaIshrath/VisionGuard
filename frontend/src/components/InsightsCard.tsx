import React from "react";
import { Insight } from "../types";

interface Props {
  insights: Insight[];
}

export const InsightsCard: React.FC<Props> = ({ insights }) => {
  if (!insights || insights.length === 0) {
    return null;
  }

  const getTypeBadge = (type: string) => {
    switch (type) {
      case "POSITIVE_PATTERN":
        return <span className="insight-badge positive">Positive Habit</span>;
      case "ATTENTION_PATTERN":
        return <span className="insight-badge attention">Attention Needed</span>;
      case "INFORMATIONAL":
        return <span className="insight-badge info">Telemetry Notice</span>;
      default:
        return <span className="insight-badge insufficient">Baseline Forming</span>;
    }
  };

  return (
    <div className="insights-card-container">
      <div className="insights-header">
        <h3 className="section-title">Personal Ergonomic Intelligence</h3>
        <span className="insights-subtitle">Deterministic insights derived from your observed sessions</span>
      </div>

      <div className="insights-list">
        {insights.map((ins) => (
          <div key={ins.id} className={`insight-item ${ins.type.toLowerCase()}`}>
            <div className="insight-top">
              {getTypeBadge(ins.type)}
              <h4 className="insight-title">{ins.title}</h4>
            </div>
            <p className="insight-desc">{ins.description}</p>
            {ins.recommended_action && (
              <div className="insight-action">
                <span className="action-icon">💡</span>
                <span className="action-text">{ins.recommended_action}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
