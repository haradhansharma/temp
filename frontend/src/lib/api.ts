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
 * Tokens are stored securely using a hybrid approach:
 *
 * - Access Token: Memory + window object (survives module re-evaluation)
 * - Refresh Token: httpOnly cookie (set by backend, not accessible to JS)
 * - "Remember Me": Controlled by cookie expiration on backend
 *
 * AUTH FLOW (SIMPLIFIED + PROACTIVE REFRESH):
 * ============================================
 * 1. On page load, try to get an access token via cookie-refresh (once only)
 * 2. Decode the JWT to extract the expiry time (exp claim)
 * 3. Schedule a proactive refresh BEFORE the access token expires
 * 4. For every API request, just make the request with whatever token we have
 * 5. If we get a 401, try to refresh the token and retry once
 * 6. If refresh fails, redirect to login
 * 7. Public endpoints (login, register, etc.) work without any token
 *
 * SESSION PERSISTENCE + FIRST-CLICK FIX:
 * =======================================
 * The backend now ROTATES the refresh token on every cookie-based refresh,
 * issuing a new refresh token with a fresh 7-day expiry. This means:
 * - "Remember Me" works correctly: cookie persists 30 days, JWT gets refreshed
 * - Active users never get logged out (session extends with each refresh)
 * - Without "Remember Me", session ends when the browser closes (session cookie)
 *
 * FIRST-CLICK FIX:
 * - When proactive refresh fails, redirect IMMEDIATELY (no silent failure)
 * - isRedirecting flag is cleared with a safety timeout (never blocks forever)
 * - isLoggedIn in useAuth checks BOTH user data AND access token
 * - SessionGuard reacts immediately to session-expired events
 *
 * Key principles:
 * - Proactive refresh eliminates the 401→refresh→retry delay
 * - Promise deduplication prevents concurrent refresh calls
 * - Throttle prevents rapid successive refreshes
 * - JWT expiry tracking enables accurate session monitoring
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

// ─── JWT Decoding (lightweight, no library needed) ───────────────────────────
//
// We decode the JWT payload to extract the `exp` (expiry) claim.
// This is safe to do client-side — JWTs are Base64-encoded, not encrypted.
// We do NOT validate the signature client-side (the backend does that).

interface JWTPayload {
  exp?: number; // Unix timestamp when the token expires
  iat?: number; // Unix timestamp when the token was issued
  user_id?: number;
  [key: string]: unknown;
}

