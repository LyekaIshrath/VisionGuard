import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

export interface User {
  id: string;
  _id?: string;
  email?: string;
  display_name?: string;
  phone_number?: string;
  phone_masked?: string;
  phone_verified?: boolean;
  phone_verified_at?: string;
  status?: string;
}

export interface AuthSession {
  access_token: string;
  token_type?: string;
  user: User;
}

export interface RegisterStartData {
  full_name: string;
  email: string;
  phone_number: string;
  password: string;
  confirm_password?: string;
}

interface AuthContextType {
  user: User | null;
  session: AuthSession | null;
  token: string | null;
  loading: boolean;
  isConfigured: boolean;
  signIn: (email: string, password: string) => Promise<{ error: Error | null }>;
  signUp: (email: string, password: string) => Promise<{ error: Error | null }>;
  startRegister: (data: RegisterStartData) => Promise<{ error: Error | null; data?: any }>;
  verifyRegister: (phoneNumber: string, code: string) => Promise<{ error: Error | null }>;
  resendRegisterOtp: (phoneNumber: string) => Promise<{ error: Error | null; data?: any }>;
  startPhoneChange: (newPhone: string) => Promise<{ error: Error | null; data?: any }>;
  verifyPhoneChange: (newPhone: string, code: string) => Promise<{ error: Error | null; data?: any }>;
  refreshUser: () => Promise<void>;
  signOut: () => Promise<void>;
}

const TOKEN_KEY = "visionguard_token";

const AuthContext = createContext<AuthContextType>({
  user: null,
  session: null,
  token: null,
  loading: true,
  isConfigured: true,
  signIn: async () => ({ error: null }),
  signUp: async () => ({ error: null }),
  startRegister: async () => ({ error: null }),
  verifyRegister: async () => ({ error: null }),
  resendRegisterOtp: async () => ({ error: null }),
  startPhoneChange: async () => ({ error: null }),
  verifyPhoneChange: async () => ({ error: null }),
  refreshUser: async () => {},
  signOut: async () => {},
});

