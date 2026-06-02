/**
 * useAuth — shared auth + billing state across Vue components.
 *
 * Provides reactive refs for user profile, subscription, and access map.
 * Calls billing.auth.me() once and shares the result across all components
 * via window-level singleton state that survives Astro View Transition
 * module re-evaluations (VM#### contexts).
 *
 * FIRST-CLICK FIX:
 * ================
 * The `isLoggedIn` computed now checks BOTH the user data AND the access token.
 * Previously it only checked `sharedUser.value`, which could be stale — the
 * access token might be cleared (by proactive refresh failure) while the user
 * ref still has cached data. This caused the Vue watch to NOT fire, leaving
 * the user on a protected page with no token.
 *
 * Now, when the access token is cleared (session expired):
 * 1. `isLoggedIn` immediately becomes false (reactive)
 * 2. The Vue watch fires → shows toast → redirects to login
 * 3. The `auth:session-expired` event also triggers an immediate redirect
 * 4. No "first click doesn't work" problem
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

import { ref, computed, watch, onUnmounted } from "vue";
import { billingApi, setUserCurrency } from "@/lib/billing";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { authHelpers, onAuthEvent, getSessionInfo } from "@/lib/api";
import { showToast } from "@/lib/toast";
import type { UserProfile } from "@/lib/auth";
import type { SubscriptionInfoSchema } from "@/lib/billing";

// ─── Window-level shared state (survives module re-evaluation) ────────────
//
// Vue refs are NOT stored on window because they need to remain reactive.
// HOWEVER, module-level Vue refs are destroyed when the module is re-evaluated
// by Astro View Transitions. To solve this, we store the refs on window
// and reuse them on subsequent module evaluations.
//
// The key insight: Vue's reactive system works via Proxy objects. As long as
// we keep using the SAME ref object (even across different module evaluations),
// the reactivity works. We store the ref objects on window and recover them.

const SB_AUTH_COMPOSABLE_KEY = "__sb_auth_composable";

interface SharedAuthComposableState {
  // Vue reactive refs — stored on window so they survive module re-evaluation
  userRef: any; // ref<UserProfile | null>
  subscriptionRef: any; // ref<SubscriptionInfoSchema | null>
  accessRef: any; // ref<Record<string, boolean | number | string>>
  loadingRef: any; // ref<boolean>
  errorRef: any; // ref<Error | null>
  initializedRef: any; // ref<boolean>

  // FIRST-CLICK FIX: Track access token state reactively
  // This ref is updated whenever the access token changes, so Vue's
  // computed properties that depend on it re-evaluate immediately.
  hasTokenRef: any; // ref<boolean>

  // Plain data for deduplication (not reactive)
  initialized: boolean;
  fetchPromise: Promise<UserProfile | null> | null;
  _listenersRegistered?: boolean;
}

function getSharedState(): SharedAuthComposableState {
  if (typeof window === "undefined") {
    // SSR fallback — return a temporary state that won't persist
    return {
      userRef: ref<UserProfile | null>(null),
      subscriptionRef: ref<SubscriptionInfoSchema | null>(null),
      accessRef: ref<Record<string, boolean | number | string>>({}),
      loadingRef: ref(false),
      errorRef: ref<Error | null>(null),
      initializedRef: ref(false),
      hasTokenRef: ref(false),
      initialized: false,
      fetchPromise: null,
    };
  }
  const win = window as any;
  if (!win[SB_AUTH_COMPOSABLE_KEY]) {
    win[SB_AUTH_COMPOSABLE_KEY] = {
      // Create Vue refs ONCE and store on window
      userRef: ref<UserProfile | null>(null),
      subscriptionRef: ref<SubscriptionInfoSchema | null>(null),
      accessRef: ref<Record<string, boolean | number | string>>({}),
      loadingRef: ref(false),
      errorRef: ref<Error | null>(null),
      initializedRef: ref(false),
      hasTokenRef: ref(false),
      // Plain data for dedup
      initialized: false,
      fetchPromise: null,
    };
  }
  return win[SB_AUTH_COMPOSABLE_KEY];
}

// Recover shared refs from window (or create new ones for SSR)
const sharedState = getSharedState();
const sharedUser = sharedState.userRef as import("vue").Ref<UserProfile | null>;
const sharedSubscription =
  sharedState.subscriptionRef as import("vue").Ref<SubscriptionInfoSchema | null>;
const sharedAccess = sharedState.accessRef as import("vue").Ref<
  Record<string, boolean | number | string>
>;
const sharedLoading = sharedState.loadingRef as import("vue").Ref<boolean>;
const sharedError = sharedState.errorRef as import("vue").Ref<Error | null>;
const sharedInitialized =
  sharedState.initializedRef as import("vue").Ref<boolean>;
const sharedHasToken = sharedState.hasTokenRef as import("vue").Ref<boolean>;

// ─── Sync hasToken with the actual access token ──────────────────────────
//
// FIRST-CLICK FIX: The hasToken ref is updated whenever the auth state
// changes. This makes it reactive so that `isLoggedIn` (which depends on it)
// re-evaluates immediately when the access token is cleared.

if (typeof window !== "undefined") {
  // VIEW TRANSITION FIX: Register event listeners using a window-level counter
  // instead of a boolean flag. This allows re-registration when the module
  // is re-evaluated (View Transitions), while still preventing duplicate
  // registrations from the SAME module instance.
  //
  // Previously, `_listenersRegistered` was a boolean on window that was set
  // to `true` on first registration and never reset. When the module was
  // re-evaluated, the Set-based listeners were lost (new empty Set) but the
  // flag prevented re-registration. Now we use a counter that increments on
  // each module evaluation, so the listeners are re-registered.
  const ws = getSharedState();
  const currentEval = (window as any).__sb_auth_eval_count || 0;
  const thisEval = currentEval + 1;
  (window as any).__sb_auth_eval_count = thisEval;

  const regCount =
    typeof ws._listenersRegistered === "number"
      ? ws._listenersRegistered
      : ws._listenersRegistered
        ? 1
        : 0;
  if (regCount < thisEval) {
    ws._listenersRegistered = thisEval;

    // Listen for auth events from api.ts and sync the hasToken ref
    onAuthEvent((event) => {
      if (event === "auth:logout" || event === "auth:session-expired") {
        // Immediately update the reactive token flag so the Vue watch
        // on isLoggedIn fires BEFORE any user click.
        sharedHasToken.value = false;

        // Clear all cached user data when the session ends
        sharedUser.value = null;
        sharedSubscription.value = null;
        sharedAccess.value = {};
        sharedInitialized.value = false;
        getSharedState().initialized = false;
        getSharedState().fetchPromise = null;

        // Show a user-friendly message on session expiry
        if (event === "auth:session-expired") {
          showToast(
            "Your session has expired. Please sign in again.",
            "warning",
          );
        }
      } else if (event === "auth:token-refreshed") {
        // Token was refreshed — update the reactive flag
        sharedHasToken.value = true;
      }
    });

    // BACKUP: Also listen for window CustomEvents from api.ts
    // These are dispatched by emitAuthEvent() as a safety net for
    // cases where the Set-based listeners are lost during View Transitions.
    window.addEventListener("sb:auth:logout", () => {
      sharedHasToken.value = false;
      sharedUser.value = null;
      sharedSubscription.value = null;
      sharedAccess.value = {};
      sharedInitialized.value = false;
      getSharedState().initialized = false;
      getSharedState().fetchPromise = null;
    });

    window.addEventListener("sb:auth:session-expired", () => {
      sharedHasToken.value = false;
      sharedUser.value = null;
      sharedSubscription.value = null;
      sharedAccess.value = {};
      sharedInitialized.value = false;
      getSharedState().initialized = false;
      getSharedState().fetchPromise = null;
      showToast("Your session has expired. Please sign in again.", "warning");
    });

    window.addEventListener("sb:auth:token-refreshed", () => {
      sharedHasToken.value = true;
    });

    // Also listen for billing update events
    window.addEventListener("sattabase:billing-updated", () => {
      if (sharedInitialized.value) {
        // Clear everything so the next fetch hits the API
        sharedUser.value = null;
        sharedSubscription.value = null;
        sharedAccess.value = {};
        sharedInitialized.value = false;
        getSharedState().initialized = false;
        getSharedState().fetchPromise = null;
        // Silent background refetch — errors handled internally
        fetchAuthMe().catch(() => {});
      }
    });
  }
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

    // FIRST-CLICK FIX: Mark that we have a valid token
    sharedHasToken.value = true;

    // Also mark window-level state as initialized
    const ws = getSharedState();
    ws.initialized = true;

    // Set global billing currency from user profile
    if (sharedUser.value?.currency) {
      setUserCurrency(sharedUser.value.currency);
    }

    return sharedUser.value;
  } catch (err) {
    const message = getErrorMessage(err);

    // If the error is a 401, don't show a toast — the auth system will
    // handle the redirect. Showing a toast here causes a confusing
    // double notification (toast + redirect).
    if (
      err &&
      typeof err === "object" &&
      "status" in err &&
      (err as any).status === 401
    ) {
      sharedError.value = err instanceof Error ? err : new Error(message);
      // FIRST-CLICK FIX: Mark that we DON'T have a valid token
      sharedHasToken.value = false;
      return null;
    }

    sharedError.value = err instanceof Error ? err : new Error(message);
    showToast(message, "error");
    return null;
  } finally {
    sharedLoading.value = false;
    const ws = getSharedState();
    ws.fetchPromise = null;
  }
}

// ─── Public composable ──────────────────────────────────────────────────────

export function useAuth() {
  const user = sharedUser;
  const subscription = sharedSubscription;
  const access = sharedAccess;
  const loading = sharedLoading;
  const error = sharedError;

  /**
   * FIRST-CLICK FIX: isLoggedIn now checks BOTH the user data AND the access token.
   *
   * Previously, this was `computed(() => !!sharedUser.value)`, which only
   * checked the cached user data. When the access token was cleared (by
   * proactive refresh failure), the user ref still had data, so isLoggedIn
   * remained true. The Vue watch didn't fire, and the user was stuck on a
   * protected page with no token — their first click would trigger a 401
   * and be "eaten" by error handling.
   *
   * Now, `sharedHasToken` is updated reactively whenever the auth state
   * changes (token refreshed, token expired, logout, etc.). This means
   * `isLoggedIn` immediately becomes false when the token is cleared,
   * triggering the Vue watch in `useSessionGuard()` and redirecting
   * the user before they even need to click.
   */
  const isLoggedIn = computed(() => !!sharedUser.value && sharedHasToken.value);

  /**
   * Computed property for session expiry information.
   * Returns null if not authenticated, or an object with:
   * - expiresAt: Date when the access token expires
   * - timeUntilExpiry: milliseconds until the access token expires
   * - isRememberMe: whether "Remember Me" was checked
   */
  const sessionInfo = computed(() => {
    return getSessionInfo();
  });

  /**
   * Computed property for time until session expires (in minutes).
   * Returns null if not authenticated or no expiry info available.
   * Useful for displaying "Session expires in X minutes" in the UI.
   */
  const minutesUntilExpiry = computed(() => {
    const info = getSessionInfo();
    if (!info.timeUntilExpiry) return null;
    return Math.max(0, Math.floor(info.timeUntilExpiry / 60_000));
  });

  /**
   * Fetch auth.me() — returns user + subscription + access.
   *
   * Deduplicates concurrent calls so that multiple components calling
   * fetchUser() simultaneously trigger only one API request.
   * Uses window-level promise to survive module re-evaluations.
   *
   * Returns cached data if already loaded. Use refetch() to force
   * a fresh API call.
   */
  async function fetchUser(): Promise<UserProfile | null> {
    // Return cached user if already loaded (check both ref and window-level flag)
    if (sharedInitialized.value && sharedUser.value) return sharedUser.value;

    const ws = getSharedState();
    if (ws.initialized && sharedUser.value) return sharedUser.value;

    // Deduplicate concurrent fetches (use window-level promise)
    if (ws.fetchPromise) return ws.fetchPromise;

    ws.fetchPromise = fetchAuthMe();
    return ws.fetchPromise;
  }

  /**
   * Check auth and fetch user in one call. Returns false and redirects
   * to login if not authenticated. Use this in onMounted() of protected pages.
   */
  async function initAuth(): Promise<boolean> {
    // Wait for token initialization to complete (fixes race condition)
    // This ensures the cookie-based token refresh has finished before checking auth
    await authHelpers.waitForInit();

    // FIRST-CLICK FIX: Update the hasToken flag based on current state
    sharedHasToken.value = authHelpers.isAuthenticated();

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
    const ws = getSharedState();
    ws.initialized = false;
    ws.fetchPromise = null;
  }

  /**
   * Force a fresh fetch from the API — clears all cached state first.
   * Use after plan changes, checkouts, cancels, reactivations, etc.
   */
  async function refetch(): Promise<UserProfile | null> {
    invalidateUser();
    return fetchUser();
  }

  /**
   * Setup a Vue watch that monitors auth state and automatically redirects
   * to login when the session expires on a protected page.
   *
   * VUE 3 CONVENTION: All navigation is DEFERRED with setTimeout(0) to avoid
   * the "querySelector null" error in Astro's View Transitions router.
   * Calling navigate() synchronously during a Vue watch callback or event
   * handler can race with Astro's transition lifecycle. By deferring to the
   * next event loop tick, we ensure Astro's router has finished processing
   * the current transition before we start a new navigation.
   *
   * This is the Vue 3 equivalent of nextTick() for navigation — the watch
   * detects the state change immediately, but the actual navigation is
   * deferred until it's safe.
   */
  function useSessionGuard(): void {
    // Watch for auth state changes — deferred redirect
    const stopWatch = watch(isLoggedIn, (authenticated, wasAuthenticated) => {
      // Only act when transitioning FROM authenticated TO not-authenticated
      // on a protected page (not already on an auth page)
      if (wasAuthenticated && !authenticated && typeof window !== "undefined") {
        const currentPath = window.location.pathname;
        const isOnAuthPage = currentPath.startsWith("/auth/");

        if (!isOnAuthPage) {
          showToast(
            "Your session has expired. Redirecting to login...",
            "warning",
          );
          // VUE 3 CONVENTION: Defer navigation to avoid race condition with
          // Astro's View Transition router. setTimeout(0) ensures the current
          // event handler completes before navigate() is called.
          setTimeout(() => {
            if (!window.location.pathname.startsWith("/auth/")) {
              authHelpers.navigateTo("/auth/login");
            }
          }, 0);
        }
      }
    });

    // Deferred redirect on session-expired event.
    // This is the fastest path — the API layer detected the session is over
    // and we should redirect right away. No toast needed here because
    // the auth:session-expired handler in the event sync already showed one.
    const unsubscribe = onAuthEvent((event) => {
      if (event === "auth:session-expired" && typeof window !== "undefined") {
        const currentPath = window.location.pathname;
        if (!currentPath.startsWith("/auth/")) {
          // Defer navigation to avoid race condition with Astro's router
          setTimeout(() => {
            if (!window.location.pathname.startsWith("/auth/")) {
              authHelpers.navigateTo("/auth/login");
            }
          }, 0);
        }
      }
    });

    // BACKUP: Listen for window CustomEvent as a fallback.
    // The module-level `onAuthEvent` Set can be lost during View Transitions
    // (module re-evaluation creates a new empty Set). The CustomEvent on
    // window is dispatched by `emitAuthEvent()` in api.ts and always works.
    // This ensures the redirect happens even if the Set-based listener is lost.
    // SSR SAFE: Only register on the client — window is not available during SSR.
    const handleSessionExpired = () => {
      if (
        typeof window !== "undefined" &&
        !window.location.pathname.startsWith("/auth/")
      ) {
        // Defer navigation to avoid race condition with Astro's router
        setTimeout(() => {
          if (!window.location.pathname.startsWith("/auth/")) {
            authHelpers.navigateTo("/auth/login");
          }
        }, 0);
      }
    };
    if (typeof window !== "undefined") {
      window.addEventListener("sb:auth:session-expired", handleSessionExpired);
    }

    // Cleanup on component unmount
    onUnmounted(() => {
      stopWatch();
      unsubscribe();
      if (typeof window !== "undefined") {
        window.removeEventListener(
          "sb:auth:session-expired",
          handleSessionExpired,
        );
      }
    });
  }

  return {
    user,
    subscription,
    access,
    loading,
    error,
    isLoggedIn,
    initialized: sharedInitialized,
    sessionInfo,
    minutesUntilExpiry,
    fetchUser,
    refetch,
    initAuth,
    invalidateUser,
    useSessionGuard,
  };
}
