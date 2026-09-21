import { apiFetch } from "../services/apiClient";
﻿import React, { useState } from "react";
import { useAuth } from "../contexts/AuthContext";

interface PrivacyViewProps {
  apiBase: string;
  onOpenAuth: () => void;
}

export const PrivacyView: React.FC<PrivacyViewProps> = ({
  apiBase,
  onOpenAuth,
}) => {
  const { user, token } = useAuth();
  const [deleting, setDeleting] = useState<boolean>(false);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState<boolean>(false);

  const handleDeleteData = async () => {
    if (!token) return;
    setDeleting(true);
    setDeleteMessage(null);
    try {
      const resp = await apiFetch(`${apiBase}/api/v1/user/data`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (resp.ok) {
        const result = await resp.json();
        setDeleteMessage(result.message || "VisionGuard application data deleted successfully.");
        setShowConfirm(false);
      } else {
        setDeleteMessage("Failed to delete application data.");
      }
    } catch (err: any) {
      setDeleteMessage(err.message || "Network error deleting data.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="privacy-view-container">
      <div className="view-header">
        <div>
          <h2 className="view-title">Privacy &amp; Data Sovereignty</h2>
          <p className="view-subtitle">Guaranteed local edge processing, zero image persistence, and data deletion</p>
        </div>
      </div>

      <div className="privacy-cards-grid">
        <div className="privacy-info-card">
          <div className="privacy-card-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <h3 className="privacy-card-title">100% Local AI Perception</h3>
          <p className="privacy-card-desc">
            Your webcam feed is processed purely in volatile memory on your local machine using MediaPipe.
            Raw video frames, annotated frames, face crops, and raw coordinate landmarks are NEVER uploaded, stored, or transmitted.
          </p>
        </div>

        <div className="privacy-info-card">
          <div className="privacy-card-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <h3 className="privacy-card-title">Row-Level Security (RLS)</h3>
          <p className="privacy-card-desc">
            All persisted metrics (session durations, average scores, and risk event logs) are strictly scoped
            to your user ID using PostgreSQL Row-Level Security. No user can read or modify another user's records.
          </p>
        </div>

        <div className="privacy-info-card">
          <div className="privacy-card-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
          </div>
          <h3 className="privacy-card-title">Delete My VisionGuard Data</h3>
          <p className="privacy-card-desc">
            You maintain complete sovereignty over your data. You can delete all your monitoring sessions,
            temporal risk events, ergonomic preferences, and application profile at any time.
          </p>
        </div>
      </div>

      <div className="data-deletion-panel">
        <h3 className="panel-title">Manage Your VisionGuard Data</h3>
        <p className="panel-desc">
          Click below to permanently wipe all monitoring sessions, risk events, and application settings
          associated with your account.
        </p>

        {deleteMessage && <div className="auth-alert success">{deleteMessage}</div>}

        {!user ? (
          <div className="auth-prompt">
            <p>You are currently in local guest mode. Sign in to manage cloud data persistence.</p>
            <button className="btn btn-secondary btn-sm" onClick={onOpenAuth}>
              Sign In
            </button>
          </div>
        ) : showConfirm ? (
          <div className="confirm-delete-box">
            <div className="confirm-warning">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <div>
                <strong>Confirm Deletion:</strong> This action will permanently remove all your monitoring sessions,
                risk event histories, and ergonomic preferences.
                <p className="confirm-clarification">
                  <strong>Notice:</strong> Your login credentials remain active in the database.
                  Only application data (sessions, risk events, preferences) will be deleted.
                </p>
              </div>
            </div>

            <div className="confirm-actions">
              <button
                className="btn btn-danger btn-sm"
                onClick={handleDeleteData}
                disabled={deleting}
              >
                {deleting ? "Deleting Data..." : "Yes, Delete My VisionGuard Data"}
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setShowConfirm(false)}
                disabled={deleting}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            className="btn btn-outline-danger"
            onClick={() => setShowConfirm(true)}
          >
            Delete My VisionGuard Data
          </button>
        )}
      </div>
    </div>
  );
};
