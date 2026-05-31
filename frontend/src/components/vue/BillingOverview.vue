<script setup lang="ts">
/**
 * BillingOverview — Main billing dashboard Vue island.
 *
 * Displays:
 *  - Stats row: active subscriptions count, products, next billing date
 *  - Subscription cards per product with status, plan, period end
 *  - Quick actions: manage subscription, view plans, change plan
 *  - Products catalog with links to plan comparison pages
 */

import { ref, computed, onMounted, onUnmounted, watch, nextTick } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { useSubscription } from "@/composables";
import { showToast } from "@/lib/toast";
import {
  billingApi,
  formatPrice,
  formatCycle,
  formatDate,
  getStatusStyle,
  getUserCurrency,
  setUserCurrency,
} from "@/lib/billing";
import type {
  ProductSchema,
  SubscriptionOutputSchema,
  SubscriptionDetailSchema,
  TransactionItemSchema,
} from "@/lib/billing";

// 6.5: Return URL for sister-domain billing redirect
const returnUrl = ref<string | null>(null);

/** Get stored return_url from sessionStorage (set by PlanComparison or incoming redirect) */
function getStoredReturnUrl(): string | null {
  return sessionStorage.getItem("billing_return_url");
}

/** Store return_url in sessionStorage for use across redirect chain */
function storeReturnUrl(url: string | null) {
  if (url) {
    sessionStorage.setItem("billing_return_url", url);
  } else {
    sessionStorage.removeItem("billing_return_url");
  }
}

/** Redirect to return_url with billing_updated param */
function redirectToReturnUrl(updated: 1 | 0) {
  const url = returnUrl.value || getStoredReturnUrl();
  if (!url) return;
  storeReturnUrl(null); // Clean up
  const separator = url.includes("?") ? "&" : "?";
  window.location.href = `${url}${separator}billing_updated=${updated}`;
}

const loading = ref(true);
const loadError = ref(false);
const products = ref<ProductSchema[]>([]);
const { subscriptions, refetchSubscriptions } = useSubscription();
const actionLoading = ref<string | null>(null);
const transactions = ref<TransactionItemSchema[]>([]);
const transactionsLoading = ref(false);
const transactionsHasMore = ref(false);
const userCurrency = ref("USD");

// UX-03: Currency mismatch state
const currencyMismatch = ref(false);
const lockedCurrency = ref("");

// UX-02: Cancel modal state
const showCancelModal = ref(false);
const cancelModalSub = ref<SubscriptionOutputSchema | null>(null);
// SEC-02: Cancel reason state
const cancelReason = ref("");

const hasPaidSubscription = computed(() =>
  subscriptions.value.some(
    (s) =>
      (["active", "trialing", "past_due"].includes(s.status) || s.cancel_at_period_end) &&
      s.plan_slug !== "free",
  ),
);

const pastDueSubscriptions = computed(() =>
  subscriptions.value.filter((s) => s.status === "past_due"),
);

const pausedSubscriptions = computed(() =>
  subscriptions.value.filter((s) => s.status === "paused"),
);

const stats = computed(() => {
  const active = subscriptions.value.filter((s) =>
    ["active", "trialing"].includes(s.status) || s.cancel_at_period_end,
  );
  const nextEnd = subscriptions.value
    .filter((s) => s.current_period_end && s.status !== "expired")
    .sort((a, b) => new Date(a.current_period_end!).getTime() - new Date(b.current_period_end!).getTime());
  const paidCount = active.filter((s) => !s.plan_slug.includes("free"));

  return {
    activeCount: active.length,
    productCount: products.value.length,
    nextBillingDate: nextEnd.length > 0 ? nextEnd[0].current_period_end : null,
    paidPlans: paidCount.length,
  };
});

/**
 * Compute the effective cancellation date for a subscription.
 *
 * For trial subscriptions canceled from the portal, Stripe cancels at trial_end
 * (not period_end). The backend sets status=canceled + cancel_at_period_end=true.
 * We detect this by checking if trial_end is before current_period_end.
 *
 * For frontend-initiated cancels or active subscriptions, cancel is at period_end.
 */
function getCancelDate(sub: SubscriptionOutputSchema): string | null {
  if (!sub.cancel_at_period_end) return null;

  // Trial-end cancellation: portal cancels at trial end, not period end
  if (sub.trial_end) {
    const trialEnd = new Date(sub.trial_end);
    const periodEnd = sub.current_period_end ? new Date(sub.current_period_end) : null;
    if (!periodEnd || trialEnd <= periodEnd) {
      return sub.trial_end;
    }
  }

  return sub.current_period_end || null;
}

/** Whether the subscription is canceling at trial end (vs period end). */
function isTrialCancel(sub: SubscriptionOutputSchema): boolean {
  if (!sub.cancel_at_period_end || !sub.trial_end) return false;
  const trialEnd = new Date(sub.trial_end);
  const periodEnd = sub.current_period_end ? new Date(sub.current_period_end) : null;
  return !periodEnd || trialEnd <= periodEnd;
}