function decodeJWTPayload(token: string): JWTPayload | null {
  try {
    // JWT format: header.payload.signature
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // Decode the payload (middle part) from Base64URL
    const payload = parts[1];
    // Base64URL → Base64
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    // Decode and parse JSON
    const json = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join(""),
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/**
 * Get the expiry time (in milliseconds since epoch) from an access token.
 * Returns null if the token cannot be decoded or has no exp claim.
 */
function getTokenExpiry(token: string): number | null {
  const payload = decodeJWTPayload(token);
  if (payload?.exp) {
    return payload.exp * 1000; // Convert seconds → milliseconds
  }
  return null;
}

/**
 * Check if an access token is expired or about to expire.
 * @param token - The JWT access token
 * @param bufferMs - How many milliseconds before actual expiry to consider it expired
 * @returns true if the token is expired or will expire within bufferMs
 */
function isTokenExpiringSoon(
  token: string,
  bufferMs: number = 5 * 60 * 1000,
): boolean {
  const expiry = getTokenExpiry(token);
  if (!expiry) return true; // Can't decode → treat as expired
  return Date.now() + bufferMs >= expiry;
}

// ─── Shared Auth State (survives module re-evaluation) ───────────────────────
//
// When Astro View Transitions swap page content, or HMR re-evaluates the
// module, module-level variables are reset. By storing auth state on the
// `window` object, we ensure the access token and refresh deduplication
// persist across module re-evaluations.

const SHARED_AUTH_KEY = "__sb_auth";

interface SharedAuthState {
  accessToken: string | null;
  accessTokenExpiry: number | null; // Timestamp (ms) when the access token expires
  lastRefreshTime: number;
  isRedirecting: boolean;
  refreshPromise: Promise<string | null> | null;
  initPromise: Promise<void> | null;
  initComplete: boolean;
  lastRefreshFailedTime: number;
  proactiveRefreshTimer: ReturnType<typeof setTimeout> | null;
  redirectTimeout: ReturnType<typeof setTimeout> | null; // Safety timeout for isRedirecting
}

function getSharedAuth(): SharedAuthState {
  if (typeof window === "undefined") {
    // SSR fallback — create a temporary state that won't persist
    return {
      accessToken: null,
      accessTokenExpiry: null,
      lastRefreshTime: 0,
      isRedirecting: false,
      refreshPromise: null,
      initPromise: null,
      initComplete: false,
      lastRefreshFailedTime: 0,
      proactiveRefreshTimer: null,
      redirectTimeout: null,
    };
  }
  const win = window as any;
  if (!win[SHARED_AUTH_KEY]) {
    win[SHARED_AUTH_KEY] = {
      accessToken: null,
      accessTokenExpiry: null,
      lastRefreshTime: 0,
      isRedirecting: false,
      refreshPromise: null,
      initPromise: null,
      initComplete: false,
      lastRefreshFailedTime: 0,
      proactiveRefreshTimer: null,
      redirectTimeout: null,
    };
  }
  return win[SHARED_AUTH_KEY];
}

// ─── Token Management ────────────────────────────────────────────────────────

// Module-level convenience reference (synced from shared state)
let _accessToken: string | null = null;

/**
 * Get the current access token.
 * Checks module memory first, then falls back to the shared window state.
 */
function getAccessToken(): string | null {
  if (_accessToken) return _accessToken;
  const shared = getSharedAuth();
  if (shared.accessToken) {
    _accessToken = shared.accessToken;
    return _accessToken;
  }
  return null;
}

/**
 * Set the access token in both module memory and shared window state.
 * Also decodes the JWT to track the expiry time and schedules a proactive refresh.
 */
function setAccessToken(token: string | null): void {
  _accessToken = token;
  const shared = getSharedAuth();
  shared.accessToken = token;

  if (token) {
    const expiry = getTokenExpiry(token);
    shared.accessTokenExpiry = expiry;
    // Schedule a proactive refresh before the token expires
    scheduleProactiveRefresh(expiry);
  } else {
    shared.accessTokenExpiry = null;
    clearProactiveRefreshTimer();
  }
}

/**
 * Check if we have an access token (user is authenticated).
 */
function isAuthenticated(): boolean {
  return !!getAccessToken();
}

/**
 * Clear the access token from both module memory and shared state.
 */
function clearAccessToken(): void {
  _accessToken = null;
  const shared = getSharedAuth();
  shared.accessToken = null;
  shared.accessTokenExpiry = null;
  clearProactiveRefreshTimer();
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

// ─── Proactive Token Refresh ─────────────────────────────────────────────────
//
// Instead of waiting for a 401 to trigger a refresh, we schedule a refresh
// BEFORE the access token expires. This eliminates the 401→refresh→retry
// delay and provides a smoother user experience.
//
// FIRST-CLICK FIX: When the proactive refresh FAILS, we immediately redirect
// to login instead of silently failing. This prevents the "first click doesn't
// work" problem where the user's click triggers a 401→refresh→fail cycle.

// How many minutes before token expiry to trigger a proactive refresh
const PROACTIVE_REFRESH_BUFFER_MINUTES = 5;

// Minimum time between proactive refresh attempts (prevents rapid refreshes)
const PROACTIVE_REFRESH_MIN_INTERVAL_MS = 60_000; // 1 minute

function clearProactiveRefreshTimer(): void {
  const shared = getSharedAuth();
  if (shared.proactiveRefreshTimer) {
    clearTimeout(shared.proactiveRefreshTimer);
    shared.proactiveRefreshTimer = null;
  }
}

/**
 * Handle proactive refresh failure — redirect immediately if on a protected page.
 * This is the FIRST-CLICK FIX: instead of silently failing, we redirect.
 */
function handleProactiveRefreshFailure(): void {
  if (typeof window === "undefined") return;
  // Only redirect if we're on a protected page (not already on auth page)
  if (window.location.pathname.startsWith("/auth/")) return;

  // If we have no access token, the session is dead — redirect now
  if (!getAccessToken()) {
    redirectToLogin("session-expired");
  }
}

/**
 * Schedule a proactive refresh before the access token expires.
 * @param expiryMs - The token's expiry time in milliseconds since epoch
 */
function scheduleProactiveRefresh(expiryMs: number | null): void {
  clearProactiveRefreshTimer();

  if (!expiryMs) return;

  const now = Date.now();
  const refreshAt = expiryMs - PROACTIVE_REFRESH_BUFFER_MINUTES * 60 * 1000;
  const delay = refreshAt - now;

  if (delay <= 0) {
    // Token is already about to expire — refresh immediately
    // But respect the throttle — don't refresh more than once per minute
    const shared = getSharedAuth();
    if (
      shared.lastRefreshTime &&
      Date.now() - shared.lastRefreshTime < PROACTIVE_REFRESH_MIN_INTERVAL_MS
    ) {
      // Refreshed very recently — schedule for when the minimum interval passes
      const remainingDelay =
        PROACTIVE_REFRESH_MIN_INTERVAL_MS -
        (Date.now() - shared.lastRefreshTime);
      shared.proactiveRefreshTimer = setTimeout(() => {
        shared.proactiveRefreshTimer = null;
        refreshAccessToken()
          .then((token) => {
            if (!token) handleProactiveRefreshFailure();
          })
          .catch(() => handleProactiveRefreshFailure());
      }, remainingDelay);
      return;
    }

    // No recent refresh — do it now
    refreshAccessToken()
      .then((token) => {
        if (!token) handleProactiveRefreshFailure();
      })
      .catch(() => handleProactiveRefreshFailure());
    return;
  }

  // Schedule the refresh for later
  const shared = getSharedAuth();
  shared.proactiveRefreshTimer = setTimeout(() => {
    shared.proactiveRefreshTimer = null;
    refreshAccessToken()
      .then((token) => {
        if (!token) handleProactiveRefreshFailure();
      })
      .catch(() => handleProactiveRefreshFailure());
  }, delay);
}

// ─── Token refresh ───────────────────────────────────────────────────────────

// Minimum time between refresh calls (in milliseconds).
// The access token has a 60-minute lifetime, so refreshing more often than
// every 30 seconds is unnecessary.
const REFRESH_THROTTLE_MS = 30_000;

// Cooldown after a failed refresh to prevent hammering the server.
// If refresh failed recently, don't try again for 10 seconds.
const REFRESH_COOLDOWN_MS = 10_000;

// Event system for auth state changes (allows Vue components to react)
//
// VIEW TRANSITION FIX: authEventListeners is stored on window so it survives
// module re-evaluation. Previously, it was a module-level Set that got
// re-created as empty on every View Transition, causing all registered
// listeners to be lost. Now, both the Set and the _listenersRegistered guard
// are on the same window-level state, so they stay consistent.
type AuthEventType =
  | "auth:logout"
  | "auth:token-refreshed"
  | "auth:session-expired";
type AuthEventCallback = (event: AuthEventType) => void;

const AUTH_LISTENERS_KEY = "__sb_auth_listeners";

function getAuthListeners(): Set<AuthEventCallback> {
  if (typeof window === "undefined") return new Set<AuthEventCallback>();
  const win = window as any;
  if (!win[AUTH_LISTENERS_KEY]) {
    win[AUTH_LISTENERS_KEY] = new Set<AuthEventCallback>();
  }
  return win[AUTH_LISTENERS_KEY];
}

/**
 * Subscribe to auth state events.
 * Events: 'auth:logout' - session invalidated, should redirect to login
 *         'auth:token-refreshed' - token was successfully refreshed
 *         'auth:session-expired' - refresh token expired, session is truly over
 */
export function onAuthEvent(callback: AuthEventCallback): () => void {
  const listeners = getAuthListeners();
  listeners.add(callback);
  return () => listeners.delete(callback);
}

function emitAuthEvent(event: AuthEventType): void {
  const listeners = getAuthListeners();
  listeners.forEach((callback) => {
    try {
      callback(event);
    } catch {
      // Ignore callback errors
    }
  });

  // BACKUP: Also dispatch a window CustomEvent so that any component
  // (even from a different module context after a View Transition)
  // can listen for it. This is a safety net in case the Set-based
  // listeners are lost during module re-evaluation.
  if (typeof window !== "undefined") {
    try {
      window.dispatchEvent(
        new CustomEvent(`sb:${event}`, { detail: { event } }),
      );
    } catch {
      // Ignore dispatch errors
    }
  }
}

// ─── Astro Navigation (Vue 3 Convention) ─────────────────────────────────────
//
// VUE 3 CONVENTION: api.ts NEVER navigates directly. It only emits events
// and updates auth state. All navigation is handled by Vue components
// (SessionGuard.vue) which use Astro's navigate() from 'astro:transitions'.
//
// This avoids the "querySelector null" error that occurs when
// window.location.replace() is called during an active View Transition,
// or when navigate() is called synchronously during a transition lifecycle
// event (astro:before-preparation), which creates a race condition with
// Astro's router.
//
// The key principle: api.ts is the "store" (state + events), and
// SessionGuard.vue is the "router guard" (navigation). This separation
// ensures navigation only happens when it's safe — after the current
// transition lifecycle event has completed.

type AstroNavigateFn = (
  path: string,
  options?: Record<string, unknown>,
) => void | Promise<void>;

const ASTRO_NAVIGATE_KEY = "__sb_astro_navigate";

/**
 * Register Astro's navigate() function for use by SessionGuard.vue.
 * Called from BaseLayout.astro (non-inline script) and also from
 * SessionGuard.vue's onMounted() as a safety net.
 *
 * VUE 3 CONVENTION: In Vue 3, you'd call router.push() to navigate.
 * Here, we register Astro's equivalent (navigate from 'astro:transitions')
 * so that Vue components can use it without directly importing the virtual
 * module from composable code.
 */
export function registerNavigate(fn: AstroNavigateFn): void {
  if (typeof window === "undefined") return;
  (window as any)[ASTRO_NAVIGATE_KEY] = fn;
}

/**
 * Navigate to a path using Astro's router (Vue 3 convention).
 *
 * IMPORTANT: This function should ONLY be called from Vue components
 * (SessionGuard.vue), never from api.ts directly. It uses Astro's
 * navigate() which properly integrates with the View Transition system
 * and never causes the "querySelector null" error.
 *
 * Callers MUST wrap this in setTimeout(0) to avoid race conditions
 * with Astro's transition lifecycle events.
 */
function navigateTo(path: string): void {
  if (typeof window === "undefined") return;

  // Use Astro's navigate() — the Vue 3 convention way
  const astroNav = (window as any)[ASTRO_NAVIGATE_KEY] as
    | AstroNavigateFn
    | undefined;
  if (astroNav) {
    astroNav(path, { history: "replace" });
    return;
  }

  // Fallback: If navigate() is not registered yet (shouldn't happen
  // since we register it in BaseLayout.astro), queue the redirect.
  // SessionGuard.vue checks for queued redirects on astro:page-load.
  (window as any).__sb_pending_redirect = path;
}

/**
 * Redirect to login page — EMIT-ONLY (Vue 3 Convention).
 *
 * VUE 3 CONVENTION: This function updates auth state and emits events so
 * Vue components (SessionGuard.vue) can react and navigate. It does NOT
 * call navigateTo() or window.location.replace() directly. This ensures
 * navigation only happens from Vue components using Astro's navigate(),
 * which properly integrates with the View Transition system.
 *
 * Flow:
 * 1. Clear tokens and update shared state
 * 2. Emit events so Vue components react immediately
 * 3. Set a window-level flag so SessionGuard knows to redirect
 * 4. SessionGuard picks up the event/flag and navigates using navigate()
 */
function redirectToLogin(
  reason: "session-expired" | "auth-failed" = "auth-failed",
): void {
  const shared = getSharedAuth();

  if (shared.isRedirecting) {
    // Already redirecting — don't start a second redirect
    return;
  }

  shared.isRedirecting = true;

  // Safety timeout: clear isRedirecting after 3 seconds in case the
  // redirect fails for any reason.
  if (shared.redirectTimeout) clearTimeout(shared.redirectTimeout);
  shared.redirectTimeout = setTimeout(() => {
    const s = getSharedAuth();
    s.isRedirecting = false;
    s.redirectTimeout = null;
  }, 3000);

  // IMPORTANT: Emit events so Vue components can react immediately.
  // SessionGuard.vue listens for these events and handles the navigation.
  clearAccessToken();
  shared.lastRefreshTime = 0;
  shared.lastRefreshFailedTime = 0;

  // Set a window-level redirect flag for SessionGuard to pick up.
  // This is a safety net in case event listeners are lost during View Transitions.
  if (typeof window !== "undefined") {
    (window as any).__sb_redirect_reason = reason;
  }

  // Emit events for Vue components to react and navigate
  if (reason === "session-expired") {
    emitAuthEvent("auth:session-expired");
  }
  emitAuthEvent("auth:logout");
}

/**
 * Refresh the access token using the refresh token from httpOnly cookie.
 *
 * SIMPLE APPROACH:
 * - All concurrent callers share the SAME promise (deduplication via window)
 * - Throttle prevents refreshing more than once per 30 seconds
 * - Cooldown prevents retrying after a recent failure for 10 seconds
 * - On failure, check if another concurrent refresh succeeded before clearing
 * - On success, decode the new token and schedule proactive refresh
 */
async function refreshAccessToken(): Promise<string | null> {
  const shared = getSharedAuth();

  // Throttle: if we refreshed very recently, return the current token.
  if (
    shared.accessToken &&
    shared.lastRefreshTime &&
    Date.now() - shared.lastRefreshTime < REFRESH_THROTTLE_MS
  ) {
    _accessToken = shared.accessToken;
    return _accessToken;
  }

  // Cooldown: if refresh failed recently, don't try again yet.
  // FIRST-CLICK FIX: If we're in cooldown AND have no token, return null
  // immediately so the caller (401 handler) can redirect. Previously this
  // returned shared.accessToken which was null, but the caller might not
  // have handled it correctly.
  if (
    shared.lastRefreshFailedTime &&
    Date.now() - shared.lastRefreshFailedTime < REFRESH_COOLDOWN_MS
  ) {
    return shared.accessToken; // Return whatever we have (could be null)
  }

  // Deduplicate: if a refresh is already in-flight, join it.
  if (shared.refreshPromise) {
    return shared.refreshPromise;
  }

  // Start a new refresh — the promise is shared on window so ALL concurrent
  // callers (from any module instance / VM context) join the same refresh.
  shared.refreshPromise = (async () => {
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
        // Before clearing everything, check if another refresh already
        // set a valid token while ours was in-flight.
        const current = getSharedAuth();
        if (current.accessToken && current.lastRefreshTime) {
          _accessToken = current.accessToken;
          return current.accessToken;
        }

        // Truly failed — no valid token.
        // If 401, the refresh token itself is expired or invalid.
        // This means the session is truly over (not just the access token).
        _accessToken = null;
        shared.accessToken = null;
        shared.accessTokenExpiry = null;
        shared.lastRefreshTime = 0;
        shared.lastRefreshFailedTime = Date.now();
        return null;
      }

      const data = await response.json();
      if (data.access) {
        _accessToken = data.access;
        shared.accessToken = data.access;
        shared.lastRefreshTime = Date.now();
        shared.lastRefreshFailedTime = 0;
        shared.isRedirecting = false;

        // Clear any pending redirect timeout
        if (shared.redirectTimeout) {
          clearTimeout(shared.redirectTimeout);
          shared.redirectTimeout = null;
        }

        // Decode JWT to track expiry and schedule proactive refresh
        const expiry = getTokenExpiry(data.access);
        shared.accessTokenExpiry = expiry;
        scheduleProactiveRefresh(expiry);

        emitAuthEvent("auth:token-refreshed");
        return data.access;
      }

      // No access token in response
      _accessToken = null;
      shared.accessToken = null;
      shared.accessTokenExpiry = null;
      shared.lastRefreshTime = 0;
      shared.lastRefreshFailedTime = Date.now();
      return null;
    } catch {
      // Network error — check if another refresh succeeded
      const current = getSharedAuth();
      if (current.accessToken && current.lastRefreshTime) {
        _accessToken = current.accessToken;
        return current.accessToken;
      }

      _accessToken = null;
      shared.accessToken = null;
      shared.accessTokenExpiry = null;
      shared.lastRefreshTime = 0;
      shared.lastRefreshFailedTime = Date.now();
      return null;
    }
  })();

  try {
    return await shared.refreshPromise;
  } finally {
    // Keep the promise for a grace period so late-arriving callers
    // join the SAME refresh instead of starting a new one.
    setTimeout(() => {
      const s = getSharedAuth();
      if (s.refreshPromise === shared.refreshPromise) {
        s.refreshPromise = null;
      }
    }, 2000);
  }
}

// ─── Initialization ──────────────────────────────────────────────────────────

/**
 * Check if the current page is an auth page where the user is not
 * expected to be logged in.
 */
function isAuthPage(): boolean {
  if (typeof window === "undefined") return false;
  const path = window.location.pathname;
  return (
    path.startsWith("/auth/login") ||
    path.startsWith("/auth/register") ||
    path.startsWith("/auth/forgot-password") ||
    path.startsWith("/auth/reset-password") ||
    path.startsWith("/auth/verify-email") ||
    path.startsWith("/auth/callback") ||
    path === "/auth" ||
    path === "/"
  );
}

/**
 * Initialize access token on page load.
 *
 * This runs ONCE per page load. On subsequent module re-evaluations
 * (Astro View Transitions), the shared state is checked and the
 * existing token is reused — no additional refresh is triggered.
 */
async function initAccessToken(): Promise<void> {
  if (typeof window === "undefined") return;

  const shared = getSharedAuth();

  // If init was already completed by another module instance, just sync token
  if (shared.initComplete) {
    if (shared.accessToken) {
      _accessToken = shared.accessToken;
      // Re-schedule proactive refresh if we have an expiry time
      if (shared.accessTokenExpiry) {
        scheduleProactiveRefresh(shared.accessTokenExpiry);
      }
    }
    return;
  }

  // Skip refresh on auth pages — no cookie expected
  if (isAuthPage()) {
    shared.initComplete = true;
    return;
  }

  // If we already have an access token from a previous evaluation, use it
  if (shared.accessToken) {
    _accessToken = shared.accessToken;
    shared.initComplete = true;
    // Re-schedule proactive refresh if we have an expiry time
    if (shared.accessTokenExpiry) {
      scheduleProactiveRefresh(shared.accessTokenExpiry);
    }
    return;
  }

  // No token — try to get one using the cookie-based refresh (once only)
  const token = await refreshAccessToken();
  if (token) {
    _accessToken = token;
  } else {
    // FIRST-CLICK FIX: If the initial refresh fails on a protected page,
    // redirect immediately. Don't leave the user on a page with no token
    // where their first click will "not work."
    if (
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/auth/")
    ) {
      redirectToLogin("session-expired");
    }
  }
  shared.initComplete = true;
}

/**
 * Wait for token initialization to complete.
 */
async function waitForInit(): Promise<void> {
  const shared = getSharedAuth();
  if (shared.initPromise) await shared.initPromise;
}

// Initialize access token on module load.
// IMPORTANT: Only run init ONCE per session (not per module re-evaluation).
// Astro View Transitions re-evaluate this module, but the shared state on
// window.__sb_auth persists. We check it to avoid redundant refresh calls.
const sharedAuth = getSharedAuth();
if (!sharedAuth.initComplete && !sharedAuth.initPromise) {
  sharedAuth.initPromise = initAccessToken().catch(() => {
    const shared = getSharedAuth();
    shared.initComplete = true;
  });
} else {
  // Module re-evaluated (View Transition / HMR) — just sync the token.
  if (sharedAuth.accessToken) {
    _accessToken = sharedAuth.accessToken;
    // Re-schedule proactive refresh
    if (sharedAuth.accessTokenExpiry) {
      scheduleProactiveRefresh(sharedAuth.accessTokenExpiry);
    }
  }
}

// ─── Astro View Transition handling ──────────────────────────────────────────
//
// VUE 3 CONVENTION: api.ts NEVER calls navigateTo() or window.location.replace()
// during a transition lifecycle event. Instead, it only emits events and sets
// flags. SessionGuard.vue picks up these events and handles the navigation
// using Astro's navigate() from 'astro:transitions', properly deferred with
// setTimeout to avoid race conditions.
//
// The "querySelector null" error was caused by calling navigate() or
// window.location.replace() synchronously inside astro:before-preparation.
// This created a race condition with Astro's router. Now, we simply cancel
// the transition and emit events — SessionGuard handles the rest.
//
// Transition lifecycle:
// - astro:before-preparation: Transition is starting → if session expired,
//   cancel transition + emit events (no navigation here!)
// - astro:page-load: Page is fully loaded → sync auth state, check for
//   pending redirects

if (typeof window !== "undefined") {
  // ── astro:before-preparation ──
  //
  // VUE 3 CONVENTION: If the session is expired, cancel this transition
  // and emit events. SessionGuard.vue will handle the redirect.
  // We do NOT call navigateTo() here because:
  // 1. navigate() from astro:transitions called during before-preparation
  //    creates a race condition with the current transition
  // 2. window.location.replace() during a transition causes the
  //    "querySelector null" error in Astro's router
  // Instead, we cancel the transition and let the Vue component handle it.
  document.addEventListener("astro:before-preparation", (e: any) => {
    const shared = getSharedAuth();
    const isOnProtectedPage = !window.location.pathname.startsWith("/auth/");

    if (!shared.accessToken && isOnProtectedPage) {
      // Cancel the transition — the user's session is expired, they
      // shouldn't navigate to another protected page
      e.preventDefault();

      // Update state and emit events — SessionGuard will redirect
      clearAccessToken();
      emitAuthEvent("auth:session-expired");
      emitAuthEvent("auth:logout");

      // Set a redirect flag so SessionGuard knows to navigate
      (window as any).__sb_redirect_reason = "session-expired";
      return;
    }
  });

  // ── astro:page-load ──
  //
  // Fires after every page navigation (initial load + View Transitions).
  // Sync auth state and check for pending redirects from SessionGuard.
  document.addEventListener("astro:page-load", () => {
    const shared = getSharedAuth();

    // Always reset isRedirecting on page load.
    shared.isRedirecting = false;
    if (shared.redirectTimeout) {
      clearTimeout(shared.redirectTimeout);
      shared.redirectTimeout = null;
    }

    // Always sync token from shared state (handles new module contexts)
    if (shared.accessToken) {
      _accessToken = shared.accessToken;
    }
    shared.initComplete = true;

    // Re-schedule proactive refresh on page navigation
    if (shared.accessTokenExpiry) {
      scheduleProactiveRefresh(shared.accessTokenExpiry);
    }
  });
}

// ─── Session Info (for Vue components to display session state) ───────────────

/**
 * Get information about the current session.
 * Used by Vue components to show session timers, warnings, etc.
 */
export function getSessionInfo(): {
  isAuthenticated: boolean;
  accessTokenExpiry: Date | null;
  sessionExpiresAt: Date | null;
  timeUntilExpiry: number | null; // milliseconds
  isRememberMe: boolean;
} {
  const shared = getSharedAuth();
  const token = shared.accessToken;
  const expiry = shared.accessTokenExpiry;

  // Check if "Remember Me" cookie is set
  let isRememberMe = false;
  if (typeof document !== "undefined") {
    isRememberMe = document.cookie
      .split("; ")
      .some((row) => row.startsWith("sb_remember_me=true"));
  }

  if (!token || !expiry) {
    return {
      isAuthenticated: false,
      accessTokenExpiry: null,
      sessionExpiresAt: null,
      timeUntilExpiry: null,
      isRememberMe,
    };
  }

  const timeUntilExpiry = expiry - Date.now();

  return {
    isAuthenticated: true,
    accessTokenExpiry: new Date(expiry),
    sessionExpiresAt: new Date(expiry),
    timeUntilExpiry: Math.max(0, timeUntilExpiry),
    isRememberMe,
  };
}

// ─── Main client ─────────────────────────────────────────────────────────────

export const apiClient = {
  async get<T = unknown>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { method: "GET", ...options });
  },

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

  async delete<T = unknown>(
    path: string,
    options?: RequestOptions,
  ): Promise<T> {
    return request<T>(path, { method: "DELETE", ...options });
  },

  async upload<T = unknown>(path: string, formData: FormData): Promise<T> {
    return request<T>(path, {
      method: "POST",
      body: formData,
      headers: { "Content-Type": "" },
    });
  },

  async uploadPut<T = unknown>(path: string, formData: FormData): Promise<T> {
    return request<T>(path, {
      method: "PUT",
      body: formData,
      headers: { "Content-Type": "" },
    });
  },
};

