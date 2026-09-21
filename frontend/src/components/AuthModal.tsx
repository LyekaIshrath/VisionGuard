import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

function formatAuthError(rawError: any): string {
  if (!rawError) return "An unexpected error occurred. Please try again.";
  const msg = typeof rawError === "string" ? rawError : rawError.message || "";

  if (
    msg.includes("Unexpected token") ||
    msg.includes("is not valid JSON") ||
    msg.includes("Internal Server Error") ||
    msg.includes("Internal S")
  ) {
    return "Unable to connect to VisionGuard. Please try again shortly.";
  }
  if (
    msg.includes("401") ||
    msg.includes("Invalid credentials") ||
    msg.includes("Incorrect email or password") ||
    msg.toLowerCase().includes("invalid email or password")
  ) {
    return "Incorrect email or password.";
  }
  if (msg.includes("sms") || msg.includes("phone") || msg.includes("twilio") || msg.includes("OTP")) {
    if (msg.includes("Invalid verification code") || msg.includes("Incorrect code")) {
      return "Incorrect verification code. Please check and try again.";
    }
    return "Phone verification service unavailable.";
  }
  if (msg.includes("Failed to fetch") || msg.includes("NetworkError") || msg.includes("Network error")) {
    return "Unable to connect to VisionGuard.";
  }
  if (msg.length > 120 || msg.includes("Traceback") || msg.includes("File \"")) {
    return "Unable to connect to VisionGuard.";
  }
  return msg;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose }) => {
  const { signIn, startRegister, verifyRegister, resendRegisterOtp, isConfigured } = useAuth();
  const [isSignUp, setIsSignUp] = useState<boolean>(false);
  const [step, setStep] = useState<"FORM" | "OTP">("FORM");

  // Form Fields
  const [fullName, setFullName] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [phoneNumber, setPhoneNumber] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [otpCode, setOtpCode] = useState<string>("");

  // States
  const [maskedPhone, setMaskedPhone] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [cooldown, setCooldown] = useState<number>(0);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Cooldown countdown timer
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  if (!isOpen) return null;

  const handleReset = () => {
    setErrorMsg(null);
    setSuccessMsg(null);
    setOtpCode("");
    setStep("FORM");
  };

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!email || !password) {
      setErrorMsg("Please enter both email and password.");
      return;
    }

    setSubmitting(true);
    try {
      const { error } = await signIn(email, password);
      if (error) {
        setErrorMsg(formatAuthError(error));
      } else {
        onClose();
      }
    } catch (err) {
      setErrorMsg(formatAuthError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleStartRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!fullName.trim()) {
      setErrorMsg("Please enter your full name.");
      return;
    }
    if (!email.trim()) {
      setErrorMsg("Please enter your email.");
      return;
    }
    if (!phoneNumber.trim()) {
      setErrorMsg("Please enter your mobile number in E.164 format (e.g. +919876543210).");
      return;
    }
    if (password.length < 6) {
      setErrorMsg("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMsg("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const { error, data } = await startRegister({
        full_name: fullName.trim(),
        email: email.trim(),
        phone_number: phoneNumber.trim(),
        password,
        confirm_password: confirmPassword,
      });

      if (error) {
        setErrorMsg(formatAuthError(error));
      } else {
        setMaskedPhone(data?.phone_number_masked || phoneNumber);
        setCooldown(data?.resend_cooldown_seconds || 60);
        setSuccessMsg("Verification code dispatched to your phone.");
        setStep("OTP");
      }
    } catch (err) {
      setErrorMsg(formatAuthError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!otpCode || otpCode.length < 4) {
      setErrorMsg("Please enter the verification code.");
      return;
    }

    setSubmitting(true);
    try {
      const { error } = await verifyRegister(email.trim(), otpCode.trim());
      if (error) {
        setErrorMsg(formatAuthError(error));
      } else {
        setSuccessMsg("Account verified successfully! Welcome to VisionGuard.");
        setTimeout(() => {
          onClose();
        }, 1200);
      }
    } catch (err) {
      setErrorMsg(formatAuthError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleResendOtp = async () => {
    if (cooldown > 0) return;
    setErrorMsg(null);
    setSuccessMsg(null);

    setSubmitting(true);
    try {
      const { error, data } = await resendRegisterOtp(email.trim());
      if (error) {
        setErrorMsg(formatAuthError(error));
      } else {
        setCooldown(data?.resend_cooldown_seconds || 60);
        setSuccessMsg("A fresh verification code has been dispatched.");
      }
    } catch (err) {
      setErrorMsg(formatAuthError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="auth-modal-card" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="auth-modal-close"
          onClick={onClose}
          aria-label="Close authentication modal"
        >
          ✕
        </button>

        <div className="auth-modal-header">
          <div className="auth-brand-badge">VisionGuard SaaS</div>
          <h2 className="auth-modal-title">
            {isSignUp ? (step === "OTP" ? "Verify Your Phone" : "Create VisionGuard Account") : "Welcome Back"}
          </h2>
          <p className="auth-modal-subtitle">
            {isSignUp
              ? step === "OTP"
                ? `Enter the 6-digit code sent to ${maskedPhone || "your phone"}`
                : "Continuous ergonomic and wellness intelligence across your workstations."
              : "Sign in to access personalized baselines, reports, and remote SMS alerts."}
          </p>
        </div>

        {errorMsg && (
          <div className="auth-banner auth-banner-error" role="alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="auth-banner auth-banner-success" role="status">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <span>{successMsg}</span>
          </div>
        )}

        {/* 1. SIGN IN FORM */}
        {!isSignUp && (
          <form onSubmit={handleSignIn} className="auth-form">
            <div className="form-group">
              <label className="form-label" htmlFor="auth-email">Email Address</label>
              <input
                id="auth-email"
                type="email"
                className="form-input"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                autoComplete="email"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="auth-password">Password</label>
              <input
                id="auth-password"
                type="password"
                className="form-input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
                autoComplete="current-password"
                required
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-block auth-submit-btn"
              disabled={submitting || !isConfigured}
            >
              {submitting ? "Signing In..." : "Sign In"}
            </button>
          </form>
        )}

        {/* 2. SIGN UP: STEP 1 (FORM) */}
        {isSignUp && step === "FORM" && (
          <form onSubmit={handleStartRegister} className="auth-form">
            <div className="form-group">
              <label className="form-label" htmlFor="reg-name">Full Name</label>
              <input
                id="reg-name"
                type="text"
                className="form-input"
                placeholder="Jane Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={submitting}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="reg-email">Email Address</label>
              <input
                id="reg-email"
                type="email"
                className="form-input"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                autoComplete="email"
                required
              />
            </div>

            <div className="form-group">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <label className="form-label" htmlFor="reg-phone">Mobile Number</label>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)" }}>E.164 with Country Code</span>
              </div>
              <input
                id="reg-phone"
                type="tel"
                className="form-input"
                placeholder="+919876543210"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                disabled={submitting}
                required
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label" htmlFor="reg-password">Password</label>
                <input
                  id="reg-password"
                  type="password"
                  className="form-input"
                  placeholder="Min 6 chars"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={submitting}
                  autoComplete="new-password"
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="reg-confirm">Confirm Password</label>
                <input
                  id="reg-confirm"
                  type="password"
                  className="form-input"
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={submitting}
                  autoComplete="new-password"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-block auth-submit-btn"
              disabled={submitting || !isConfigured}
            >
              {submitting ? "Sending Verification Code..." : "Send Verification Code"}
            </button>
          </form>
        )}

        {/* 3. SIGN UP: STEP 2 (OTP VERIFICATION) */}
        {isSignUp && step === "OTP" && (
          <form onSubmit={handleVerifyOtp} className="auth-form">
            <div className="form-group">
              <label className="form-label" htmlFor="reg-otp">6-Digit Verification Code</label>
              <input
                id="reg-otp"
                type="text"
                className="form-input"
                placeholder="123456"
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                maxLength={6}
                disabled={submitting}
                autoFocus
                required
                style={{ textAlign: "center", letterSpacing: "0.4em", fontSize: "1.25rem", fontWeight: 700 }}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary btn-block auth-submit-btn"
              disabled={submitting || otpCode.length < 4}
            >
              {submitting ? "Verifying..." : "Verify & Activate Account"}
            </button>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1rem" }}>
              <button
                type="button"
                className="auth-link-btn"
                onClick={() => setStep("FORM")}
                disabled={submitting}
              >
                ← Back to Edit
              </button>

              <button
                type="button"
                className="auth-link-btn"
                onClick={handleResendOtp}
                disabled={cooldown > 0 || submitting}
              >
                {cooldown > 0 ? `Resend Code (${cooldown}s)` : "Resend Code"}
              </button>
            </div>
          </form>
        )}

        <div className="auth-toggle">
          {isSignUp ? (
            <span>
              Already have an account?{" "}
              <button
                type="button"
                className="auth-link-btn"
                onClick={() => {
                  setIsSignUp(false);
                  handleReset();
                }}
              >
                Sign In
              </button>
            </span>
          ) : (
            <span>
              Don't have an account?{" "}
              <button
                type="button"
                className="auth-link-btn"
                onClick={() => {
                  setIsSignUp(true);
                  handleReset();
                }}
              >
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
