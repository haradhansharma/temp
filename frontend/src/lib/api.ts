/**
 * API Client — centralized fetch wrapper for Django Ninja backend.
 *
 * All API calls go through here so auth headers, error handling,
 * and token refresh are handled in one place.
 *
 * Usage in Vue components (client-side only):
 *   import { apiClient } from "@/lib/api";
 *   const data = await apiClient.get("/auth/me");
 *   const result = await apiClient.post("/auth/login", { email, password });
 *
 * HIGH-03 FIX: Token Storage Security
 * ====================================
 * Tokens are now stored securely using a hybrid approach:
 *
 * - Access Token: Memory only (never persisted to storage)
 * - Refresh Token: httpOnly cookie (set by backend, not accessible to JS)
 * - "Remember Me": Controlled by cookie expiration on backend
 *
 * This prevents XSS attacks from stealing refresh tokens.
 * The cookie is httpOnly, secure (HTTPS only), and SameSite=Lax.
 *
 * Backwards Compatibility:
 * - The login response still contains tokens in the body for API clients
 * - The frontend ignores the body tokens and uses cookies instead
 */

// Vite will find this exact string and replace it during 'npm run build'
// Vite/Astro provides 'import.meta.env.DEV' which is true during 'npm run dev'
const isDev = import.meta.env.DEV;

const envUrl =
  process.env.SERVER_API_BASE_URL_SB || process.env.PUBLIC_API_BASE_URL_SB;

export const API_BASE_URL = isDev
  ? "http://localhost:8086/api/v1"
  : envUrl || "https://baseapi.sattaspace.com/api/v1";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
  errors?: Record<string, string[]>;
}

export interface ApiError {
  status: number;
  message: string;
  errors?: Record<string, string[]>;
}

// ─── Token Management (HIGH-03 FIX: Memory-only access token) ───────────────

// Access token is kept in memory only - never persisted to storage
// Refresh token is stored in httpOnly cookie by the backend
let _accessToken: string | null = null;

/**
 * Get the current access token from memory.
 * HIGH-03 FIX: Never reads from localStorage/sessionStorage.
 */
function getAccessToken(): string | null {
  return _accessToken;
}

/**
 * Set the access token in memory.
 * HIGH-03 FIX: Does NOT persist to localStorage/sessionStorage.
 */
function setAccessToken(token: string | null): void {
  _accessToken = token;
}

/**
 * Check if we have an access token (user is authenticated).
 */
function isAuthenticated(): boolean {
  return !!_accessToken;
}

/**
 * Clear the access token from memory.
 * Called on logout or when refresh fails.
 */
function clearAccessToken(): void {
  _accessToken = null;
}

function buildHeaders(custom?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...custom,
  };

  // If Content-Type was explicitly overridden to empty string,
  // remove it so the browser auto-sets multipart boundary for FormData uploads.
  if (headers["Content-Type"] === "") {
    delete headers["Content-Type"];
  }

  const token = getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return headers;
}

// ─── Token refresh (HIGH-03 FIX: Cookie-based) ──────────────────────────────

let refreshPromise: Promise<{ token: string | null; success: boolean }> | null =
  null;
let lastSuccessfulToken: string | null = null;
let lastRefreshTime: number = 0; // Timestamp of last successful refresh
const REFRESH_GRACE_PERIOD = 30000; // 30 seconds - don't refresh again within this window
let isRedirecting = false; // Prevent multiple simultaneous redirects

// Event system for auth state changes (allows Vue components to react)
type AuthEventType = "auth:logout" | "auth:token-refreshed";
type AuthEventCallback = (event: AuthEventType) => void;
const authEventListeners = new Set<AuthEventCallback>();

/**
 * Subscribe to auth state events.
 * Events: 'auth:logout' - session invalidated, should redirect to login
 *         'auth:token-refreshed' - token was successfully refreshed
 */
export function onAuthEvent(callback: AuthEventCallback): () => void {
  authEventListeners.add(callback);
  return () => authEventListeners.delete(callback);
}

function emitAuthEvent(event: AuthEventType): void {
  authEventListeners.forEach((callback) => {
    try {
      callback(event);
    } catch {
      // Ignore callback errors
    }
  });
}

/**
 * Redirect to login page. Uses event-based notification for Vue reactivity.
 * Ensures only one redirect happens even if multiple requests fail simultaneously.
 */
