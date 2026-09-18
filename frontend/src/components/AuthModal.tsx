import React, { useState } from "react";
import { useAuth } from "../contexts/AuthContext";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose }) => {
  const { signIn, signUp, isConfigured } = useAuth();
  const [isSignUp, setIsSignUp] = useState<boolean>(false);
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!email || !password) {
      setErrorMsg("Please enter both email and password.");
      return;
    }

    setSubmitting(true);
    try {
      if (isSignUp) {
        const { error } = await signUp(email, password);
        if (error) {
          const errStatus = (error as any).status;
          const errCode = (error as any).code || "";
          const msg = (error.message || "").toLowerCase();
          if (
            errStatus === 429 ||
            errCode === "over_email_send_rate_limit" ||
            msg.includes("over_email_send_rate_limit") ||
            msg.includes("rate limit") ||
            msg.includes("too many requests")
          ) {
            setErrorMsg("Too many verification emails were requested. Please wait a little before trying again.");
          } else {
            setErrorMsg(error.message);
          }
        } else {
          setSuccessMsg("Account created! Check your email for confirmation or sign in.");
        }
      } else {
        const { error } = await signIn(email, password);
        if (error) {
          const errStatus = (error as any).status;
          const errCode = (error as any).code || "";
          const msg = (error.message || "").toLowerCase();
          if (
            errStatus === 429 ||
            errCode === "over_email_send_rate_limit" ||
            msg.includes("over_email_send_rate_limit") ||
            msg.includes("rate limit") ||
            msg.includes("too many requests")
          ) {
            setErrorMsg("Too many verification emails were requested. Please wait a little before trying again.");
          } else {
            setErrorMsg(error.message);
          }
        } else {
          onClose();
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || "An unexpected error occurred.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} aria-modal="true" role="dialog">
      <div className="modal-card auth-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-group">
            <h2 className="modal-title">{isSignUp ? "Create VisionGuard Account" : "Sign in to VisionGuard"}</h2>
            <p className="modal-subtitle">Sync your sessions and analytics securely with Row-Level Privacy</p>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {!isConfigured && (
          <div className="auth-notice warning">
            <strong>Local Mode Active:</strong> Supabase cloud credentials are not configured on this frontend. 
            All vision processing and session monitoring will continue locally on your machine.
          </div>
        )}

        {errorMsg && <div className="auth-alert error">{errorMsg}</div>}
        {successMsg && <div className="auth-alert success">{successMsg}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="auth-email">Email Address</label>
            <input
              id="auth-email"
              type="email"
              className="form-input"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting || !isConfigured}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              className="form-input"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting || !isConfigured}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-block auth-submit-btn"
            disabled={submitting || !isConfigured}
          >
            {submitting ? "Processing..." : isSignUp ? "Create Account" : "Sign In"}
          </button>
        </form>

        <div className="auth-toggle">
          {isSignUp ? (
            <span>
              Already have an account?{" "}
              <button type="button" className="auth-link-btn" onClick={() => setIsSignUp(false)}>
                Sign In
              </button>
            </span>
          ) : (
            <span>
              Don't have an account?{" "}
              <button type="button" className="auth-link-btn" onClick={() => setIsSignUp(true)}>
                Sign Up
              </button>
            </span>
          )}
        </div>

        <div className="auth-privacy-footnote">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span>Raw webcam frames and face landmarks are NEVER uploaded or stored.</span>
        </div>
      </div>
    </div>
  );
};
