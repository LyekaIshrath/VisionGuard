import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

export interface User {
  id: string;
  _id?: string;
  email?: string;
  display_name?: string;
  status?: string;
}

export interface AuthSession {
  access_token: string;
  token_type?: string;
  user: User;
}

interface AuthContextType {
  user: User | null;
  session: AuthSession | null;
  token: string | null;
  loading: boolean;
  isConfigured: boolean;
  signIn: (email: string, password: string) => Promise<{ error: Error | null }>;
  signUp: (email: string, password: string, displayName?: string) => Promise<{ error: Error | null }>;
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

  const signUp = useCallback(
    async (email: string, password: string, displayName?: string) => {
      try {
        const resp = await fetch("/api/v1/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email,
            password,
            display_name: displayName || undefined,
          }),
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
    },
    []
  );

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
        refreshUser,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