onMounted(async () => {
  if (!requireAuth()) return;

  // Handle Stripe checkout redirect feedback
  const params = new URLSearchParams(window.location.search);
  const checkoutStatus = params.get("checkout");
  const sessionId = params.get("session_id");
  const incomingReturnUrl = params.get("return_url");

  // 6.5: Capture return_url from incoming Stripe redirect or direct link
  if (incomingReturnUrl) {
    storeReturnUrl(incomingReturnUrl);
    returnUrl.value = incomingReturnUrl;
  } else {
    returnUrl.value = getStoredReturnUrl();
  }

  if (checkoutStatus === "success" && sessionId) {
    try {
      showToast("Processing payment...", "info", { duration: 3000 });
      const result = await billingApi.confirmCheckout(sessionId);
      const trialNote = result.status === "trialing"
        ? ` (trial ends ${new Date(result.trial_end!).toLocaleDateString()})`
        : "";
      showToast(`Upgraded to ${result.plan_name}!${trialNote}`, "success", { duration: 8000 });
    } catch (err) {
      showToast(getErrorMessage(err), "error", { duration: 8000 });
    }
    window.history.replaceState({}, "", "/dashboard/billing");
    // 6.5: Redirect to sister domain after successful checkout confirmation
    redirectToReturnUrl(1);
    return; // Don't render the billing page — redirecting out
  } else if (checkoutStatus === "canceled") {
    showToast("Checkout was canceled. No changes were made.", "info", { duration: 5000 });
    window.history.replaceState({}, "", "/dashboard/billing");
    // 6.5: Redirect to sister domain after cancel
    if (returnUrl.value) {
      redirectToReturnUrl(0);
      return;
    }
  }

  // UX-04: Handle Stripe Portal return feedback
  const portalStatus = params.get("portal");
  if (portalStatus === "success") {
    showToast("Billing settings updated successfully.", "success", { duration: 5000 });
    window.history.replaceState({}, "", "/dashboard/billing");
    // UX-04: Force-sync from Stripe to eliminate webhook race condition.
    // The user may have canceled, reactivated, or changed payment method
    // in the portal.  The webhook might not have fired yet, so we fetch
    // the live state from Stripe directly.
    try {
      // Capture pre-portal state to detect what changed
      const prePortalState = new Map(
        subscriptions.value.map((s) => [s.product_slug, s.status])
      );

      const synced = await billingApi.syncSubscriptions();
      await refetchSubscriptions();

      // PORTAL-CANCEL SYNC: Compare pre-portal vs synced state to show
      // the same feedback messages as the Cancel/Reactivate buttons.
      for (const sub of synced) {
        const prevStatus = prePortalState.get(sub.product_slug);
        if (!prevStatus) continue;

        // Detect cancellation: active/trialing → canceled
        if (
          ["active", "trialing"].includes(prevStatus) &&
          sub.status === "canceled"
        ) {
          showToast(`Subscription canceled (${sub.plan_name}). Access continues until period end.`, "success", { duration: 8000 });
        }

        // Detect reactivation: canceled → active/trialing
        if (
          prevStatus === "canceled" &&
          ["active", "trialing"].includes(sub.status)
        ) {
          showToast(`Subscription reactivated (${sub.plan_name}).`, "success", { duration: 8000 });
        }
      }
    } catch (err) {
      showToast("Failed to sync billing state from Stripe. Please reload the page.", "error", { duration: 5000 });
      // Fallback: re-fetch from local DB (webhook may have processed by now)
      try {
        await refetchSubscriptions();
      } catch {
        // Non-critical — data will refresh on next page load
      }
    }
    // 6.5: Redirect to sister domain after portal session
    if (returnUrl.value) {
      redirectToReturnUrl(1);
      return;
    }
  }

    await fetchInitialData();
  });

  // UX-04: Error state — retry capability when initial data fetch fails
  async function retryFetch() {
    loading.value = true;
    loadError.value = false;
    await fetchInitialData();
  }

  // Moved out of onMounted so it's accessible from the template
  async function fetchInitialData() {
    try {
      const [productsData] = await Promise.all([
        billingApi.getProducts(),
        refetchSubscriptions(),
      ]);
      products.value = productsData;

      // Fetch user's preferred currency from auth/me (F13)
      try {
        const authData = await billingApi.getAuthMe();
        if (authData?.user?.currency) {
          const cur = authData.user.currency as string;
          userCurrency.value = cur;
          // Also update the global default so PlanComparison etc. benefit
          setUserCurrency(cur);

          // UX-03: Detect currency mismatch between user preference and
          // the global default that was set by Navbar before this fetch
          // completed (race condition recovery).
          const prevGlobal = getUserCurrency();
          if (prevGlobal && prevGlobal !== cur) {
            currencyMismatch.value = true;
            lockedCurrency.value = cur;
          }
        }
      } catch {
        // Non-critical — falls back to "USD"
      }

      // UX-01: Auto-load initial billing history for paid subscribers
      if (subscriptions.value.some(
        (s) => ["active", "trialing", "past_due"].includes(s.status) && s.plan_slug !== "free",
      )) {
        try {
          const txResult = await billingApi.getTransactionHistory(20);
          transactions.value = txResult.transactions;
          transactionsHasMore.value = txResult.has_more;
        } catch {
          // Non-critical — user can manually load
        }
      }
    } catch (err) {
      // UX-04 Fix: Set error state instead of just showing a toast
      loadError.value = true;
      showToast(getErrorMessage(err), "error");
    } finally {
      loading.value = false;
    }
  }

