/**
 * Auth utilities — provides helper functions for authentication state
 * management across Vue components (client-side only).
 *
 * Tokens are persisted in sessionStorage (default) or localStorage
 * (when "Remember me" is checked). See api.ts for details.
 */

import { authHelpers, apiClient } from "./api";
import type { ApiError } from "./api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LoginPayload {
  email: string;
  password: string;
  remember?: boolean;
}

export interface RegisterPayload {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  timezone: string;
  currency: string;
  language: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface UserProfile {
  id: number;
  slug: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  timezone: string;
  currency: string;
  language: string;
  is_email_verified: boolean;
  role: string;
  avatar: string | null;
  created_at: string;
  full_name: string;
  display_name: string;
}

// ─── Choice options (synced with backend via API) ────────────────────────────

export interface ChoiceOption {
  value: string;
  label: string;
}

export interface Choices {
  timezones: ChoiceOption[];
  currencies: ChoiceOption[];
  languages: ChoiceOption[];
}

let _choicesCache: Choices | null = null;
let _choicesPromise: Promise<Choices> | null = null;

/**
 * Fetch timezone, currency, language choices from the backend.
 *
 * Reads from Django model enums (TimezoneChoices, CurrencyChoices, LanguageChoices)
 * via `GET /api/v1/auth/choices`. Results are cached in memory for the page
 * lifetime — subsequent calls return the cached data instantly.
 *
 * Usage in a Vue component:
 * ```ts
 * const choices = ref<Choices>({ timezones: [], currencies: [], languages: [] });
 * onMounted(async () => { choices.value = await fetchChoices(); });
 * ```
 */
export async function fetchChoices(): Promise<Choices> {
  if (_choicesCache) return _choicesCache;
  if (_choicesPromise) return _choicesPromise;

  _choicesPromise = apiClient
    .get<Choices>("/auth/choices")
    .then((data) => {
      _choicesCache = data;
      _choicesPromise = null;
      return data;
    })
    .catch((err) => {
      _choicesPromise = null;
      console.error("Failed to fetch choices:", err);
      return { timezones: [], currencies: [], languages: [] };
    });

  return _choicesPromise;
}

/**
 * Return cached choices if already fetched, otherwise null.
 */
export function getCachedChoices(): Choices | null {
  return _choicesCache;
}

// ─── Auth functions ─────────────────────────────────────────────────────────

/**
 * Login — POST /auth/login → store access token in memory
 *
 * HIGH-03 FIX: The refresh token is now stored in an httpOnly cookie by the backend.
 * The response body still contains both tokens for backwards compatibility with
 * API clients, but we only store the access token in memory.
 *
 * @param payload.remember - If true, the cookie persists for 30 days.
 *                          If false/omitted, the cookie is session-only.
 */
export async function login(payload: LoginPayload): Promise<AuthTokens> {
  const data = await apiClient.post<AuthTokens>("/auth/login", payload);
  // HIGH-03 FIX: Only store access token - refresh token is in httpOnly cookie
  authHelpers.setAccessToken(data.access);
  return data;
}

/**
 * Register — POST /auth/register
 */
export async function register(payload: RegisterPayload): Promise<void> {
  await apiClient.post("/auth/register", payload);
}

/**
 * Logout — clear tokens and redirect
 *
 * HIGH-03 FIX: Uses the new cookie-based logout endpoint that:
 * 1. Blacklists the refresh token from the httpOnly cookie
 * 2. Clears the auth cookies
 * We also clear the access token from memory.
 */
export async function logout(): Promise<void> {
  // HIGH-03 FIX: Use cookie-based logout endpoint
  // This blacklists the refresh token and clears cookies
  try {
    await apiClient.post("/auth/logout");
  } catch {
    // Continue with local cleanup even if API call fails
  }
  // Clear access token from memory
  authHelpers.clearAuth();
  if (typeof window !== "undefined") {
    window.location.href = "/auth/login";
  }
}

/**
 * Request password reset email — POST /auth/password-reset/request
 */
export async function requestPasswordReset(email: string): Promise<void> {
  await apiClient.post("/auth/password-reset/request", { email });
}

/**
 * Confirm password reset — POST /auth/password-reset/confirm (OTP-based)
 */
export async function confirmPasswordReset(
  email: string,
  otp: string,
  new_password: string,
  confirm_password: string,
): Promise<void> {
  await apiClient.post("/auth/password-reset/confirm", {
    email,
    otp,
    new_password,
    confirm_password,
  });
}

/**
 * Change password (requires current password) — POST /users/me/change-password
 */
export async function changePassword(
  current_password: string,
  new_password: string,
  confirm_password: string,
): Promise<void> {
  await apiClient.post("/users/me/change-password", {
    current_password,
    new_password,
    confirm_password,
  });
}

/**
 * Confirm user identity via current password — POST /users/me/confirm-identity
 *
 * Reusable identity gate for sensitive operations (email change, account deletion).
 * Rate-limited: 10 attempts per hour window.
 * Returns success if password is correct.
 */
export async function confirmIdentity(
  current_password: string,
): Promise<{ message: string }> {
  return apiClient.post<{ message: string }>("/users/me/confirm-identity", {
    current_password,
  });
}

// NOTE (L1): POST /auth/token/verify is intentionally unused on the frontend.
// Tokens are implicitly verified on each API request via JWT decode in api.ts.
// The standalone verify endpoint is available as a utility but adds no UX value
// since failed tokens already trigger automatic refresh or redirect to login.

/**
 * Request email change — POST /users/me/change-email
 * Sends a 6-digit OTP to the current email.
 */
export async function requestEmailChange(
  current_password: string,
  new_email: string,
): Promise<void> {
  await apiClient.post("/users/me/change-email", {
    current_password,
    new_email,
  });
}

/**
 * Confirm email change with OTP (authenticated) — POST /users/me/change-email/confirm
 */
export async function confirmEmailChangeOTP(otp: string): Promise<string> {
  const res = await apiClient.post<{ message: string; success: boolean }>(
    "/users/me/change-email/confirm",
    { otp },
  );
  return res.message;
}

/**
 * Request email verification — POST /auth/verify-email/request
 */
export async function requestEmailVerification(email: string): Promise<void> {
  await apiClient.post("/auth/verify-email/request", { email });
}

/**
 * Verify email with OTP — POST /auth/verify-email/confirm
 */
export async function verifyEmail(email: string, otp: string): Promise<void> {
  await apiClient.post("/auth/verify-email/confirm", { email, otp });
}

/**
 * Delete account — POST /users/me/delete-account
 */
export async function deleteAccount(current_password: string): Promise<void> {
  await apiClient.post("/users/me/delete-account", { current_password });
}

/**
 * Get current user profile — GET /users/me
 */
export async function getCurrentUser(): Promise<UserProfile> {
  return apiClient.get<UserProfile>("/users/me");
}

/**
 * Update user profile — PUT /users/me
 */
export async function updateProfile(
  data: Partial<
    Pick<
      UserProfile,
      | "first_name"
      | "last_name"
      | "phone"
      | "timezone"
      | "currency"
      | "language"
    >
  >,
): Promise<UserProfile> {
  return apiClient.put<UserProfile>("/users/me", data);
}

/**
 * Update avatar — PUT /users/me/avatar (multipart/form-data)
 *
 * Accepts a File object (from <input type="file">), validates type/size client-side,
 * then uploads via multipart/form-data. Returns the updated user profile with new avatar URL.
 *
 * @param file - The image file to upload
 * @throws Error if file type is invalid or file is too large
 */
export async function updateAvatar(file: File): Promise<UserProfile> {
  // Client-side validation
  const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];
  const MAX_SIZE = 2 * 1024 * 1024; // 2 MB

