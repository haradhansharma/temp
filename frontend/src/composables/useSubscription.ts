/**
 * useSubscription — shared subscription state across Vue components.
 *
 * Provides reactive subscription data fetched once and shared across all
 * dashboard components. Eliminates duplicate getSubscriptions() calls from
 * DashboardHome, BillingOverview, PlanComparison, and ProfileCard.
 *
 * Usage:
 *   const { subscriptions, loading, fetchSubscriptions, refetchSubscriptions } = useSubscription();
 */

import { ref } from "vue";
import { billingApi } from "@/lib/billing";
import type { SubscriptionOutputSchema } from "@/lib/billing";

// ─── Module-level shared state (singleton across all components) ────────────

const sharedSubscriptions = ref<SubscriptionOutputSchema[]>([]);
const sharedLoading = ref(false);
const sharedInitialized = ref(false);
let fetchPromise: Promise<SubscriptionOutputSchema[]> | null = null;

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
    if (sharedInitialized.value && sharedSubscriptions.value) return sharedSubscriptions.value;

    if (fetchPromise) return fetchPromise;

    fetchPromise = (async () => {
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
        fetchPromise = null;
      }
    })();

    return fetchPromise;
  }

  /**
   * Force a fresh fetch from the API — clears cache first.
   * Use after plan changes, checkouts, cancels, reactivations, etc.
   */
  async function refetchSubscriptions(): Promise<SubscriptionOutputSchema[]> {
    sharedInitialized.value = false;
    fetchPromise = null;
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