// UX-02: Cancel subscription modal — replaces simple toast confirmation
function openCancelModal(sub: SubscriptionOutputSchema) {
  cancelModalSub.value = sub;
  showCancelModal.value = true;
}

function closeCancelModal() {
  showCancelModal.value = false;
  cancelModalSub.value = null;
  cancelReason.value = "";
}

// A11Y-01: Focus trap and Escape key handler for modal
const modalRef = ref<HTMLElement | null>(null);
const previouslyFocusedElement = ref<HTMLElement | null>(null);

function handleEscapeKey(e: KeyboardEvent) {
  if (e.key === "Escape" && showCancelModal.value) {
    closeCancelModal();
  }
}

function trapFocus(e: KeyboardEvent) {
  if (!showCancelModal.value || !modalRef.value) return;
  const modal = modalRef.value;
  const focusable = modal.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  if (focusable.length === 0) return;
  const firstFocusable = focusable[0];
  const lastFocusable = focusable[focusable.length - 1];
  if (e.key === "Tab") {
    if (e.shiftKey) {
      if (document.activeElement === firstFocusable) {
        e.preventDefault();
        lastFocusable.focus();
      }
    } else {
      if (document.activeElement === lastFocusable) {
        e.preventDefault();
        firstFocusable.focus();
      }
    }
  }
}

watch(showCancelModal, async (isOpen) => {
  if (isOpen) {
    previouslyFocusedElement.value = document.activeElement as HTMLElement;
    document.addEventListener("keydown", handleEscapeKey);
    document.addEventListener("keydown", trapFocus);
    await nextTick();
    // Focus the first focusable element in the modal
    const focusable = modalRef.value?.querySelector<HTMLElement>(
      'button, [href], input, select, textarea'
    );
    focusable?.focus();
  } else {
    document.removeEventListener("keydown", handleEscapeKey);
    document.removeEventListener("keydown", trapFocus);
    previouslyFocusedElement.value?.focus();
  }
});

onUnmounted(() => {
  document.removeEventListener("keydown", handleEscapeKey);
  document.removeEventListener("keydown", trapFocus);
});

async function executeCancelModal() {
  if (!cancelModalSub.value) return;
  const productSlug = cancelModalSub.value.product_slug;
  // SEC-02 Fix: Capture the cancel reason before closing modal
  const reason = cancelReason.value || "";
  showCancelModal.value = false;
  await executeCancel(productSlug, reason);
}

async function handleCancel(productSlug: string) {
  // UX-02: Open full cancel modal instead of simple toast
  const sub = subscriptions.value.find((s) => s.product_slug === productSlug);
  if (sub) {
    openCancelModal(sub);
  }
}

