/**
 * useSubscription — shared subscription state across Vue components.
 *
 * Provides reactive subscription data fetched once and shared across all
 * dashboard components. Eliminates duplicate getSubscriptions() calls from
 * DashboardHome, BillingOverview, PlanComparison, and ProfileCard.
 *
 * CRITICAL FIX: Vue ref() objects created at module level are destroyed
 * when the module is re-evaluated by Astro View Transitions (VM#### contexts).
 * We now store the reactive state on the window object so it persists across
 * module re-evaluations. On re-evaluation, we recover the existing refs from
 * window instead of creating new ones.
 *
 * Usage:
 *   const { subscriptions, loading, fetchSubscriptions, refetchSubscriptions } = useSubscription();
 */

import { ref } from "vue";
import { billingApi } from "@/lib/billing";
import type { SubscriptionOutputSchema } from "@/lib/billing";

// ─── Window-level shared state (survives module re-evaluation) ────────────

const SB_SUB_COMPOSABLE_KEY = "__sb_sub_composable";

interface SharedSubState {
  // Vue reactive refs — stored on window so they survive module re-evaluation
  subscriptionsRef: any; // ref<SubscriptionOutputSchema[]>
  loadingRef: any; // ref<boolean>
  initializedRef: any; // ref<boolean>

  // Plain data for deduplication (not reactive)
  fetchPromise: Promise<SubscriptionOutputSchema[]> | null;
}

function getSharedSubState(): SharedSubState {
  if (typeof window === "undefined") {
    // SSR fallback
    return {
      subscriptionsRef: ref<SubscriptionOutputSchema[]>([]),
      loadingRef: ref(false),
      initializedRef: ref(false),
      fetchPromise: null,
    };
  }
  const win = window as any;
  if (!win[SB_SUB_COMPOSABLE_KEY]) {
    win[SB_SUB_COMPOSABLE_KEY] = {
      // Create Vue refs ONCE and store on window
      subscriptionsRef: ref<SubscriptionOutputSchema[]>([]),
      loadingRef: ref(false),
      initializedRef: ref(false),
      // Plain data
      fetchPromise: null,
    };
  }
  return win[SB_SUB_COMPOSABLE_KEY];
}

// Recover shared refs from window (or create new ones for SSR)
const sharedState = getSharedSubState();
const sharedSubscriptions = sharedState.subscriptionsRef as import("vue").Ref<
  SubscriptionOutputSchema[]
>;
const sharedLoading = sharedState.loadingRef as import("vue").Ref<boolean>;
const sharedInitialized =
  sharedState.initializedRef as import("vue").Ref<boolean>;

export function useSubscription() {
  const subscriptions = sharedSubscriptions;
  const loading = sharedLoading;

  /**
   * Fetch subscriptions. Deduplicates concurrent calls — if multiple components
   * call fetchSubscriptions() simultaneously, only one API request is made
   * and all get the same result.
   *
   * Returns cached subscriptions if already loaded. Use refetchSubscriptions()
   * to force a fresh fetch (e.g. after plan change or checkout).
   */
  async function fetchSubscriptions(): Promise<SubscriptionOutputSchema[]> {
    // Return cached data if already initialized (check both ref and window-level state)
    if (sharedInitialized.value && sharedSubscriptions.value.length > 0) {
      return sharedSubscriptions.value;
    }

    const ws = getSharedSubState();
    if (ws.fetchPromise) return ws.fetchPromise;

    ws.fetchPromise = (async () => {
      sharedLoading.value = true;
      try {
        const data = await billingApi.getSubscriptions();
        sharedSubscriptions.value = data;
        sharedInitialized.value = true;
        return data;
      } catch {
        return [];
      } finally {
        sharedLoading.value = false;
        ws.fetchPromise = null;
      }
    })();

    return ws.fetchPromise;
  }

  /**
   * Force a fresh fetch from the API — clears cache first.
   * Use after plan changes, checkouts, cancels, reactivations, etc.
   */
  async function refetchSubscriptions(): Promise<SubscriptionOutputSchema[]> {
    sharedInitialized.value = false;
    sharedSubscriptions.value = [];
    const ws = getSharedSubState();
    ws.fetchPromise = null;
    return fetchSubscriptions();
  }

  /**
   * Invalidate cached subscriptions — forces fresh fetch on next call.
   */
  function invalidateSubscriptions(): void {
    sharedInitialized.value = false;
  }

  return {
    subscriptions,
    loading,
    initialized: sharedInitialized,
    fetchSubscriptions,
    refetchSubscriptions,
    invalidateSubscriptions,
  };
}