async function parseJsonResponse(resp: Response): Promise<{ ok: boolean; data: any; errorMessage?: string }> {
  try {
    const text = await resp.text();
    try {
      const data = JSON.parse(text);
      return { ok: resp.ok, data, errorMessage: data?.detail || (typeof data === "string" ? data : undefined) };
    } catch {
      return { ok: resp.ok, data: null, errorMessage: text || resp.statusText || "Internal server error" };
    }
  } catch (err: any) {
    return { ok: false, data: null, errorMessage: err?.message || "Network error" };
  }
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshUser = useCallback(async () => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (!storedToken) return;

    try {
      const resp = await fetch("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${storedToken}` },
      });
      const { ok, data: userData } = await parseJsonResponse(resp);
      if (ok && userData) {
        const authUser: User = {
          id: userData.id || userData._id,
          email: userData.email,
          display_name: userData.display_name,
          phone_number: userData.phone_number,
          phone_masked: userData.phone_masked,
          phone_verified: userData.phone_verified,
          status: userData.status,
        };
        setUser(authUser);
      }
    } catch {
      // ignore
    }
  }, []);

  // Validate existing stored token on mount
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = localStorage.getItem(TOKEN_KEY);
      if (!storedToken) {
        setLoading(false);
        return;
      }

      try {
        const resp = await fetch("/api/v1/auth/me", {
          headers: { Authorization: `Bearer ${storedToken}` },
        });

        const { ok, data: userData } = await parseJsonResponse(resp);
        if (ok && userData) {
          const authUser: User = {
            id: userData.id || userData._id,
            email: userData.email,
            display_name: userData.display_name,
            phone_number: userData.phone_number,
            phone_masked: userData.phone_masked,
            phone_verified: userData.phone_verified,
            status: userData.status,
          };
          setUser(authUser);
          setSession({
            access_token: storedToken,
            token_type: "bearer",
            user: authUser,
          });
        } else {
          localStorage.removeItem(TOKEN_KEY);
        }
      } catch {
        localStorage.removeItem(TOKEN_KEY);
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    try {
      const resp = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const { ok, data, errorMessage } = await parseJsonResponse(resp);
      if (!ok || !data) {
        return { error: new Error(errorMessage || "Authentication failed.") };
      }

      const authToken = data.access_token;
      localStorage.setItem(TOKEN_KEY, authToken);

      const authUser: User = {
        id: data.user.id || data.user._id,
        email: data.user.email,
        display_name: data.user.display_name,
        phone_number: data.user.phone_number,
        phone_masked: data.user.phone_masked,
        phone_verified: data.user.phone_verified,
        status: data.user.status,
      };

      setUser(authUser);
      setSession({
        access_token: authToken,
        token_type: data.token_type || "bearer",
        user: authUser,
      });

      return { error: null };
    } catch (err: any) {
      return { error: new Error(err.message || "Network error during login.") };
    }
  }, []);

  const signUp = useCallback(async (email: string, password: string) => {
    try {
      const resp = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const { ok, data, errorMessage } = await parseJsonResponse(resp);
      if (!ok || !data) {
        return { error: new Error(errorMessage || "Registration failed.") };
      }

      const authToken = data.access_token;
      localStorage.setItem(TOKEN_KEY, authToken);

      const authUser: User = {
        id: data.user.id || data.user._id,
        email: data.user.email,
        display_name: data.user.display_name,
        phone_number: data.user.phone_number,
        phone_masked: data.user.phone_masked,
        phone_verified: data.user.phone_verified,
        status: data.user.status,
      };

      setUser(authUser);
      setSession({
        access_token: authToken,
        token_type: data.token_type || "bearer",
        user: authUser,
      });

      return { error: null };
    } catch (err: any) {
      return { error: new Error(err.message || "Network error during registration.") };
    }
  }, []);

  const startRegister = useCallback(async (data: RegisterStartData) => {
    try {
      const resp = await fetch("/api/v1/auth/register/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const { ok, data: res, errorMessage } = await parseJsonResponse(resp);
      if (!ok || !res) {
        return { error: new Error(errorMessage || "Failed to initiate registration.") };
      }
      return { error: null, data: res };
    } catch (err: any) {
      return { error: new Error(err.message || "Network error during registration.") };
    }
  }, []);

  const verifyRegister = useCallback(async (phoneNumber: string, code: string) => {
    try {
      const resp = await fetch("/api/v1/auth/register/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phoneNumber, code }),
      });
      const { ok, data, errorMessage } = await parseJsonResponse(resp);
      if (!ok || !data) {
        return { error: new Error(errorMessage || "Verification failed.") };
      }

      const authToken = data.access_token;
      localStorage.setItem(TOKEN_KEY, authToken);

      const authUser: User = {
        id: data.user.id || data.user._id,
        email: data.user.email,
        display_name: data.user.display_name,
        phone_number: data.user.phone_number,
        phone_masked: data.user.phone_masked,
        phone_verified: true,
        status: data.user.status,
      };

      setUser(authUser);
      setSession({
        access_token: authToken,
        token_type: data.token_type || "bearer",
        user: authUser,
      });

      return { error: null };
    } catch (err: any) {
      return { error: new Error(err.message || "Network error during verification.") };
    }
  }, []);

  const resendRegisterOtp = useCallback(async (phoneNumber: string) => {
    try {
      const resp = await fetch("/api/v1/auth/register/resend-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phoneNumber }),
      });
      const { ok, data: res, errorMessage } = await parseJsonResponse(resp);
      if (!ok || !res) {
        return { error: new Error(errorMessage || "Failed to resend code.") };
      }
      return { error: null, data: res };
    } catch (err: any) {
      return { error: new Error(err.message || "Network error.") };
    }
  }, []);

  const startPhoneChange = useCallback(async (newPhone: string) => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (!storedToken) return { error: new Error("Not authenticated.") };

    try {
      const resp = await fetch("/api/v1/auth/phone/start-change", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${storedToken}`,
        },
        body: JSON.stringify({ new_phone_number: newPhone }),
      });
      const { ok, data: res, errorMessage } = await parseJsonResponse(resp);
      if (!ok || !res) {
        return { error: new Error(errorMessage || "Failed to start phone change.") };
      }
      return { error: null, data: res };
    } catch (err: any) {
      return { error: new Error(err.message || "Network error.") };
    }
  }, []);

  const verifyPhoneChange = useCallback(async (newPhone: string, code: string) => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (!storedToken) return { error: new Error("Not authenticated.") };

    try {
      const resp = await fetch("/api/v1/auth/phone/verify-change", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${storedToken}`,
        },
        body: JSON.stringify({ new_phone_number: newPhone, code }),
      });
      const { ok, data: res, errorMessage } = await parseJsonResponse(resp);
      if (!ok || !res) {
        return { error: new Error(errorMessage || "Failed to verify phone change.") };
      }
      await refreshUser();
      return { error: null, data: res };
    } catch (err: any) {
      return { error: new Error(err.message || "Network error.") };
    }
  }, [refreshUser]);

  const signOut = useCallback(async () => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (storedToken) {
      fetch("/api/v1/auth/logout", {
        method: "POST",
        headers: { Authorization: `Bearer ${storedToken}` },
      }).catch(() => {});
    }

    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    setSession(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        token: session?.access_token ?? (typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null),
        loading,
        isConfigured: true,
        signIn,
        signUp,
        startRegister,
        verifyRegister,
        resendRegisterOtp,
        startPhoneChange,
        verifyPhoneChange,
        refreshUser,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