async function executeCancel(productSlug: string, reason: string = "") {
  actionLoading.value = `cancel-${productSlug}`;
  try {
    // SEC-02 Fix: Pass cancellation reason to the backend API
    await billingApi.cancelSubscription(productSlug, reason);
    if (reason) {
      showToast(`Subscription canceled (reason: ${reason}). Access continues until period end.`, "success");
    } else {
      showToast("Subscription canceled. Access continues until period end.", "success");
    }
    await refetchSubscriptions();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

async function handleReactivate(productSlug: string) {
  actionLoading.value = `reactivate-${productSlug}`;
  try {
    await billingApi.reactivateSubscription(productSlug);
    showToast("Subscription reactivated successfully.", "success");
    await refetchSubscriptions();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

async function handleManageBilling() {
  actionLoading.value = "portal";
  try {
    const result = await billingApi.createPortalSession(getStoredReturnUrl() || undefined);
    window.location.href = result.portal_url;
  } catch (err) {
    showToast(getErrorMessage(err), "error");
    actionLoading.value = null;
  }
}

async function handleFixPayment(productSlug: string) {
  showToast(
    "Your payment method needs updating. You'll be redirected to Stripe to update your payment information.",
    "warning",
    { duration: 5000 }
  );
  try {
    await billingApi.createPortalSession(getStoredReturnUrl() || undefined).then((result) => {
      window.location.href = result.portal_url;
    });
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  }
}

// UX-03: Handle currency mismatch — auto-detect from error and provide recovery
async function switchCurrency(currency: string) {
  userCurrency.value = currency;
  setUserCurrency(currency);
  currencyMismatch.value = false;
  try {
    await refetchSubscriptions();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  }
}

// M1: Subscription detail expand state
const expandedSubSlug = ref<string | null>(null);
const subDetails = ref<Map<string, SubscriptionDetailSchema>>(new Map());
const subDetailLoading = ref<string | null>(null);

async function toggleSubDetail(productSlug: string) {
  if (expandedSubSlug.value === productSlug) {
    expandedSubSlug.value = null;
    return;
  }
  expandedSubSlug.value = productSlug;

  // Already fetched — just toggle visibility
  if (subDetails.value.has(productSlug)) return;

  subDetailLoading.value = productSlug;
  try {
    const detail = await billingApi.getSubscriptionDetail(productSlug);
    subDetails.value.set(productSlug, detail);
  } catch (err) {
    showToast(getErrorMessage(err), "error");
    expandedSubSlug.value = null;
  } finally {
    subDetailLoading.value = null;
  }
}

async function loadTransactions() {
  transactionsLoading.value = true;
  try {
    const lastId = transactions.value.length > 0 ? transactions.value[transactions.value.length - 1].id : undefined;
    const result = await billingApi.getTransactionHistory(20, lastId);
    transactions.value = [...transactions.value, ...result.transactions];
    transactionsHasMore.value = result.has_more;
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    transactionsLoading.value = false;
  }
}
</script>

<template>
  <div>
    <!-- Page Header -->
    <div class="mb-8">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-2xl font-bold tracking-tight md:text-3xl">Billing &amp; Subscriptions</h1>
          <p class="mt-1 text-[var(--color-muted-foreground)]">
            Manage your subscriptions, view plans, and control access across all products.
          </p>
        </div>
        <button
          v-if="hasPaidSubscription"
          :disabled="actionLoading === 'portal'"
          class="btn-secondary text-sm shrink-0"
          @click="handleManageBilling"
        >
          <svg class="h-4 w-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          {{ actionLoading === 'portal' ? 'Opening...' : 'Manage Billing' }}
        </button>
      </div>
    </div>

    <!-- Loading Skeleton -->
    <template v-if="loading">
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <div v-for="i in 4" :key="i" class="card p-6 animate-pulse">
          <div class="flex items-center justify-between">
            <div class="h-4 w-28 rounded bg-[var(--color-muted)]" />
            <div class="h-8 w-8 rounded-lg bg-[var(--color-muted)]" />
          </div>
          <div class="mt-3 h-7 w-20 rounded bg-[var(--color-muted)]" />
        </div>
      </div>
      <div v-for="i in 3" :key="'sub-' + i" class="card p-6 animate-pulse mb-4">
        <div class="flex items-center justify-between mb-4">
          <div class="h-5 w-40 rounded bg-[var(--color-muted)]" />
          <div class="h-6 w-24 rounded-full bg-[var(--color-muted)]" />
        </div>
        <div class="h-4 w-64 rounded bg-[var(--color-muted)]" />
      </div>
    </template>

    <template v-else-if="loadError">
      <!-- UX-04: Error state with retry button when initial fetch fails -->
      <div class="card flex flex-col items-center justify-center py-20 text-center px-6">
        <div class="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
          <svg class="h-8 w-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
        </div>
        <h3 class="text-lg font-semibold text-red-800 dark:text-red-300">Unable to Load Billing Data</h3>
        <p class="mt-2 text-sm text-[var(--color-muted-foreground)] max-w-sm">
          We couldn't load your billing information. This may be a temporary network issue. Please try again.
        </p>
        <button
          class="btn-primary mt-6"
          @click="retryFetch"
        >
          <svg class="h-4 w-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Retry
        </button>
      </div>
    </template>

    <template v-else>
      <!-- PAST_DUE Warning Banner (H2: Dunning) -->
      <div
        v-if="pastDueSubscriptions.length > 0"
        class="mb-6 rounded-lg border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30 p-4"
      >
        <div class="flex items-start gap-3">
          <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/50">
            <svg class="h-4 w-4 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <div class="flex-1">
            <h3 class="text-sm font-semibold text-red-800 dark:text-red-300">Payment Failed</h3>
            <p class="mt-1 text-sm text-red-700 dark:text-red-400">
              Your payment method was declined. Please update your payment information to avoid losing access.
            </p>
            <div class="mt-3 flex items-center gap-2">
              <button
                :disabled="actionLoading === 'fix-payment'"
                class="btn-primary text-xs !bg-red-600 hover:!bg-red-700 dark:!bg-red-700 dark:hover:!bg-red-800"
                @click="handleFixPayment(pastDueSubscriptions[0].product_slug)"
              >
                {{ actionLoading === 'fix-payment' ? 'Opening...' : 'Update Payment Method' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Paused Subscription Banner (I1) -->
      <div
        v-if="pausedSubscriptions.length > 0"
        class="mb-6 rounded-lg border border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50 p-4"
      >
        <div class="flex items-start gap-3">
          <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-700">
            <svg class="h-4 w-4 text-gray-600 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div class="flex-1">
            <h3 class="text-sm font-semibold text-gray-800 dark:text-gray-300">Subscription Paused</h3>
            <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Your subscription is currently paused. You can resume it from the billing portal.
            </p>
            <div class="mt-3">
              <button
                :disabled="actionLoading === 'portal'"
                class="btn-secondary text-xs"
                @click="handleManageBilling"
              >
                Manage in Portal
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Stats Row -->
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <!-- Active Subscriptions -->
        <div class="card p-6">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-[var(--color-muted-foreground)]">Active Plans</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-100 dark:bg-brand-950">
              <svg class="h-4 w-4 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">{{ stats.activeCount }}</p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">across {{ stats.productCount }} product{{ stats.productCount !== 1 ? 's' : '' }}</p>
        </div>

        <!-- Products -->
        <div class="card p-6">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-[var(--color-muted-foreground)]">Products</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-950">
              <svg class="h-4 w-4 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">{{ stats.productCount }}</p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">available services</p>
        </div>

        <!-- Next Billing -->
        <div class="card p-6">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-[var(--color-muted-foreground)]">Next Billing</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-100 dark:bg-purple-950">
              <svg class="h-4 w-4 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">{{ stats.nextBillingDate ? formatDate(stats.nextBillingDate) : '—' }}</p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">earliest renewal</p>
        </div>

        <!-- Paid Plans -->
        <div class="card p-6">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-[var(--color-muted-foreground)]">Paid Plans</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-950">
              <svg class="h-4 w-4 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">{{ stats.paidPlans }}</p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">premium subscriptions</p>
        </div>
      </div>

      <!-- Subscriptions Section -->
      <div class="mb-8">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold">Your Subscriptions</h2>
          <!-- UX-03 Fix: Use stats.activeCount (active/trialing) instead of
               activeSubscriptions.length (includes past_due/canceled) for the
               "N active" label. This ensures the header count matches the
               Active Plans stat card below, eliminating user confusion.
               activeSubscriptions is still used for rendering the subscription
               card list which shows all non-expired subs. -->
          <span class="text-sm text-[var(--color-muted-foreground)]">
            {{ stats.activeCount }} active
          </span>
        </div>

        <!-- No subscriptions state -->
        <div v-if="subscriptions.length === 0" class="card flex flex-col items-center justify-center py-16 text-center px-6">
          <div class="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[var(--color-muted)]">
            <svg class="h-8 w-8 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
            </svg>
          </div>
          <p class="text-sm font-medium text-[var(--color-muted-foreground)]">No subscriptions yet</p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)] max-w-xs">
            Browse available products and plans below to get started.
          </p>
        </div>

        <!-- Subscription Cards -->
        <div v-else class="space-y-4">
          <div
            v-for="sub in subscriptions"
            :key="sub.id"
            class="card p-6 transition-all duration-200 hover:shadow-md"
          >
            <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <!-- Left: Product + Plan info -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-3 mb-2">
                  <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg gradient-brand text-white text-sm font-bold shadow-md shadow-brand-600/20">
                    {{ sub.product_name.charAt(0) }}
                  </div>
                  <div>
                    <h3 class="text-base font-semibold truncate">{{ sub.product_name }}</h3>
                    <p class="text-sm text-[var(--color-muted-foreground)]">
                      {{ sub.plan_name }} Plan
                    </p>
                  </div>
                </div>

                <div class="flex flex-wrap items-center gap-3 text-sm text-[var(--color-muted-foreground)]">
                  <!-- Status Badge -->
                  <span
                    :class="[
                      sub.cancel_at_period_end
                        ? 'bg-amber-50 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300'
                        : [getStatusStyle(sub.status).bg, getStatusStyle(sub.status).text]
                    ]"
                    class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
                  >
                    <span
                      :class="sub.cancel_at_period_end ? 'bg-amber-500' : getStatusStyle(sub.status).dot"
                      class="h-1.5 w-1.5 rounded-full"
                    />
                    <template v-if="sub.cancel_at_period_end">
                      {{ isTrialCancel(sub) ? 'Trial, cancels at end' : 'Cancels at period end' }}
                    </template>
                    <template v-else>
                      {{ sub.status.charAt(0).toUpperCase() + sub.status.slice(1).replace('_', ' ') }}
                    </template>
                  </span>

                  <!-- Trial end date (only when NOT canceling — canceling shows its own line below) -->
                  <span v-if="sub.status === 'trialing' && sub.trial_end && !sub.cancel_at_period_end" class="flex items-center gap-1 text-blue-600 dark:text-blue-400">
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Trial ends {{ formatDate(sub.trial_end) }}
                  </span>

                  <!-- Canceling: show effective cancel date (trial end or period end) -->
                  <span v-if="sub.cancel_at_period_end && getCancelDate(sub)" class="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                    </svg>
                    Cancels {{ formatDate(getCancelDate(sub)!) }}
                  </span>

                  <!-- Renewal date (non-trial, non-canceled active) -->
                  <span v-if="sub.current_period_end && sub.status !== 'trialing' && !sub.cancel_at_period_end" class="flex items-center gap-1">
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    Renews {{ formatDate(sub.current_period_end) }}
                  </span>

                  <!-- First billing after trial (only when NOT canceling) -->
                  <span v-if="sub.status === 'trialing' && sub.current_period_end && !sub.cancel_at_period_end" class="text-[var(--color-muted-foreground)]">
                    First bill {{ formatDate(sub.current_period_end) }}
                  </span>

                  <!-- Canceled date (hard cancellation, not cancel_at_period_end) -->
                  <span v-if="sub.canceled_at && !sub.cancel_at_period_end" class="text-orange-600 dark:text-orange-400">
                    Canceled {{ formatDate(sub.canceled_at) }}
                  </span>
                </div>
              </div>

              <!-- Right: Actions -->
              <div class="flex items-center gap-2 shrink-0">
                <!-- M1: Toggle plan details -->
                <button
                  class="btn-ghost text-xs"
                  :class="expandedSubSlug === sub.product_slug ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                  :disabled="subDetailLoading === sub.product_slug"
                  @click="toggleSubDetail(sub.product_slug)"
                >
                  <svg
                    class="h-3.5 w-3.5 mr-1 transition-transform duration-200"
                    :class="expandedSubSlug === sub.product_slug ? 'rotate-180' : ''"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                  </svg>
                  {{ subDetailLoading === sub.product_slug ? 'Loading...' : 'Details' }}
                </button>

                <!-- UX-09: Prominent Upgrade CTA for free plans -->
                <a
                  v-if="sub.plan_slug === 'free'"
                  :href="`/dashboard/billing/plans/${sub.product_slug}`"
                  class="btn-primary text-xs"
                >
                  <svg class="h-3.5 w-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                  </svg>
                  Upgrade
                </a>
                <a
                  v-else
                  :href="`/dashboard/billing/plans/${sub.product_slug}`"
                  class="btn-secondary text-xs"
                >
                  View Plans
                </a>

                <!-- Manage Billing (Stripe Portal) -->
                <button
                  v-if="sub.plan_slug !== 'free' && (['active', 'trialing'].includes(sub.status) || sub.cancel_at_period_end)"
                  :disabled="actionLoading === `portal-${sub.product_slug}`"
                  class="btn-ghost text-xs text-brand-600 dark:text-brand-400 hover:text-brand-700"
                  @click="handleManageBilling"
                >
                  <svg class="h-3.5 w-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {{ actionLoading === 'portal' ? 'Opening...' : 'Manage' }}
                </button>

                <button
                  v-if="sub.plan_slug !== 'free' && ['active', 'trialing'].includes(sub.status) && !sub.cancel_at_period_end"
                  :disabled="actionLoading === `cancel-${sub.product_slug}`"
                  class="btn-ghost text-xs text-destructive hover:text-destructive"
                  @click="handleCancel(sub.product_slug)"
                >
                  Cancel
                </button>

                <button
                  v-if="sub.status === 'canceled'"
                  :disabled="actionLoading === `reactivate-${sub.product_slug}`"
                  class="btn-ghost text-xs text-brand-600 dark:text-brand-400 hover:text-brand-700"
                  @click="handleReactivate(sub.product_slug)"
                >
                  {{ actionLoading === `reactivate-${sub.product_slug}` ? 'Reactivating...' : 'Reactivate' }}
                </button>

                <button
                  v-if="sub.status === 'past_due'"
                  :disabled="actionLoading === `fix-${sub.product_slug}`"
                  class="btn-ghost text-xs text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 font-medium"
                  @click="handleFixPayment(sub.product_slug)"
                >
                  {{ actionLoading === `fix-${sub.product_slug}` ? 'Opening...' : 'Fix Payment' }}
                </button>
              </div>
            </div>

            <!-- M1: Plan Details (expandable — sibling of flex row, child of card) -->
            <div
              v-if="expandedSubSlug === sub.product_slug"
              class="mt-4 pt-4 border-t border-border"
            >
              <!-- Loading skeleton for detail -->
              <div v-if="subDetailLoading === sub.product_slug" class="space-y-3 animate-pulse">
                <div class="h-4 w-32 rounded bg-[var(--color-muted)]"></div>
                <div class="grid grid-cols-2 gap-2">
                  <div v-for="i in 4" :key="i" class="h-8 rounded bg-[var(--color-muted)]"></div>
                </div>
              </div>

              <!-- Detail content -->
              <template v-else-if="subDetails.get(sub.product_slug)">
                <div class="space-y-4">
                  <!-- Plan Features -->
                  <div v-if="Object.keys(subDetails.get(sub.product_slug)!.plan.features).length > 0">
                    <h4 class="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted-foreground)] mb-2">Plan Features</h4>
                    <div class="grid gap-1.5 sm:grid-cols-2">
                      <div
                        v-for="(value, key) in subDetails.get(sub.product_slug)!.plan.features"
                        :key="key"
                        class="flex items-start gap-2 text-sm"
                      >
                        <svg class="h-4 w-4 shrink-0 mt-0.5 text-brand-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                        </svg>
                        <div class="min-w-0">
                          <span class="font-medium text-foreground">{{ key }}</span>
                          <span class="text-[var(--color-muted-foreground)]">: {{ value }}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Access Entries -->
                  <div v-if="subDetails.get(sub.product_slug)!.plan.access_entries.length > 0">
                    <h4 class="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted-foreground)] mb-2">Access Limits</h4>
                    <div class="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                      <div
                        v-for="entry in subDetails.get(sub.product_slug)!.plan.access_entries"
                        :key="entry.key"
                        class="flex items-center justify-between rounded-lg border border-border px-3 py-2"
                      >
                        <div class="min-w-0">
                          <p class="text-sm font-medium truncate">{{ entry.key }}</p>
                          <p v-if="entry.description" class="text-xs text-[var(--color-muted-foreground)] truncate">{{ entry.description }}</p>
                        </div>
                        <span
                          class="ml-2 shrink-0 text-sm font-semibold"
                          :class="typeof entry.value === 'boolean'
                            ? (entry.value ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]')
                            : 'text-foreground'
                          "
                        >
                          {{ typeof entry.value === 'boolean' ? (entry.value ? 'Yes' : 'No') : entry.value }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Current Access Map (actual values the user has) -->
                  <div v-if="Object.keys(subDetails.get(sub.product_slug)!.access).length > 0">
                    <h4 class="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted-foreground)] mb-2">Your Current Access</h4>
                    <div class="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
                      <div
                        v-for="(value, key) in subDetails.get(sub.product_slug)!.access"
                        :key="key"
                        class="flex items-center justify-between rounded-lg border border-border px-3 py-2"
                      >
                        <span class="text-sm text-[var(--color-muted-foreground)] truncate">{{ key }}</span>
                        <span
                          class="ml-2 shrink-0 text-sm font-semibold"
                          :class="typeof value === 'boolean'
                            ? (value ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]')
                            : 'text-foreground'
                          "
                        >
                          {{ typeof value === 'boolean' ? (value ? 'Yes' : 'No') : value }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Plan metadata summary -->
                  <div class="flex flex-wrap items-center gap-4 text-xs text-[var(--color-muted-foreground)]">
                    <span>
                      <span class="font-medium">Price:</span>
                      {{ subDetails.get(sub.product_slug)!.plan.is_free ? 'Free' : formatPrice(subDetails.get(sub.product_slug)!.plan.price_cents, subDetails.get(sub.product_slug)!.plan.currency) + '/' + (subDetails.get(sub.product_slug)!.plan.billing_cycle === 'monthly' ? 'mo' : subDetails.get(sub.product_slug)!.plan.billing_cycle === 'yearly' ? 'yr' : 'lifetime') }}
                    </span>
                    <span v-if="subDetails.get(sub.product_slug)!.plan.trial_days > 0">
                      <span class="font-medium">Trial:</span> {{ subDetails.get(sub.product_slug)!.plan.trial_days }} days
                    </span>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Products Catalog -->
      <div>
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold">Available Products</h2>
          <span class="text-sm text-[var(--color-muted-foreground)]">
            {{ products.length }} product{{ products.length !== 1 ? 's' : '' }}
          </span>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <a
            v-for="product in products"
            :key="product.id"
            :href="`/dashboard/billing/plans/${product.slug}`"
            class="card group p-6 transition-all duration-200 hover:shadow-md hover:border-brand-300 dark:hover:border-brand-700"
          >
            <div class="flex items-start gap-4">
              <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl gradient-brand text-white text-lg font-bold shadow-md shadow-brand-600/20 transition-transform duration-150 group-hover:scale-110">
                {{ product.name.split(' ').map(w => w[0]).join('').slice(0, 2) }}
              </div>
              <div class="flex-1 min-w-0">
                <h3 class="font-semibold group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">
                  {{ product.name }}
                </h3>
                <p class="mt-1 text-sm text-[var(--color-muted-foreground)] line-clamp-2">
                  {{ product.description || 'No description available.' }}
                </p>
                <div class="mt-3 flex items-center gap-2 text-xs text-brand-600 dark:text-brand-400 font-medium">
                  <span>View plans</span>
                  <svg class="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
            </div>
          </a>
        </div>
      </div>

      <!-- UX-03: Currency Mismatch Recovery Banner -->
      <div
        v-if="currencyMismatch"
        class="mb-6 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 p-4"
      >
        <div class="flex items-start gap-3">
          <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/50">
            <svg class="h-4 w-4 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div class="flex-1">
            <h3 class="text-sm font-semibold text-blue-800 dark:text-blue-300">Currency Mismatch Detected</h3>
            <p class="mt-1 text-sm text-blue-700 dark:text-blue-400">
              Your billing account uses <strong>{{ lockedCurrency.toUpperCase() }}</strong>.
              Switch pricing to {{ lockedCurrency.toUpperCase() }} to continue.
            </p>
            <!-- UX-10 Part 2 Fix: Added currency mismatch disclaimer about approximate
                 converted prices. Previously, the banner only showed the recovery action
                 without explaining that converted prices are estimates. This matches
                 the disclaimer already shown on PlanComparison.vue. -->
            <p class="mt-1 text-xs text-blue-600/70 dark:text-blue-400/70">
              Prices shown in other currencies are approximate. Final charges are processed in {{ lockedCurrency.toUpperCase() }}.
            </p>
            <button class="btn-primary text-xs mt-2" @click="switchCurrency(lockedCurrency)">
              Switch to {{ lockedCurrency.toUpperCase() }}
            </button>
          </div>
        </div>
      </div>

      <!-- Billing History (F11 — pulled from Stripe) -->
      <div v-if="hasPaidSubscription" class="mt-8">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-3">
            <h2 class="text-lg font-semibold">Billing History</h2>
            <a
              href="/dashboard/billing/transactions"
              class="text-sm text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 font-medium flex items-center gap-1 transition-colors"
            >
              View all
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </a>
          </div>
          <button
            v-if="transactionsHasMore"
            :disabled="transactionsLoading"
            class="btn-secondary text-xs"
            @click="loadTransactions"
          >
            {{ transactionsLoading ? 'Loading...' : 'Load More' }}
          </button>
        </div>

        <div v-if="transactions.length === 0 && !transactionsLoading" class="card flex flex-col items-center justify-center py-12 text-center px-6">
          <p class="text-sm text-[var(--color-muted-foreground)]">
            No billing history available yet.
          </p>
        </div>

        <div v-else class="space-y-2">
          <div
            v-for="tx in transactions"
            :key="tx.id"
            class="card p-4 flex items-center justify-between gap-4"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span
                  class="text-sm font-medium truncate"
                  :class="{
                    'text-green-700 dark:text-green-400': tx.status === 'paid',
                    'text-orange-600 dark:text-orange-400': tx.status === 'open',
                    'text-red-600 dark:text-red-400': tx.status === 'uncollectible',
                    'text-[var(--color-muted-foreground)]': tx.status === 'draft',
                  }"
                >
                  {{ tx.status === 'paid' ? 'Paid' : tx.status === 'draft' ? 'Pending' : tx.status }}
                </span>
                <span v-if="tx.number" class="text-xs text-[var(--color-muted-foreground)]">
                  #{{ tx.number }}
                </span>
                <span v-if="tx.card_brand" class="text-xs text-[var(--color-muted-foreground)]">
                  • {{ tx.card_brand }} **** {{ tx.payment_method }}
                </span>
              </div>
              <div class="text-sm text-[var(--color-muted-foreground)]">
                {{ tx.description || (tx.type === 'invoice' ? 'Invoice' : 'Charge') }}
                <span v-if="tx.period_start" class="ml-2 text-xs">
                  ({{ formatDate(tx.period_start) }} – {{ formatDate(tx.period_end) }})
                </span>
              </div>
            </div>
            <div class="flex items-center gap-3 shrink-0">
              <div class="text-right">
                <span class="text-sm font-semibold">
                  {{ formatPrice(Math.round(tx.amount_paid * 100), tx.currency) }}
                </span>
                <span v-if="tx.tax > 0" class="text-xs text-[var(--color-muted-foreground)] ml-1">
                  + {{ formatPrice(Math.round(tx.tax * 100), tx.currency) }} tax
                </span>
              </div>
              <!-- UX-14 Fix: Added PDF download button using tx.pdf_url.
                   Previously, only hosted_url (Stripe invoice page) was rendered.
                   Users had no way to download the PDF directly from the UI. -->
              <div class="flex items-center gap-2 shrink-0">
                <a
                  v-if="tx.pdf_url"
                  :href="tx.pdf_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="btn-ghost text-xs text-[var(--color-muted-foreground)] hover:text-foreground"
                  title="Download PDF"
                >
                  <svg class="h-3.5 w-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  PDF
                </a>
                <a
                  v-if="tx.hosted_url"
                  :href="tx.hosted_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="btn-ghost text-xs text-brand-600 dark:text-brand-400 hover:text-brand-700"
                >
                  View
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
      <!-- A11Y-01: Cancel Subscription Modal with ARIA attributes -->
      <Teleport to="body">
        <div
          v-if="showCancelModal && cancelModalSub"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          @click.self="closeCancelModal"
          role="presentation"
        >
          <div
            ref="modalRef"
            class="w-full max-w-md rounded-xl bg-white dark:bg-gray-900 shadow-2xl p-6"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cancel-modal-title"
          >
            <!-- Header -->
            <div class="flex items-center gap-3 mb-4">
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/50">
                <svg class="h-5 w-5 text-red-600 dark:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
              </div>
              <div>
                <h3 id="cancel-modal-title" class="text-lg font-semibold">Cancel Subscription?</h3>
                <p class="text-sm text-[var(--color-muted-foreground)]">
                  {{ cancelModalSub.product_name }} — {{ cancelModalSub.plan_name }} Plan
                </p>
              </div>
            </div>

            <!-- Consequences -->
            <div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-muted)]/30 p-4 mb-4">
              <h4 class="text-sm font-medium mb-2">What happens when you cancel:</h4>
              <ul class="space-y-2 text-sm text-[var(--color-muted-foreground)]">
                <li class="flex items-start gap-2">
                  <svg class="mt-0.5 h-4 w-4 shrink-0 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
                  You keep access until <strong>{{ cancelModalSub.current_period_end ? formatDate(cancelModalSub.current_period_end) : 'the end of your billing period' }}</strong>
                </li>
                <li class="flex items-start gap-2">
                  <svg class="mt-0.5 h-4 w-4 shrink-0 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                  <span>You will be downgraded to the free plan after that date</span>
                </li>
                <li class="flex items-start gap-2">
                  <svg class="mt-0.5 h-4 w-4 shrink-0 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  <span>You can reactivate at any time before the period ends</span>
                </li>
              </ul>
            </div>

            <!-- Feedback form -->
            <div class="mb-4">
              <label class="block text-sm font-medium mb-1.5">Why are you canceling?</label>
              <select id="cancel-reason" v-model="cancelReason" aria-label="Cancellation reason" class="w-full rounded-lg border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500">
                <option value="">Select a reason (optional)</option>
                <option value="too_expensive">Too expensive</option>
                <option value="missing_features">Missing features I need</option>
                <option value="switching">Switching to another service</option>
                <option value="not_using">Not using it enough</option>
                <option value="other">Other</option>
              </select>
            </div>

            <!-- Actions -->
            <div class="flex items-center gap-2">
              <button
                class="btn-secondary flex-1"
                @click="closeCancelModal"
              >
                Keep My Plan
              </button>
              <button
                :disabled="actionLoading && actionLoading.startsWith('cancel-')"
                class="flex-1 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors disabled:opacity-60"
                @click="executeCancelModal"
              >
                {{ (actionLoading && actionLoading.startsWith('cancel-')) ? 'Canceling...' : 'Cancel Anyway' }}
              </button>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
</template>