// ─── Core request handler ────────────────────────────────────────────────────

interface RequestOptions extends RequestInit {
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
  // Wait for token initialization before making any request
  await waitForInit();

  const { params, ...restOptions } = options;
  const url = buildUrl(path, params);

  // ─── PROACTIVE REFRESH ───
  //
  // Before making any request, check if the access token is about to expire.
  // If it is, proactively refresh it first. This eliminates the
  // 401→refresh→retry delay for most requests.
  const currentToken = getAccessToken();
  if (currentToken && isTokenExpiringSoon(currentToken)) {
    // Wait for the refresh to complete before making the request.
    // FIRST-CLICK FIX: Previously this was fire-and-forget, which meant
    // the request could go out with an expired token, get a 401, and the
    // first click would be "eaten" by the error handling.
    const newToken = await refreshAccessToken();
    if (!newToken) {
      // Refresh failed — session is dead. The 401 handler below will redirect.
      // Don't bother making the request — it will fail anyway.
      const isPublicEndpoint =
        path.startsWith("/auth/login") ||
        path.startsWith("/auth/register") ||
        path.startsWith("/auth/choices") ||
        path.startsWith("/auth/password-reset") ||
        path.startsWith("/auth/verify-email");

      if (!isPublicEndpoint) {
        redirectToLogin("session-expired");
        throw createApiError(
          { status: 401 } as Response,
          "Session expired. Please sign in again.",
        );
      }
    }
  }

