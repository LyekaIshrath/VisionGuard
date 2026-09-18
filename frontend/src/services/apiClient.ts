/**
 * VisionGuard Central Authenticated API Client.
 *
 * Implements token injection, 401 detection, and automatic single-retry via session refresh.
 * If token refresh fails, invalid auth state is cleared and an event is emitted so UI can notify the user.
 * Local vision monitoring (camera, posture, alertness, risk, local audio) is never terminated by cloud auth expiration.
 */

import { supabase } from "./supabase";

export interface ApiFetchOptions extends RequestInit {
  /** If true, requires authentication and skips request if no session */
  requireAuth?: boolean;
}

type AuthExpiredCallback = () => void;
const authExpiredListeners: Set<AuthExpiredCallback> = new Set();

/**
 * Register a listener invoked when a 401 token refresh fails, requiring re-authentication.
 */
export function onAuthExpired(callback: AuthExpiredCallback): () => void {
  authExpiredListeners.add(callback);
  return () => {
    authExpiredListeners.delete(callback);
  };
}

export function notifyAuthExpired(): void {
  authExpiredListeners.forEach((fn) => {
    try {
      fn();
    } catch (e) {
      console.error("[ApiClient] Auth expired listener error:", e);
    }
  });
}

/**
 * Authenticated fetch with automatic token injection and 401 refresh-and-retry (exactly once).
 */
export async function apiFetch(input: string | URL | Request, init?: ApiFetchOptions): Promise<Response> {
  const options: ApiFetchOptions = { ...init };
  const headers = new Headers(options.headers || {});

  let currentToken: string | null = null;

  if (supabase) {
    try {
      const { data } = await supabase.auth.getSession();
      currentToken = data.session?.access_token ?? null;
    } catch (err) {
      console.warn("[ApiClient] Failed to get current session:", err);
    }
  }

  if (options.requireAuth && !currentToken) {
    throw new Error("Authentication required for this request.");
  }

  if (currentToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${currentToken}`);
  }

  options.headers = headers;

  // 1. Initial Request
  let response = await fetch(input, options);

  // 2. If 401 Unauthorized, attempt refresh exactly once
  if (response.status === 401 && supabase) {
    console.warn("[ApiClient] 401 Unauthorized received. Attempting session refresh...");
    try {
      const { data: refreshData, error: refreshError } = await supabase.auth.refreshSession();

      if (!refreshError && refreshData.session?.access_token) {
        const newToken = refreshData.session.access_token;
        console.info("[ApiClient] Session refreshed successfully. Retrying original request ONCE...");

        // Clone headers and inject refreshed access token
        const retryHeaders = new Headers(options.headers);
        retryHeaders.set("Authorization", `Bearer ${newToken}`);

        const retryOptions: ApiFetchOptions = {
          ...options,
          headers: retryHeaders,
        };

        // Retry original request exactly ONCE
        response = await fetch(input, retryOptions);
      } else {
        console.warn("[ApiClient] Session refresh failed. Clearing invalid auth state.");
        // Clear invalid auth state
        await supabase.auth.signOut().catch(() => {});
        notifyAuthExpired();
      }
    } catch (refreshErr) {
      console.error("[ApiClient] Exception during session refresh:", refreshErr);
      await supabase.auth.signOut().catch(() => {});
      notifyAuthExpired();
    }
  }

  return response;
}
