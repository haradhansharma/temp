/**
 * useAuth — shared auth + billing state across Vue components.
 *
 * Provides reactive refs for user profile, subscription, and access map.
 * Calls billing.auth.me() once and shares the result across all components
 * via module-level singleton state.
 *
 * On the Sattabase dashboard (no X-Service-Domain header):
 *   user is populated, subscription and access are empty.
 *
 * On sister domains (X-Service-Domain header sent):
 *   user + subscription + access are all populated with domain-specific data.
 *
 * Auto-invalidates when a billing update is detected (dispatched by
 * useBillingRedirect via the "sattabase:billing-updated" custom event).
 *
 * Usage:
 *   const { user, subscription, access, loading, error, refetch } = useAuth();
 */

import { ref, computed, onMounted, onUnmounted } from "vue";
import { billingApi, setUserCurrency } from "@/lib/billing";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { authHelpers, onAuthEvent } from "@/lib/api";
import { showToast } from "@/lib/toast";
import type { UserProfile } from "@/lib/auth";
import type { SubscriptionInfoSchema } from "@/lib/billing";

// ─── Module-level shared state (singleton across all components) ────────────

const sharedUser = ref<UserProfile | null>(null);
const sharedSubscription = ref<SubscriptionInfoSchema | null>(null);
const sharedAccess = ref<Record<string, boolean | number | string>>({});
const sharedLoading = ref(false);
const sharedError = ref<Error | null>(null);
const sharedInitialized = ref(false);
let fetchPromise: Promise<UserProfile | null> | null = null;

// ─── Auto-invalidation on billing updates ──────────────────────────────────
//
// When a sister domain detects a billing_updated param (via useBillingRedirect),
// it dispatches this custom event. useAuth picks it up and silently refetches
// so that subscription and access are fresh.

const BILLING_EVENT = "sattabase:billing-updated";

if (typeof window !== "undefined") {
  window.addEventListener(BILLING_EVENT, () => {
    if (sharedInitialized.value) {
      // Clear everything so the next fetch hits the API
      sharedUser.value = null;
      sharedSubscription.value = null;
      sharedAccess.value = {};
      sharedInitialized.value = false;
      fetchPromise = null;
      // Silent background refetch — errors handled internally
      fetchAuthMe().catch(() => {});
    }
  });

  // Listen for auth logout events from api.ts
  // This handles the case where multiple concurrent requests fail auth
  // and we need to redirect to login
  onAuthEvent((event) => {
    if (event === "auth:logout") {
      // Clear the shared state
      sharedUser.value = null;
      sharedSubscription.value = null;
      sharedAccess.value = {};
      sharedInitialized.value = false;
      fetchPromise = null;
    }
  });
}

// ─── Internal fetch ─────────────────────────────────────────────────────────

async function fetchAuthMe(): Promise<UserProfile | null> {
  sharedLoading.value = true;
  sharedError.value = null;

  try {
    const data = await billingApi.getAuthMe();

    // The backend returns the same user fields as GET /users/me,
    // wrapped with subscription + access. Cast to UserProfile.
    sharedUser.value = data.user as unknown as UserProfile;
    sharedSubscription.value = data.subscription;
    sharedAccess.value = data.access;
    sharedInitialized.value = true;

    // Set global billing currency from user profile
    if (sharedUser.value?.currency) {
      setUserCurrency(sharedUser.value.currency);
    }

    return sharedUser.value;
  } catch (err) {
    const message = getErrorMessage(err);
    sharedError.value = err instanceof Error ? err : new Error(message);
    showToast(message, "error");
    return null;
  } finally {
    sharedLoading.value = false;
    fetchPromise = null;
  }
}

// ─── Public composable ──────────────────────────────────────────────────────

export function useAuth() {
  const user = sharedUser;
  const subscription = sharedSubscription;
  const access = sharedAccess;
  const loading = sharedLoading;
  const error = sharedError;

  const isLoggedIn = computed(() => !!sharedUser.value);

  /**
   * Fetch auth.me() — returns user + subscription + access.
   *
   * Deduplicates concurrent calls so that multiple components calling
   * fetchUser() simultaneously trigger only one API request.
   *
   * Returns cached data if already loaded. Use refetch() to force
   * a fresh API call.
   */
  async function fetchUser(): Promise<UserProfile | null> {
    // Return cached user if already loaded
    if (sharedInitialized.value && sharedUser.value) return sharedUser.value;

    // Deduplicate concurrent fetches
    if (fetchPromise) return fetchPromise;

    fetchPromise = fetchAuthMe();
    return fetchPromise;
  }

  /**
   * Check auth and fetch user in one call. Returns false and redirects
   * to login if not authenticated. Use this in onMounted() of protected pages.
   */
  async function initAuth(): Promise<boolean> {
    // Wait for token initialization to complete (fixes race condition)
    // This ensures the cookie-based token refresh has finished before checking auth
    await authHelpers.waitForInit();

    if (!requireAuth()) return false;
    await fetchUser();
    return !!sharedUser.value;
  }

  /**
   * Invalidate the cached user — forces a fresh fetch on next fetchUser() call.
   * Useful after profile updates, email changes, or billing operations.
   */
  function invalidateUser(): void {
    sharedUser.value = null;
    sharedSubscription.value = null;
    sharedAccess.value = {};
    sharedInitialized.value = false;
    fetchPromise = null;
  }

  /**
   * Force a fresh fetch from the API — clears all cached state first.
   * Use after plan changes, checkouts, cancels, reactivations, etc.
   */
  async function refetch(): Promise<UserProfile | null> {
    invalidateUser();
    return fetchUser();
  }

  return {
    user,
    subscription,
    access,
    loading,
    error,
    isLoggedIn,
    initialized: sharedInitialized,
    fetchUser,
    refetch,
    initAuth,
    invalidateUser,
  };
}