  if (!ALLOWED_TYPES.includes(file.type)) {
    throw {
      status: 400,
      message:
        "Invalid file type. Please upload a JPEG, PNG, GIF, or WebP image.",
    } as ApiError;
  }

  if (file.size > MAX_SIZE) {
    throw {
      status: 400,
      message: "File is too large. Maximum size is 2 MB.",
    } as ApiError;
  }

  const formData = new FormData();
  formData.append("avatar", file);

  return apiClient.uploadPut<UserProfile>("/users/me/avatar", formData);
}

/**
 * Delete avatar — DELETE /users/me/avatar
 * Removes the user's avatar and returns the updated profile.
 */
export async function deleteAvatar(): Promise<UserProfile> {
  return apiClient.delete<UserProfile>("/users/me/avatar");
}

// ─── Cross-Domain SSO ──────────────────────────────────────────────────────

/**
 * Exchange a one-time authorization code for JWT tokens.
 *
 * Called by the /auth/callback page when a sister domain redirects
 * the user to the Sattabase base domain with an authorization code.
 * The code is consumed upon use and cannot be reused.
 *
 * HIGH-03 FIX: The refresh token is now stored in an httpOnly cookie by the backend.
 * We only store the access token in memory.
 *
 * POST /auth/token/exchange
 */
export async function exchangeAuthCode(code: string): Promise<AuthTokens> {
  const data = await apiClient.post<AuthTokens>("/auth/token/exchange", {
    code,
  });
  // HIGH-03 FIX: Only store access token - refresh token is in httpOnly cookie
  // SSO always uses session cookies (not persistent) for security
  authHelpers.setAccessToken(data.access);
  return data;
}

// ─── Convenience ────────────────────────────────────────────────────────────

/**
 * Check if user is authenticated (has a non-expired access token).
 * Note: This checks the in-memory token (recovered from storage on init).
 * It doesn't validate the token with the server.
 */
export function isAuthenticated(): boolean {
  return authHelpers.isAuthenticated();
}

/**
 * Redirect to login if not authenticated.
 */
export function requireAuth(): boolean {
  if (!isAuthenticated()) {
    if (typeof window !== "undefined") {
      window.location.href = "/auth/login";
    }
    return false;
  }
  return true;
}

/**
 * Format API error message for display.
 */
export function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) {
    return (error as ApiError).message || "An unexpected error occurred.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected error occurred. Please try again.";
}

// ─── Helper: Detect user preferences ────────────────────────────────────────

/**
 * Try to detect the user's timezone from the browser.
 * Falls back to "UTC" if detection fails or if the timezone isn't in our options.
 */
export function detectUserTimezone(choices?: ChoiceOption[]): string {
  if (typeof window === "undefined") return "UTC";
  try {
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (choices) {
      const known = choices.some((opt) => opt.value === detected);
      return known ? detected : "UTC";
    }
    return detected || "UTC";
  } catch {
    return "UTC";
  }
}

/**
 * Try to detect the user's preferred language from the browser.
 * Falls back to "en" if detection fails or if the language isn't in our options.
 */
export function detectUserLanguage(choices?: ChoiceOption[]): string {
  if (typeof window === "undefined") return "en";
  try {
    const browserLang = (navigator.language || "en")
      .split("-")[0]
      .toLowerCase();
    if (choices) {
      const known = choices.some((opt) => opt.value === browserLang);
      return known ? browserLang : "en";
    }
    return browserLang || "en";
  } catch {
    return "en";
  }
}
