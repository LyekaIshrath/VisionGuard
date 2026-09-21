import React from "react";

export const PrivacyPanel: React.FC = () => {
  const privacyGuarantees = [
    "Local camera processing",
    "No raw video stored",
    "No screenshots stored",
    "No facial identity recognition",
    "No typed content stored",
    "No passwords captured",
    "No mouse coordinates stored",
  ];

  return (
    <footer className="report-privacy-panel">
      <div className="privacy-panel-header">
        <div className="privacy-title-group">
          <svg className="privacy-shield-icon" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M10 1.944A11.954 11.954 0 012.166 5C2.056 5.649 2 6.319 2 7c0 5.225 3.34 9.67 8 11.317C14.66 16.67 18 12.225 18 7c0-.682-.057-1.35-.166-2.001A11.954 11.954 0 0110 1.944zM11 14a1 1 0 11-2 0 1 1 0 012 0zm0-7a1 1 0 10-2 0v3a1 1 0 102 0V7z"
              clipRule="evenodd"
            />
          </svg>
          <span className="privacy-title">PRIVACY BY DESIGN</span>
        </div>
        <span className="privacy-subtitle">Edge telemetry architecture</span>
      </div>

      <div className="privacy-guarantee-grid">
        {privacyGuarantees.map((item, idx) => (
          <div key={idx} className="privacy-guarantee-item">
            <svg className="privacy-check-icon" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
            <span className="privacy-guarantee-text">{item}</span>
          </div>
        ))}
      </div>

      <p className="privacy-bottom-notice">
        Cloud/database stores derived session metrics and discrete state transitions only.
      </p>
    </footer>
  );
};
