import React from "react";
import { RiskStatusResponse, RiskLevel } from "../types";
import { StatusBadge } from "./StatusBadge";

interface RiskCardProps {
  riskStatus: RiskStatusResponse | null;
  overallRiskLevel: RiskLevel;
}

export const RiskCard: React.FC<RiskCardProps> = ({
  riskStatus,
  overallRiskLevel,
}) => {
  const score = riskStatus?.risk_score;
  const pRisk = riskStatus?.posture_risk;
  const aRisk = riskStatus?.alertness_risk;
  const reasons = riskStatus?.active_reasons || [];
  const dominant = riskStatus?.dominant_category;

  const formatReason = (reason: string) => {
    return reason.replace(/_/g, " ").toLowerCase();
  };

  const getMeterColorClass = () => {
    if (score === null || score === undefined) return "meter-unknown";
    if (score >= 70) return "meter-high";
    if (score >= 40) return "meter-warning";
    return "meter-good";
  };

  return (
    <section className="dashboard-card risk-card" id="risk-section" aria-label="Safety and Wellness Risk Intelligence">
      <div className="card-header">
        <div className="card-title-group">
          <h2 className="card-title">SAFETY &amp; WELLNESS RISK</h2>
          <span className="card-subtitle">Temporal Asymmetric Hysteresis Fusion</span>
        </div>
        <StatusBadge type="risk" value={overallRiskLevel} />
      </div>

      <div className="risk-body">
        <div className="risk-primary-stat">
          <div className="risk-level-display">
            <span className="risk-level-value">{overallRiskLevel}</span>
            {dominant && (
              <span className="dominant-tag">
                Driven by {dominant}
              </span>
            )}
          </div>
          <div className="risk-score-display">
            <span className="risk-score-number">{score !== null && score !== undefined ? Math.round(score) : "—"}</span>
            <span className="risk-score-denom">/ 100</span>
          </div>
        </div>

        <div className="risk-meter-wrapper">
          <div className="risk-meter-bar" role="progressbar" aria-valuenow={score || 0} aria-valuemin={0} aria-valuemax={100} aria-label="Continuous Risk Score">
            <div
              className={`risk-meter-fill ${getMeterColorClass()}`}
              style={{ width: `${Math.max(0, Math.min(100, score || 0))}%` }}
            />
          </div>
          <div className="risk-meter-labels">
            <span>0 LOW</span>
            <span>40 MODERATE</span>
            <span>70 HIGH</span>
            <span>100</span>
          </div>
        </div>

        <div className="domain-breakdown">
          <div className="domain-row">
            <div className="domain-info">
              <span className="domain-name">Posture Risk</span>
              <span className="domain-desc">Duration + severity accumulation</span>
            </div>
            <div className="domain-status">
              <StatusBadge type="risk" value={pRisk?.level || "UNKNOWN"} />
              {pRisk?.score !== null && pRisk?.score !== undefined && (
                <span className="domain-score">{pRisk.score}</span>
              )}
            </div>
          </div>

          <div className="domain-row">
            <div className="domain-info">
              <span className="domain-name">Alertness Risk</span>
              <span className="domain-desc">Eye closure &amp; vigilance signals</span>
            </div>
            <div className="domain-status">
              <StatusBadge type="risk" value={aRisk?.level || "UNKNOWN"} />
              {aRisk?.score !== null && aRisk?.score !== undefined && (
                <span className="domain-score">{aRisk.score}</span>
              )}
            </div>
          </div>
        </div>

        <div className="active-signals-section">
          <span className="signals-title">ACTIVE SIGNALS</span>
          <div className="signals-chips">
            {reasons.length === 0 ? (
              <span className="signal-chip chip-normal">No active risk signals</span>
            ) : (
              reasons.map((r, i) => (
                <span key={i} className="signal-chip chip-active">
                  {formatReason(r)}
                </span>
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