function redirectToLogin(): void {
  if (isRedirecting) return;
  isRedirecting = true;
  clearAccessToken();
  lastSuccessfulToken = null;
  lastRefreshTime = 0;

  // Emit event for Vue components to react (they can use Vue Router for navigation)
  emitAuthEvent("auth:logout");

  // Fallback: direct navigation after a small delay if event handlers didn't navigate
  if (typeof window !== "undefined") {
    setTimeout(() => {
      // Only navigate if we're still on a protected page
      if (!window.location.pathname.startsWith("/auth/")) {
        window.location.href = "/auth/login";
      }
    }, 100);
  }
}

/**
 * Refresh the access token using the refresh token from httpOnly cookie.
 *
 * HIGH-03 FIX: Uses the cookie-based refresh endpoint instead of sending
 * the refresh token in the request body. The cookie is automatically sent
 * by the browser and cannot be accessed by JavaScript.
 *
 * RACE CONDITION FIX: Multiple layers of protection:
 * 1. Promise deduplication: All concurrent requests share the SAME refresh promise
 * 2. Grace period: If we refreshed successfully within 30s, don't try again
 * 3. The refresh token is single-use (rotated), so we can only refresh once
 */
async function refreshAccessToken(): Promise<string | null> {
  const now = Date.now();

  // GRACE PERIOD CHECK: If we refreshed successfully within the grace period,
  // the current token should be valid. Don't try to refresh again.
  // This prevents "refresh token already used/blacklisted" errors.
  if (
    lastSuccessfulToken &&
    lastRefreshTime > 0 &&
    now - lastRefreshTime < REFRESH_GRACE_PERIOD
  ) {
    // Return the current token - it should still be valid
    return lastSuccessfulToken;
  }

  // If we have a recently acquired token that's still valid, use it
  if (lastSuccessfulToken && _accessToken === lastSuccessfulToken) {
    return lastSuccessfulToken;
  }

  // Deduplicate concurrent refresh calls - ALL requests share the same promise
  if (refreshPromise) {
    const result = await refreshPromise;
    return result.token;
  }

  // Create the shared promise that all concurrent requests will await
  refreshPromise = (async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/auth/token/refresh-cookie`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({}),
        },
      );

      if (!response.ok) {
        // Refresh failed - clear tokens
        _accessToken = null;
        lastSuccessfulToken = null;
        lastRefreshTime = 0;
        return { token: null, success: false };
      }

      const data = await response.json();
      if (data.access) {
        _accessToken = data.access;
        lastSuccessfulToken = data.access;
        lastRefreshTime = Date.now(); // Record successful refresh time
        // Reset redirect flag on successful refresh
        isRedirecting = false;
        // Notify listeners that token was refreshed
        emitAuthEvent("auth:token-refreshed");
        return { token: data.access, success: true };
      }

      _accessToken = null;
      lastSuccessfulToken = null;
      lastRefreshTime = 0;
      return { token: null, success: false };
    } catch {
      _accessToken = null;
      lastSuccessfulToken = null;
      lastRefreshTime = 0;
      return { token: null, success: false };
    }
  })();

  try {
    const result = await refreshPromise;
    return result.token;
  } finally {
    // Clear the promise AFTER all waiting requests have received their result
    // This ensures no new refresh attempts while requests are still waiting
    refreshPromise = null;
  }
}

// Track initialization state to handle race condition between
// module-load token refresh and component-mounted auth checks
let initPromise: Promise<void> | null = null;
let initComplete = false;

/**
 * Initialize access token on page load.
 *
 * HIGH-03 FIX: Called on module init to get a fresh access token
 * using the refresh token from the httpOnly cookie. This allows
 * the user to stay logged in across page reloads.
 */
async function initAccessToken(): Promise<void> {
  // Only run in browser
  if (typeof window === "undefined") return;

  // Try to get a new access token using the cookie-based refresh
  const token = await refreshAccessToken();
  if (token) {
    _accessToken = token;
  }
  initComplete = true;
}

/**
 * Wait for token initialization to complete.
 *
 * This is important because initAccessToken() runs on module load,
 * but components may try to check auth status before it completes.
 * This ensures auth checks wait for the initial token refresh.
 */
async function waitForInit(): Promise<void> {
  if (initPromise) await initPromise;
}

// Initialize access token on module load
// This uses the refresh token cookie to get a fresh access token
initPromise = initAccessToken().catch(() => {
  // Silently fail - user will need to log in again
  initComplete = true;
});

// ─── Main client ────────────────────────────────────────────────────────────

export const apiClient = {
  /**
   * GET request. Supports `params` for query string parameters.
   *
   * @example
   * apiClient.get("/billing/products/finance", { params: { currency: "BDT" } })
   */
  async get<T = unknown>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { method: "GET", ...options });
  },

  /**
   * POST request
   */
  async post<T = unknown>(
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<T> {
    return request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
      ...options,
    });
  },

  /**
   * PUT request
   */
  async put<T = unknown>(
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<T> {
    return request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
      ...options,
    });
  },

  /**
   * PATCH request
   */
  async patch<T = unknown>(
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<T> {
    return request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
      ...options,
    });
  },

  /**
   * DELETE request
   */
  async delete<T = unknown>(
    path: string,
    options?: RequestOptions,
  ): Promise<T> {
    return request<T>(path, { method: "DELETE", ...options });
  },

  /**
   * Upload files using multipart/form-data.
   * Do NOT set Content-Type — the browser auto-sets the boundary header.
   */
  async upload<T = unknown>(path: string, formData: FormData): Promise<T> {
    return request<T>(path, {
      method: "POST",
      body: formData,
      headers: { "Content-Type": "" }, // Override to let browser set multipart boundary
    });
  },

  /**
   * PUT with file upload using multipart/form-data.
   */
  async uploadPut<T = unknown>(path: string, formData: FormData): Promise<T> {
    return request<T>(path, {
      method: "PUT",
      body: formData,
      headers: { "Content-Type": "" }, // Override to let browser set multipart boundary
    });
  },
};

// ─── Core request handler ───────────────────────────────────────────────────

/**
 * Supported extra options beyond standard RequestInit.
 * These are extracted before passing to fetch() and applied separately.
 */
interface RequestOptions extends RequestInit {
  /** Query parameters to append to the URL. NOT a standard fetch option. */
  params?: Record<string, string | number | boolean>;
}

function buildUrl(
  path: string,
  params?: Record<string, string | number | boolean>,
): string {
  let url = `${API_BASE_URL}${path}`;
  if (params && Object.keys(params).length > 0) {
    const qs = new URLSearchParams();
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null && val !== "") {
        qs.append(key, String(val));
      }
    }
    const qsStr = qs.toString();
    if (qsStr) url += (url.includes("?") ? "&" : "?") + qsStr;
  }
  return url;
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  // HIGH-03 FIX: Wait for token initialization before making any request
  // This ensures the cookie-based token refresh has completed
  await waitForInit();

  const { params, ...restOptions } = options;
  const url = buildUrl(path, params);
  const headers = buildHeaders(
    restOptions.headers as Record<string, string> | undefined,
  );

  // Prevent browser/CDN from caching API responses — every request
  // must hit the server so currency conversions and auth state are fresh.
  // HIGH-03 FIX: Include credentials to send cookies with requests
  const fetchOptions: RequestInit = {
    ...restOptions,
    headers,
    cache: "no-store",
    credentials: "include", // Send cookies with requests (for httpOnly refresh token)
  };

  let response = await fetch(url, fetchOptions);

  // ── 401 → try token refresh ──
  // HIGH-03 FIX: Try cookie-based refresh when we get 401
  if (response.status === 401) {
    const now = Date.now();
    const inGracePeriod =
      lastRefreshTime > 0 && now - lastRefreshTime < REFRESH_GRACE_PERIOD;

    // GRACE PERIOD: If we just refreshed successfully, the token should be valid.
    // A 401 in this window means either:
    // 1. Permission denied (not an auth issue)
    // 2. The endpoint has special auth requirements
    // In either case, don't try to refresh again - just fail the request.
    if (inGracePeriod && lastSuccessfulToken) {
      // Don't trigger logout - just fail this request
      throw await createApiErrorFromResponse(response);
    }

    const newToken = await refreshAccessToken();

    if (newToken) {
      // Refresh succeeded - retry with new token
      const retryHeaders = buildHeaders(
        options.headers as Record<string, string> | undefined,
      );
      retryHeaders["Authorization"] = `Bearer ${newToken}`;
      response = await fetch(url, { ...fetchOptions, headers: retryHeaders });

      // If retry still fails with 401, the token might be invalid for this endpoint
      // or there's a backend issue - let it fall through to error handling
    } else {
      // Refresh failed - session is invalid, redirect to login
      redirectToLogin();
      throw createApiError(response, "Session expired. Please sign in again.");
    }
  }

  // ── Non-OK response → throw ──
  if (!response.ok) {
    throw await createApiErrorFromResponse(response);
  }

  // ── 204 No Content ──
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// ─── Error factory ──────────────────────────────────────────────────────────

async function createApiErrorFromResponse(
  response: Response,
): Promise<ApiError> {
  let message = `Request failed with status ${response.status}`;

  try {
    const body = await response.json();
    if (typeof body === "object" && body !== null) {
      // Django Ninja typically returns { detail: "..." } or { message: "..." } or { non_field_errors: [...] }
      if (body.detail) message = body.detail;
      else if (body.message) message = body.message;
      else if (body.non_field_errors?.[0]) message = body.non_field_errors[0];

      // Handle validation error format: { detail: "...", errors: [{ field, message }], code: "validation_error" }
      if (
        body.code === "validation_error" &&
        Array.isArray(body.errors) &&
        body.errors.length > 0
      ) {
        const firstError = body.errors[0];
        if (firstError.message) {
          // Build user-friendly message from field name
          const fieldLabel = (firstError.field || "")
            .replace(/payload\.\s*/g, "") // Remove "payload." prefix
            .replace(/body\.\s*/g, "") // Remove "body." prefix
            .replace(/_/g, " ") // snake_case → space
            .replace(/\b\w/g, (c: string) => c.toUpperCase()); // Capitalize
          message = fieldLabel
            ? `${fieldLabel}: ${firstError.message}`
            : firstError.message;
        }
      }

      // Field-level errors (dict format)
      const fieldErrors: Record<string, string[]> = {};
      for (const [key, value] of Object.entries(body)) {
        if (
          key !== "detail" &&
          key !== "message" &&
          key !== "non_field_errors" &&
          key !== "code" &&
          key !== "errors"
        ) {
          if (Array.isArray(value)) {
            fieldErrors[key] = value.map(String);
          } else if (typeof value === "string") {
            fieldErrors[key] = [value];
          }
        }
      }
      if (Object.keys(fieldErrors).length > 0) {
        return { status: response.status, message, errors: fieldErrors };
      }
    }
  } catch {
    // Body wasn't JSON — use default message
  }

  return createApiError(response, message);
}

function createApiError(response: Response, message: string): ApiError {
  return { status: response.status, message };
}

// ─── Media URL helper ─────────────────────────────────────────────────────

/**
 * Convert a relative media path (e.g. "/media/avatars/...") to a full URL
 * pointing at the backend server. Returns null if path is falsy.
 *
 * Example:
 *   getMediaUrl("/media/avatars/2026/04/photo.jpg")
 *   → "https://xxx.ngrok-free.dev/media/avatars/2026/04/photo.jpg"
 */
export function getMediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  // Already an absolute URL (http/https) — return as-is
  if (/^https?:\/\//i.test(path)) return path;
  // Strip "/api/v1" from API_BASE_URL to get the backend origin
  const origin = API_BASE_URL.replace(/\/api\/v\d+\/?$/, "");
  // Ensure path starts with "/"
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${origin}${normalized}`;
}

// ─── Auth helpers ───────────────────────────────────────────────────────────

/**
 * Auth helper functions for managing authentication state.
 *
 * HIGH-03 FIX: Updated for cookie-based auth:
 * - setAccessToken: Sets access token in memory only
 * - clearAuth: Clears access token from memory (logout clears cookie via API)
 * - getAccessToken: Gets access token from memory
 * - isAuthenticated: Checks if access token exists
 */
export const authHelpers = {
  /**
   * Set the access token after login.
   * HIGH-03 FIX: Only sets access token - refresh token is in httpOnly cookie.
   * Also resets redirect flag and tracks the successful token.
   * Sets the refresh grace period timer.
   */
  setAccessToken: (token: string): void => {
    setAccessToken(token);
    lastSuccessfulToken = token;
    lastRefreshTime = Date.now(); // Set grace period start time
    isRedirecting = false; // Reset redirect flag on successful login
  },

  /**
   * Clear authentication state.
   * HIGH-03 FIX: Clears access token from memory.
   * Note: The httpOnly cookie is cleared by calling the /auth/logout endpoint.
   */
  clearAuth: (): void => {
    clearAccessToken();
    lastSuccessfulToken = null;
    lastRefreshTime = 0;
  },

  /**
   * Get the current access token.
   */
  getAccessToken,

  /**
   * Check if the user is authenticated.
   */
  isAuthenticated,

  /**
   * Wait for token initialization to complete.
   * Call this before checking isAuthenticated() to avoid race conditions.
   */
  waitForInit,

  /**
   * @deprecated Use setAccessToken instead. The refresh token is now handled via httpOnly cookie.
   */
  setTokens: (access: string, _refresh: string, _remember = false): void => {
    setAccessToken(access);
    lastSuccessfulToken = access;
    lastRefreshTime = Date.now();
    isRedirecting = false;
  },

  /**
   * @deprecated Use clearAuth instead.
   */
  clearTokens: (): void => {
    clearAccessToken();
    lastSuccessfulToken = null;
    lastRefreshTime = 0;
  },

  /**
   * @deprecated Refresh token is no longer accessible - it's in an httpOnly cookie.
   */
  getRefreshToken: (): null => {
    return null;
  },
};