  const headers = buildHeaders(
    restOptions.headers as Record<string, string> | undefined,
  );

  const fetchOptions: RequestInit = {
    ...restOptions,
    headers,
    cache: "no-store",
    credentials: "include",
  };

  let response = await fetch(url, fetchOptions);

  // ── 401 → try token refresh and retry ONCE ──
  if (response.status === 401) {
    const newToken = await refreshAccessToken();

    if (newToken) {
      // Refresh succeeded - retry with new token
      const retryHeaders = buildHeaders(
        options.headers as Record<string, string> | undefined,
      );
      retryHeaders["Authorization"] = `Bearer ${newToken}`;
      response = await fetch(url, { ...fetchOptions, headers: retryHeaders });

      // If retry STILL fails with 401 after a successful refresh,
      // this is a permission issue (not an auth issue) — don't redirect.
      // The error falls through to the generic non-OK handler below.
    } else {
      // Refresh failed - the refresh token (httpOnly cookie) is also expired/invalid.
      // This means the session is truly over.
      // BUT: only redirect if this is NOT a public endpoint.
      const isPublicEndpoint =
        path.startsWith("/auth/login") ||
        path.startsWith("/auth/register") ||
        path.startsWith("/auth/choices") ||
        path.startsWith("/auth/password-reset") ||
        path.startsWith("/auth/verify-email");

      if (!isPublicEndpoint) {
        redirectToLogin("session-expired");
      }
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

// ─── Error factory ───────────────────────────────────────────────────────────

async function createApiErrorFromResponse(
  response: Response,
): Promise<ApiError> {
  let message = `Request failed with status ${response.status}`;

  try {
    const body = await response.json();
    if (typeof body === "object" && body !== null) {
      if (body.detail) message = body.detail;
      else if (body.message) message = body.message;
      else if (body.non_field_errors?.[0]) message = body.non_field_errors[0];

      if (
        body.code === "validation_error" &&
        Array.isArray(body.errors) &&
        body.errors.length > 0
      ) {
        const firstError = body.errors[0];
        if (firstError.message) {
          const fieldLabel = (firstError.field || "")
            .replace(/payload\.\s*/g, "")
            .replace(/body\.\s*/g, "")
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c: string) => c.toUpperCase());
          message = fieldLabel
            ? `${fieldLabel}: ${firstError.message}`
            : firstError.message;
        }
      }

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

// ─── Media URL helper ──────────────────────────────────────────────────────

export function getMediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  const origin = API_BASE_URL.replace(/\/api\/v\d+\/?$/, "");
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${origin}${normalized}`;
}

// ─── Auth helpers ────────────────────────────────────────────────────────────

export const authHelpers = {
  setAccessToken: (token: string): void => {
    setAccessToken(token);
    const shared = getSharedAuth();
    shared.lastRefreshTime = Date.now();
    shared.isRedirecting = false;
    shared.lastRefreshFailedTime = 0;

    // Clear any pending redirect timeout
    if (shared.redirectTimeout) {
      clearTimeout(shared.redirectTimeout);
      shared.redirectTimeout = null;
    }
  },

  clearAuth: (): void => {
    clearAccessToken();
    const shared = getSharedAuth();
    shared.lastRefreshTime = 0;
    shared.lastRefreshFailedTime = 0;
  },

  getAccessToken,
  isAuthenticated,
  waitForInit,
  navigateTo,

  /** @deprecated Use setAccessToken instead. */
  setTokens: (access: string, _refresh: string, _remember = false): void => {
    setAccessToken(access);
    const shared = getSharedAuth();
    shared.lastRefreshTime = Date.now();
    shared.isRedirecting = false;
    shared.lastRefreshFailedTime = 0;

    if (shared.redirectTimeout) {
      clearTimeout(shared.redirectTimeout);
      shared.redirectTimeout = null;
    }
  },

  /** @deprecated Use clearAuth instead. */
  clearTokens: (): void => {
    clearAccessToken();
    const shared = getSharedAuth();
    shared.lastRefreshTime = 0;
    shared.lastRefreshFailedTime = 0;
  },

  /** @deprecated Refresh token is in httpOnly cookie. */
  getRefreshToken: (): null => {
    return null;
  },
};
