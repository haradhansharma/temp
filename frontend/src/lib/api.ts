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
 */

// Vite will find this exact string and replace it during 'npm run build'
// Vite/Astro provides 'import.meta.env.DEV' which is true during 'npm run dev'
const isDev = import.meta.env.DEV;

const envUrl =
  process.env.SERVER_API_BASE_URL_SB || process.env.PUBLIC_API_BASE_URL_SB;

export const API_BASE_URL = isDev
  ? "http://localhost:8081/api/v1"
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

// ─── Helpers ─────────────────────────────────────────────────────────────────

// Token persistence strategy:
//   - Default: sessionStorage  — survives full page reloads within the tab,
//     cleared when tab/window closes. Good balance of convenience + security.
//   - "Remember me": localStorage — persists across tabs and browser restarts.
//   - Tokens are kept in-memory for fast access, with storage as the
//     persistence layer that survives page reloads.

const TOKEN_KEY_ACCESS = "auth_access_token";
const TOKEN_KEY_REFRESH = "auth_refresh_token";
const REMEMBER_KEY = "auth_remember_me";

let _accessToken: string | null = null;
let _refreshToken: string | null = null;

/** Pick the correct storage backend based on "remember me" preference. */
function tokenStorage(): Storage {
  if (typeof window === "undefined") return sessionStorage;
  try {
    return localStorage.getItem(REMEMBER_KEY) === "true"
      ? localStorage
      : sessionStorage;
  } catch {
    return sessionStorage;
  }
}

/** Recover tokens from storage into memory (called on module init). */
function initTokens(): void {
  if (typeof window === "undefined") return;
  try {
    const access =
      sessionStorage.getItem(TOKEN_KEY_ACCESS) ||
      localStorage.getItem(TOKEN_KEY_ACCESS);
    const refresh =
      sessionStorage.getItem(TOKEN_KEY_REFRESH) ||
      localStorage.getItem(TOKEN_KEY_REFRESH);
    if (access) _accessToken = access;
    if (refresh) _refreshToken = refresh;
  } catch {
    /* storage unavailable */
  }
}

// Recover tokens immediately so they're available before requireAuth() runs
initTokens();

function getAccessToken(): string | null {
  return _accessToken;
}

function getRefreshToken(): string | null {
  return _refreshToken;
}

/**
 * Store tokens in memory AND the active storage backend.
 * @param remember - true → localStorage (30-day persistence), false → sessionStorage
 */
function setTokens(access: string, refresh: string, remember = false): void {
  _accessToken = access;
  _refreshToken = refresh;

  if (typeof window === "undefined") return;
  try {
    const storage = remember ? localStorage : sessionStorage;
    storage.setItem(TOKEN_KEY_ACCESS, access);
    storage.setItem(TOKEN_KEY_REFRESH, refresh);
    localStorage.setItem(REMEMBER_KEY, String(remember));
  } catch {
    /* storage unavailable */
  }
}

/** Clear tokens from memory AND both storage backends. */
function clearTokens(): void {
  _accessToken = null;
  _refreshToken = null;

  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(TOKEN_KEY_ACCESS);
    sessionStorage.removeItem(TOKEN_KEY_REFRESH);
    localStorage.removeItem(TOKEN_KEY_ACCESS);
    localStorage.removeItem(TOKEN_KEY_REFRESH);
    localStorage.removeItem(REMEMBER_KEY);
  } catch {
    /* storage unavailable */
  }
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

// ─── Token refresh ──────────────────────────────────────────────────────────

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  // Deduplicate concurrent refresh calls
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const refresh = getRefreshToken();
      if (!refresh) return null;

      const response = await fetch(`${API_BASE_URL}/auth/token/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });

      if (!response.ok) {
        clearTokens();
        return null;
      }

      const data = await response.json();
      if (data.access) {
        _accessToken = data.access;
        if (data.refresh) {
          _refreshToken = data.refresh;
        }
        // Persist refreshed tokens to storage so they survive page reloads
        if (typeof window !== "undefined") {
          try {
            const storage = tokenStorage();
            storage.setItem(TOKEN_KEY_ACCESS, _accessToken!);
            if (data.refresh)
              storage.setItem(TOKEN_KEY_REFRESH, _refreshToken!);
          } catch {
            /* storage unavailable */
          }
        }
        return data.access;
      }

      return null;
    } catch {
      clearTokens();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

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
  const { params, ...restOptions } = options;
  const url = buildUrl(path, params);
  const headers = buildHeaders(
    restOptions.headers as Record<string, string> | undefined,
  );

  // Prevent browser/CDN from caching API responses — every request
  // must hit the server so currency conversions and auth state are fresh.
  const fetchOptions: RequestInit = {
    ...restOptions,
    headers,
    cache: "no-store",
  };

  let response = await fetch(url, fetchOptions);

  // ── 401 → try token refresh ──
  if (response.status === 401 && getRefreshToken()) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      const retryHeaders = buildHeaders(
        options.headers as Record<string, string> | undefined,
      );
      // The refreshAccessToken already stored the new token,
      // but getAccessToken() will read it
      retryHeaders["Authorization"] = `Bearer ${newToken}`;
      response = await fetch(url, { ...fetchOptions, headers: retryHeaders });
    } else {
      // Refresh failed — redirect to login
      clearTokens();
      if (typeof window !== "undefined") {
        window.location.href = "/auth/login";
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

export const authHelpers = {
  setTokens,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  isAuthenticated: (): boolean => !!getAccessToken(),
};
