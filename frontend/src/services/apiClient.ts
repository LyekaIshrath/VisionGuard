/**
 * VisionGuard Central Authenticated API Client.
 *
 * Implements token injection and 401 detection backed by MongoDB session tokens.
 * If 401 Unauthorized is received, auth state is cleared and an event is emitted.
 * Local vision monitoring (camera, posture, alertness, risk, local audio) is never terminated by cloud auth expiration.
 */

export interface ApiFetchOptions extends RequestInit {
  /** If true, requires authentication and skips request if no session */
  requireAuth?: boolean;
}

type AuthExpiredCallback = () => void;
const authExpiredListeners: Set<AuthExpiredCallback> = new Set();
const TOKEN_KEY = "visionguard_token";

/**
 * Register a listener invoked when a 401 occurs requiring re-authentication.
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
 * Authenticated fetch with automatic token injection and 401 handling.
 */
export async function apiFetch(input: string | URL | Request, init?: ApiFetchOptions): Promise<Response> {
  const options: ApiFetchOptions = { ...init };
  const headers = new Headers(options.headers || {});

  const currentToken = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;

  if (options.requireAuth && !currentToken) {
    throw new Error("Authentication required for this request.");
  }

  if (currentToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${currentToken}`);
  }

  options.headers = headers;

  const response = await fetch(input, options);

  if (response.status === 401) {
    console.warn("[ApiClient] 401 Unauthorized received. Clearing stored token.");
    if (typeof window !== "undefined") {
      localStorage.removeItem(TOKEN_KEY);
    }
    notifyAuthExpired();
  }

  return response;
}
