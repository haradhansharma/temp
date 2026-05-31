<script setup lang="ts">
/**
 * SubscriptionDetailAdmin — Subscription detail page for /admin/subscriptions/:id.
 *
 * Features:
 *   - Subscription info card (user, plan, product, status, period, trial, Stripe)
 *   - Tab navigation: Overview | Plan Changes | Invoices | Refunds
 *   - Overview tab: subscription info, override form, extend form, cancel/expire
 *   - Plan Changes tab: chronological table of plan changes
 *   - Invoices tab: table of invoices with view hosted URL
 *   - Refunds tab: table of refunds with status badges
 *   - Override modal (change plan, status, period end)
 *   - Extend modal (extend by N days)
 *   - Cancel/Expire confirmation dialogs
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable,
 * AdminConfirmDialog, AdminStatusBadge, AdminEmptyState.
 */

import { ref, computed, onMounted, watch, onUnmounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { adminApi, formatDateTime } from "@/lib/admin";
import type {
  SubscriptionDetail,
  SubscriptionOverridePayload,
  SubscriptionExtendPayload,
  PlanChangeItem,
  InvoiceItem,
  RefundItem,
  PlanItem,
  IssueRefundPayload,
} from "@/lib/admin";

import AdminPageHeader from "@/components/admin/AdminPageHeader.vue";
import AdminDataTable from "@/components/admin/AdminDataTable.vue";
import type { ColumnDef } from "@/components/admin/AdminDataTable.vue";
import AdminConfirmDialog from "@/components/admin/AdminConfirmDialog.vue";
import AdminStatusBadge from "@/components/admin/AdminStatusBadge.vue";
import AdminEmptyState from "@/components/admin/AdminEmptyState.vue";

// ─── Props & Route ID ────────────────────────────────────────────────────────
//
// With Astro ClientRouter (View Transitions) + client:only="vue", the Astro
// prop can become undefined during client-side page swaps.  We therefore read
// the subscription ID from the URL path as the primary source, with the Astro
// prop as a fallback for direct (full-page) loads.

const props = defineProps<{
  subscriptionId?: number;
}>();

/** Extract subscription ID from /admin/subscriptions/:id URL path. */
function getSubscriptionIdFromUrl(): number | undefined {
  const match = window.location.pathname.match(/\/admin\/subscriptions\/(\d+)/);
  return match ? Number(match[1]) : undefined;
}

const subscriptionId = computed(() => {
  // URL is the most reliable source during View Transition navigations
  const fromUrl = getSubscriptionIdFromUrl();
  if (fromUrl) return fromUrl;
  // Fallback to Astro prop (works on direct full-page loads)
  return props.subscriptionId;
});

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const loadError = ref<string | null>(null);
const actionLoading = ref<string | null>(null);

const subscription = ref<SubscriptionDetail | null>(null);
const activeTab = ref<"overview" | "plan-changes" | "invoices" | "refunds">("overview");

// Tab data (lazy-loaded)
const planChanges = ref<PlanChangeItem[]>([]);
const planChangesLoading = ref(false);
const planChangesLoaded = ref(false);

const invoices = ref<InvoiceItem[]>([]);
const invoicesLoading = ref(false);
const invoicesLoaded = ref(false);

const refunds = ref<RefundItem[]>([]);
const refundsLoading = ref(false);
const refundsLoaded = ref(false);

// Available plans for override dropdown
const availablePlans = ref<PlanItem[]>([]);
const plansLoading = ref(false);

// Override modal
const showOverrideModal = ref(false);
const overrideLoading = ref(false);
const overrideError = ref<string | null>(null);
const overrideForm = ref<{
  plan_id: number | null;
  status: string;
  current_period_end: string;
}>({
  plan_id: null,
  status: "",
  current_period_end: "",
});

// Extend modal
const showExtendModal = ref(false);
const extendLoading = ref(false);
const extendError = ref<string | null>(null);
const extendForm = ref({
  extend_days: 30,
});

// Confirmation dialogs
const showCancelDialog = ref(false);
const showExpireDialog = ref(false);

// Issue Refund modal
const showRefundModal = ref(false);
const refundLoading = ref(false);
const refundError = ref<string | null>(null);
const refundForm = ref<{
  amount_cents: number | null;
  reason: string;
  reason_category: string;
  admin_notes: string;
}>({
  amount_cents: null,
  reason: "",
  reason_category: "",
  admin_notes: "",
});

const REFUND_REASON_CATEGORIES = [
  { value: "customer_request", label: "Customer Request" },
  { value: "billing_error", label: "Billing Error" },
  { value: "goodwill", label: "Goodwill" },
  { value: "policy", label: "Policy" },
  { value: "chargeback", label: "Chargeback" },
];

/** Whether a refund can be issued for this subscription. */
const canIssueRefund = computed(() => {
  if (!subscription.value) return false;
  // Must have a Stripe subscription to refund
  return !!subscription.value.stripe_subscription_id
    && ["active", "trialing", "past_due", "canceled"].includes(subscription.value.status);
});

// ─── Valid subscription statuses ─────────────────────────────────────────────

const subscriptionStatuses = [
  "active",
  "trialing",
  "past_due",
  "canceled",
  "expired",
  "paused",
] as const;

/** Statuses that allow cancel/expire actions */
const cancellableStatuses = ["active", "trialing", "past_due"] as const;
const expirableStatuses = ["active", "trialing", "past_due", "paused"] as const;

const canCancel = computed(() => {
  if (!subscription.value) return false;
  return (cancellableStatuses as readonly string[]).includes(subscription.value.status);
});

const canExpire = computed(() => {
  if (!subscription.value) return false;
  return (expirableStatuses as readonly string[]).includes(subscription.value.status);
});

// ─── Column definitions ──────────────────────────────────────────────────────

const planChangeColumns = computed<ColumnDef[]>(() => [
  { key: "from_plan_name", label: "From Plan", sortable: true },
  { key: "to_plan_name", label: "To Plan", sortable: true },
  { key: "proration_amount_cents", label: "Proration", align: "right", width: "110px" },
  { key: "created_at", label: "Date", width: "160px", hideOnMobile: true },
  { key: "initiated_by_email", label: "Initiated By", width: "130px", hideOnMobile: true },
]);

const invoiceColumns = computed<ColumnDef[]>(() => [
  { key: "number", label: "Invoice #", sortable: true },
  { key: "amount_paid_cents", label: "Amount", align: "right", width: "110px" },
  { key: "status", label: "Status", align: "center", width: "110px" },
  { key: "created_at", label: "Date", width: "160px", hideOnMobile: true },
  { key: "actions", label: "", align: "right", width: "80px" },
]);

const refundColumns = computed<ColumnDef[]>(() => [
  { key: "amount_cents", label: "Amount", align: "right", width: "110px" },
  { key: "status", label: "Status", align: "center", width: "110px" },
  { key: "reason_category", label: "Reason", hideOnMobile: true },
  { key: "initiated_by_email", label: "Initiated By", width: "130px", hideOnMobile: true },
  { key: "approved_by_email", label: "Approved By", width: "130px", hideOnMobile: true },
  { key: "created_at", label: "Date", width: "160px" },
]);

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchSubscription() {
  const id = subscriptionId.value;
  if (!id) {
    loadError.value = "Invalid subscription ID.";
    loading.value = false;
    return;
  }
  loading.value = true;
  loadError.value = null;
  try {
    subscription.value = await adminApi.getSubscription(id);
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

async function fetchPlanChanges() {
  const id = subscriptionId.value;
  if (!id) return;
  planChangesLoading.value = true;
  try {
    planChanges.value = await adminApi.getSubscriptionPlanChanges(id);
    planChangesLoaded.value = true;
  } catch (err) {
    console.warn("Failed to load plan changes:", err);
  } finally {
    planChangesLoading.value = false;
  }
}

async function fetchInvoices() {
  const id = subscriptionId.value;
  if (!id) return;
  invoicesLoading.value = true;
  try {
    invoices.value = await adminApi.getSubscriptionInvoices(id);
    invoicesLoaded.value = true;
  } catch (err) {
    console.warn("Failed to load invoices:", err);
  } finally {
    invoicesLoading.value = false;
  }
}

async function fetchRefunds() {
  const id = subscriptionId.value;
  if (!id) return;
  refundsLoading.value = true;
  try {
    refunds.value = await adminApi.getSubscriptionRefunds(id);
    refundsLoaded.value = true;
  } catch (err) {
    console.warn("Failed to load refunds:", err);
  } finally {
    refundsLoading.value = false;
  }
}

async function fetchAvailablePlans() {
  if (!subscription.value) return;
  plansLoading.value = true;
  try {
    const response = await adminApi.listPlans(subscription.value.product_id);
    availablePlans.value = response.results;
  } catch (err) {
    console.warn("Failed to load plans:", err);
  } finally {
    plansLoading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchSubscription();
  // Check URL for tab parameter
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("tab");
  if (tab === "plan-changes" || tab === "invoices" || tab === "refunds") {
    activeTab.value = tab;
    window.history.replaceState({}, "", window.location.pathname);
  }
});

// Re-fetch when navigating between subscription detail pages via View Transitions.
// astro:page-load fires on every navigation (initial + client-side swaps).
function handlePageLoad() {
  const newId = getSubscriptionIdFromUrl();
  if (newId && newId !== subscription.value?.id) {
    // Reset state for the new subscription
    activeTab.value = "overview";
    planChangesLoaded.value = false;
    invoicesLoaded.value = false;
    refundsLoaded.value = false;
    planChanges.value = [];
    invoices.value = [];
    refunds.value = [];
    fetchSubscription();
  }
  // Also check for ?tab= on client-side navigations
  const params = new URLSearchParams(window.location.search);
  const tab = params.get("tab");
  if (tab === "plan-changes" || tab === "invoices" || tab === "refunds") {
    activeTab.value = tab;
    window.history.replaceState({}, "", window.location.pathname);
  }
}
document.addEventListener("astro:page-load", handlePageLoad);
onUnmounted(() => {
  document.removeEventListener("astro:page-load", handlePageLoad);
});

// Lazy-load tab data when tab is selected
watch(activeTab, (tab) => {
  if (tab === "plan-changes" && !planChangesLoaded.value) {
    fetchPlanChanges();
  } else if (tab === "invoices" && !invoicesLoaded.value) {
    fetchInvoices();
  } else if (tab === "refunds" && !refundsLoaded.value) {
    fetchRefunds();
  }
});

// ─── Format helpers ──────────────────────────────────────────────────────────

function formatCents(cents: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency?.toUpperCase() || "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

/** Format proration amount (already in cents) */
function formatProration(amount: number): string {
  // Proration amounts can be negative
  const prefix = amount < 0 ? "-" : "";
  return prefix + formatCents(Math.abs(amount), "usd");
}

/** Format date only (no time) */
function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const locale =
    typeof navigator !== "undefined" ? navigator.language : "en-US";
  return new Date(dateStr).toLocaleDateString(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ─── Override Subscription ──────────────────────────────────────────────────

function openOverrideModal() {
  if (!subscription.value) return;
  overrideForm.value = {
    plan_id: subscription.value.plan_id,
    status: subscription.value.status,
    current_period_end: subscription.value.current_period_end
      ? new Date(subscription.value.current_period_end).toISOString().slice(0, 10)
      : "",
  };
  overrideError.value = null;
  showOverrideModal.value = true;
  // Load available plans for the product
  fetchAvailablePlans();
}

async function handleOverrideSubmit() {
  overrideLoading.value = true;
  overrideError.value = null;
  try {
    const payload: SubscriptionOverridePayload = {};
    if (overrideForm.value.plan_id && overrideForm.value.plan_id !== subscription.value?.plan_id) {
      payload.plan_id = overrideForm.value.plan_id;
    }
    if (overrideForm.value.status && overrideForm.value.status !== subscription.value?.status) {
      payload.status = overrideForm.value.status;
    }
    if (overrideForm.value.current_period_end) {
      const newEnd = overrideForm.value.current_period_end;
      const currentEnd = subscription.value?.current_period_end
        ? new Date(subscription.value.current_period_end).toISOString().slice(0, 10)
        : "";
      if (newEnd !== currentEnd) {
        payload.period_end = new Date(newEnd).toISOString();
      }
    }

    // Only submit if there are changes
    if (Object.keys(payload).length === 0) {
      overrideError.value = "No changes detected.";
      overrideLoading.value = false;
      return;
    }

    await adminApi.overrideSubscription(subscriptionId.value!, payload);
    showToast("Subscription overridden.", "success");
    showOverrideModal.value = false;
    await fetchSubscription();
    // Invalidate tab data since overrides may affect plan changes/invoices
    planChangesLoaded.value = false;
    invoicesLoaded.value = false;
    refundsLoaded.value = false;
  } catch (err) {
    overrideError.value = getErrorMessage(err);
  } finally {
    overrideLoading.value = false;
  }
}

// ─── Extend Subscription ────────────────────────────────────────────────────

function openExtendModal() {
  extendForm.value = { extend_days: 30 };
  extendError.value = null;
  showExtendModal.value = true;
}

async function handleExtendSubmit() {
  if (!extendForm.value.extend_days || extendForm.value.extend_days <= 0) {
    extendError.value = "Enter a positive number of days.";
    return;
  }
  extendLoading.value = true;
  extendError.value = null;
  try {
    const payload: SubscriptionExtendPayload = {
      days: extendForm.value.extend_days,
    };
    await adminApi.extendSubscription(subscriptionId.value!, payload);
    showToast(`Subscription extended by ${extendForm.value.extend_days} day${extendForm.value.extend_days !== 1 ? "s" : ""}.`, "success");
    showExtendModal.value = false;
    await fetchSubscription();
    // Invalidate tab data
    invoicesLoaded.value = false;
  } catch (err) {
    extendError.value = getErrorMessage(err);
  } finally {
    extendLoading.value = false;
  }
}

// ─── Cancel Subscription ────────────────────────────────────────────────────

async function confirmCancel() {
  actionLoading.value = "cancel";
  try {
    await adminApi.cancelSubscription(subscriptionId.value!);
    showToast("Subscription canceled.", "success");
    showCancelDialog.value = false;
    await fetchSubscription();
    // Invalidate tab data
    planChangesLoaded.value = false;
    invoicesLoaded.value = false;
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Expire Subscription ────────────────────────────────────────────────────

async function confirmExpire() {
  actionLoading.value = "expire";
  try {
    await adminApi.expireSubscription(subscriptionId.value!);
    showToast("Subscription expired.", "success");
    showExpireDialog.value = false;
    await fetchSubscription();
    // Invalidate tab data
    planChangesLoaded.value = false;
    invoicesLoaded.value = false;
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Issue Refund ─────────────────────────────────────────────────────────

function openRefundModal() {
  refundForm.value = {
    amount_cents: null,
    reason: "",
    reason_category: "",
    admin_notes: "",
  };
  refundError.value = null;
  showRefundModal.value = true;
}

async function handleRefundSubmit() {
  if (!subscriptionId.value) return;
  refundLoading.value = true;
  refundError.value = null;
  try {
    const payload: IssueRefundPayload = {};
    if (refundForm.value.amount_cents && refundForm.value.amount_cents > 0) {
      payload.amount_cents = refundForm.value.amount_cents;
    }
    if (refundForm.value.reason) {
      payload.reason = refundForm.value.reason;
    }
    if (refundForm.value.reason_category) {
      payload.reason_category = refundForm.value.reason_category;
    }
    if (refundForm.value.admin_notes) {
      payload.admin_notes = refundForm.value.admin_notes;
    }

    const result = await adminApi.issueRefund(subscriptionId.value, payload);
    showToast(result.message || "Refund issued successfully.", "success");
    showRefundModal.value = false;
    // Invalidate refund data so it re-fetches
    refundsLoaded.value = false;
    await fetchRefunds();
  } catch (err) {
    refundError.value = getErrorMessage(err);
  } finally {
    refundLoading.value = false;
  }
}

// ─── Escape key handler for modals ──────────────────────────────────────────

function handleModalKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (showOverrideModal.value) showOverrideModal.value = false;
    else if (showExtendModal.value) showExtendModal.value = false;
    else if (showRefundModal.value) showRefundModal.value = false;
  }
}

onMounted(() => {
  document.addEventListener("keydown", handleModalKeydown);
});
onUnmounted(() => {
  document.removeEventListener("keydown", handleModalKeydown);
});
</script>

<template>
  <div class="space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="space-y-6 animate-pulse">
      <div class="h-8 w-64 rounded skeleton" />
      <div class="h-48 rounded skeleton" />
    </div>

    <!-- Error -->
    <div
      v-else-if="loadError"
      class="card flex flex-col items-center gap-4 p-10 text-center"
    >
      <svg class="h-12 w-12 text-destructive/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <p class="font-medium text-foreground">Failed to load subscription</p>
      <p class="text-sm text-muted-foreground">{{ loadError }}</p>
      <button type="button" class="btn-secondary" @click="fetchSubscription">Try again</button>
    </div>

    <!-- Subscription detail -->
    <template v-else-if="subscription">
      <!-- Page Header -->
      <AdminPageHeader
        :title="`Subscription #${subscription.id}`"
        :description="`${subscription.user_email} — ${subscription.product_name}`"
        :breadcrumbs="[
          { label: 'Admin', href: '/admin' },
          { label: 'Subscriptions', href: '/admin/subscriptions' },
          { label: `#${subscription.id}` },
        ]"
      >
        <template #secondary-action>
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            @click="openOverrideModal"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Override
          </button>
        </template>
        <template #primary-action>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="btn-secondary inline-flex items-center gap-2"
              @click="openExtendModal"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Extend
            </button>
            <button
              v-if="canCancel"
              type="button"
              class="btn-secondary inline-flex items-center gap-2 text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-950"
              :disabled="actionLoading === 'cancel'"
              @click="showCancelDialog = true"
            >
              <svg v-if="actionLoading === 'cancel'" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
              Cancel
            </button>
            <button
              v-if="canExpire"
              type="button"
              class="btn-secondary inline-flex items-center gap-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
              :disabled="actionLoading === 'expire'"
              @click="showExpireDialog = true"
            >
              <svg v-if="actionLoading === 'expire'" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Expire
            </button>
          </div>
        </template>
      </AdminPageHeader>

      <!-- Info Card -->
      <div class="card p-5">
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">User</p>
            <p class="mt-1 text-sm font-medium text-foreground">{{ subscription.user_name }}</p>
            <p class="text-xs text-muted-foreground">{{ subscription.user_email }}</p>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Product / Plan</p>
            <p class="mt-1 text-sm font-medium text-foreground">{{ subscription.product_name }}</p>
            <p class="text-xs text-muted-foreground">{{ subscription.plan_name }}</p>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Status</p>
            <div class="mt-1">
              <AdminStatusBadge :status="subscription.status" type="subscription" />
            </div>
            <p
              v-if="subscription.cancel_at_period_end"
              class="mt-1 text-xs text-amber-600 dark:text-amber-400"
            >
              Cancels at period end
            </p>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Current Period</p>
            <p class="mt-1 text-sm text-foreground">
              {{ formatDate(subscription.current_period_start) }}
              <span class="text-muted-foreground">&rarr;</span>
              {{ formatDate(subscription.current_period_end) }}
            </p>
          </div>
        </div>
        <!-- Second row: trial + Stripe info -->
        <div
          v-if="subscription.trial_start || subscription.trial_end || subscription.stripe_subscription_id"
          class="mt-4 grid grid-cols-1 gap-4 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <div v-if="subscription.trial_start">
            <p class="text-xs font-medium uppercase text-muted-foreground">Trial Period</p>
            <p class="mt-1 text-sm text-foreground">
              {{ formatDate(subscription.trial_start) }}
              <span class="text-muted-foreground">&rarr;</span>
              {{ formatDate(subscription.trial_end) }}
            </p>
          </div>
          <div v-if="subscription.stripe_subscription_id">
            <p class="text-xs font-medium uppercase text-muted-foreground">Stripe Subscription</p>
            <p class="mt-1 text-sm text-foreground font-mono">
              {{ subscription.stripe_subscription_id }}
            </p>
          </div>
        </div>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Tab Navigation                                                        -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div class="border-b border-border">
        <nav class="flex gap-6" aria-label="Subscription tabs">
          <button
            v-for="tab in (['overview', 'plan-changes', 'invoices', 'refunds'] as const)"
            :key="tab"
            class="border-b-2 pb-3 text-sm font-medium transition-colors"
            :class="
              activeTab === tab
                ? 'border-brand-600 text-brand-600 dark:border-brand-400 dark:text-brand-400'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            "
            @click="activeTab = tab"
          >
            {{
              tab === 'overview'
                ? 'Overview'
                : tab === 'plan-changes'
                  ? 'Plan Changes'
                  : tab === 'invoices'
                    ? 'Invoices'
                    : 'Refunds'
            }}
            <span
              v-if="tab === 'plan-changes' && planChangesLoaded && planChanges.length"
              class="ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-muted px-1.5 text-[10px] font-semibold text-foreground"
            >
              {{ planChanges.length }}
            </span>
            <span
              v-if="tab === 'invoices' && invoicesLoaded && invoices.length"
              class="ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-muted px-1.5 text-[10px] font-semibold text-foreground"
            >
              {{ invoices.length }}
            </span>
            <span
              v-if="tab === 'refunds' && refundsLoaded && refunds.length"
              class="ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-muted px-1.5 text-[10px] font-semibold text-foreground"
            >
              {{ refunds.length }}
            </span>
          </button>
        </nav>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Overview Tab                                                           -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div v-if="activeTab === 'overview'">
        <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <!-- Subscription Details -->
          <div class="card p-5">
            <h3 class="text-sm font-semibold text-foreground mb-4">Subscription Details</h3>
            <dl class="space-y-3">
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">ID</dt>
                <dd class="text-sm font-mono text-foreground">#{{ subscription.id }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">User</dt>
                <dd class="text-sm text-foreground">
                  <a
                    :href="`/admin/users/${subscription.user_id}`"
                    class="text-brand-600 hover:underline dark:text-brand-400"
                  >
                    {{ subscription.user_name }}
                  </a>
                </dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Email</dt>
                <dd class="text-sm text-foreground">{{ subscription.user_email }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Product</dt>
                <dd class="text-sm text-foreground">{{ subscription.product_name }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Plan</dt>
                <dd class="text-sm text-foreground">{{ subscription.plan_name }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Status</dt>
                <dd><AdminStatusBadge :status="subscription.status" type="subscription" /></dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Period Start</dt>
                <dd class="text-sm text-foreground">{{ formatDateTime(subscription.current_period_start) }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Period End</dt>
                <dd class="text-sm text-foreground">{{ formatDateTime(subscription.current_period_end) }}</dd>
              </div>
              <div v-if="subscription.cancel_at_period_end" class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-amber-600 dark:text-amber-400">Cancel at Period End</dt>
                <dd class="text-sm font-medium text-amber-600 dark:text-amber-400">Yes</dd>
              </div>
              <div v-if="subscription.trial_start" class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Trial Start</dt>
                <dd class="text-sm text-foreground">{{ formatDateTime(subscription.trial_start) }}</dd>
              </div>
              <div v-if="subscription.trial_end" class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Trial End</dt>
                <dd class="text-sm text-foreground">{{ formatDateTime(subscription.trial_end) }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Created</dt>
                <dd class="text-sm text-foreground">{{ formatDateTime(subscription.created_at) }}</dd>
              </div>
            </dl>
          </div>

          <!-- Quick Actions -->
          <div class="space-y-4">
            <div class="card p-5">
              <h3 class="text-sm font-semibold text-foreground mb-4">Quick Actions</h3>
              <div class="space-y-3">
                <button
                  type="button"
                  class="w-full btn-secondary inline-flex items-center justify-center gap-2"
                  @click="openOverrideModal"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  Override Subscription
                </button>
                <button
                  type="button"
                  class="w-full btn-secondary inline-flex items-center justify-center gap-2"
                  @click="openExtendModal"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Extend Period
                </button>
                <button
                  v-if="canCancel"
                  type="button"
                  class="w-full btn-secondary inline-flex items-center justify-center gap-2 text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-950"
                  @click="showCancelDialog = true"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                  </svg>
                  Cancel Subscription
                </button>
                <button
                  v-if="canExpire"
                  type="button"
                  class="w-full btn-secondary inline-flex items-center justify-center gap-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                  @click="showExpireDialog = true"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Expire Subscription
                </button>
                <button
                  v-if="canIssueRefund"
                  type="button"
                  class="w-full btn-secondary inline-flex items-center justify-center gap-2 text-orange-600 hover:bg-orange-50 dark:text-orange-400 dark:hover:bg-orange-950"
                  @click="openRefundModal"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                  </svg>
                  Issue Refund
                </button>
              </div>
            </div>

            <!-- Stripe Info Card -->
            <div v-if="subscription.stripe_subscription_id" class="card p-5">
              <h3 class="text-sm font-semibold text-foreground mb-3">Stripe Integration</h3>
              <div class="flex items-center gap-3">
                <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-600 dark:bg-purple-950 dark:text-purple-400">
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M13.976 9.15c-2.172-.806-3.356-1.426-3.356-2.409 0-.831.683-1.305 1.901-1.305 2.227 0 4.515.858 6.09 1.631l.89-5.494C18.252.975 15.697 0 12.165 0 9.667 0 7.589.654 6.104 1.872 4.56 3.147 3.757 4.992 3.757 7.218c0 4.039 2.467 5.76 6.476 7.219 2.585.92 3.445 1.574 3.445 2.583 0 .98-.84 1.545-2.354 1.545-1.875 0-4.965-.921-7.076-2.304l-.917 5.576C5.018 23.025 7.614 24 11.326 24c2.687 0 4.833-.639 6.355-1.854 1.615-1.267 2.46-3.135 2.46-5.502 0-4.1-2.52-5.82-6.165-7.494z"/>
                  </svg>
                </div>
                <div class="min-w-0">
                  <p class="text-xs font-medium uppercase text-muted-foreground">Subscription ID</p>
                  <p class="truncate text-sm font-mono text-foreground">{{ subscription.stripe_subscription_id }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Plan Changes Tab                                                       -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div v-if="activeTab === 'plan-changes'">
        <!-- Loading -->
        <div v-if="planChangesLoading" class="card animate-pulse p-6">
          <div class="space-y-4">
            <div class="h-4 w-40 rounded skeleton" />
            <div class="h-4 w-full rounded skeleton" />
            <div class="h-4 w-full rounded skeleton" />
          </div>
        </div>

        <template v-else-if="planChangesLoaded">
          <AdminEmptyState
            v-if="planChanges.length === 0"
            title="No plan changes"
            description="This subscription has no plan change history."
            icon="document"
          />

          <AdminDataTable
            v-else
            :columns="planChangeColumns"
            :rows="planChanges as unknown as Record<string, unknown>[]"
            :meta="null"
            :loading="false"
            :clickable="false"
            row-key="id"
            empty-message="No plan changes"
          >
            <!-- From Plan cell -->
            <template #cell-from_plan_name="{ row }">
              <span class="text-foreground">{{ (row as unknown as PlanChangeItem).from_plan_name }}</span>
            </template>

            <!-- To Plan cell -->
            <template #cell-to_plan_name="{ row }">
              <span class="font-medium text-foreground">{{ (row as unknown as PlanChangeItem).to_plan_name }}</span>
            </template>

            <!-- Proration cell -->
            <template #cell-proration_amount_cents="{ row }">
              <span
                class="font-medium"
                :class="(row as unknown as PlanChangeItem).proration_amount_cents < 0 ? 'text-green-600 dark:text-green-400' : 'text-foreground'"
              >
                {{ formatProration((row as unknown as PlanChangeItem).proration_amount_cents) }}
              </span>
            </template>

            <!-- Date cell -->
            <template #cell-created_at="{ row }">
              <span class="text-muted-foreground">{{ formatDateTime((row as unknown as PlanChangeItem).created_at) }}</span>
            </template>

            <!-- Initiated By cell -->
            <template #cell-initiated_by_email="{ row }">
              <span class="text-foreground">{{ (row as unknown as PlanChangeItem).initiated_by_email || "—" }}</span>
            </template>
          </AdminDataTable>
        </template>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Invoices Tab                                                           -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div v-if="activeTab === 'invoices'">
        <!-- Loading -->
        <div v-if="invoicesLoading" class="card animate-pulse p-6">
          <div class="space-y-4">
            <div class="h-4 w-40 rounded skeleton" />
            <div class="h-4 w-full rounded skeleton" />
            <div class="h-4 w-full rounded skeleton" />
          </div>
        </div>

        <template v-else-if="invoicesLoaded">
          <AdminEmptyState
            v-if="invoices.length === 0"
            title="No invoices"
            description="This subscription has no invoices yet."
            icon="document"
          />

          <AdminDataTable
            v-else
            :columns="invoiceColumns"
            :rows="invoices as unknown as Record<string, unknown>[]"
            :meta="null"
            :loading="false"
            :clickable="false"
            row-key="id"
            empty-message="No invoices"
          >
            <!-- Invoice # cell -->
            <template #cell-number="{ row }">
              <span class="font-medium font-mono text-foreground">{{ (row as unknown as InvoiceItem).number }}</span>
            </template>

            <!-- Amount cell -->
            <template #cell-amount_paid_cents="{ row }">
              <span class="font-medium text-foreground">{{ formatCents((row as unknown as InvoiceItem).amount_paid_cents, (row as unknown as InvoiceItem).currency) }}</span>
            </template>

            <!-- Status cell -->
            <template #cell-status="{ row }">
              <AdminStatusBadge :status="(row as unknown as InvoiceItem).status" type="generic" />
            </template>

            <!-- Date cell -->
            <template #cell-created_at="{ row }">
              <span class="text-muted-foreground">{{ formatDateTime((row as unknown as InvoiceItem).created_at) }}</span>
            </template>

            <!-- Actions cell -->
            <template #cell-actions="{ row }">
              <div class="flex items-center justify-end gap-1" @click.stop>
                <a
                  v-if="(row as unknown as InvoiceItem).hosted_url"
                  :href="(row as unknown as InvoiceItem).hosted_url!"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-brand-600 transition-colors hover:bg-brand-50 dark:text-brand-400 dark:hover:bg-brand-950"
                >
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  View
                </a>
                <span v-else class="text-xs text-muted-foreground">—</span>
              </div>
            </template>
          </AdminDataTable>
        </template>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Refunds Tab                                                            -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div v-if="activeTab === 'refunds'">
        <!-- Issue Refund button -->
        <div v-if="canIssueRefund" class="mb-4 flex justify-end">
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2 text-orange-600 hover:bg-orange-50 dark:text-orange-400 dark:hover:bg-orange-950"
            @click="openRefundModal"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
            </svg>
            Issue Refund
          </button>
        </div>

        <!-- Loading -->
        <div v-if="refundsLoading" class="card animate-pulse p-6">
          <div class="space-y-4">
            <div class="h-4 w-40 rounded skeleton" />
            <div class="h-4 w-full rounded skeleton" />
            <div class="h-4 w-full rounded skeleton" />
          </div>
        </div>

        <template v-else-if="refundsLoaded">
          <AdminEmptyState
            v-if="refunds.length === 0"
            title="No refunds"
            description="This subscription has no refund requests."
            icon="clipboard"
          />

          <AdminDataTable
            v-else
            :columns="refundColumns"
            :rows="refunds as unknown as Record<string, unknown>[]"
            :meta="null"
            :loading="false"
            :clickable="false"
            row-key="id"
            empty-message="No refunds"
          >
            <!-- Amount cell -->
            <template #cell-amount_cents="{ row }">
              <span class="font-medium text-foreground">{{ formatCents((row as unknown as RefundItem).amount_cents, (row as unknown as RefundItem).currency) }}</span>
            </template>

            <!-- Status cell -->
            <template #cell-status="{ row }">
              <AdminStatusBadge :status="(row as unknown as RefundItem).status" type="refund" />
            </template>

            <!-- Reason cell -->
            <template #cell-reason_category="{ row }">
              <span class="text-foreground">{{ (row as unknown as RefundItem).reason_category }}</span>
            </template>

            <!-- Initiated By cell -->
            <template #cell-initiated_by_email="{ row }">
              <span class="text-foreground">{{ (row as unknown as RefundItem).initiated_by_email || "—" }}</span>
            </template>

            <!-- Approved By cell -->
            <template #cell-approved_by_email="{ row }">
              <span class="text-foreground">{{ (row as unknown as RefundItem).approved_by_email || "—" }}</span>
            </template>

            <!-- Date cell -->
            <template #cell-created_at="{ row }">
              <span class="text-muted-foreground">{{ formatDateTime((row as unknown as RefundItem).created_at) }}</span>
            </template>
          </AdminDataTable>
        </template>
      </div>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Override Subscription Modal                                            -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <Teleport to="body">
      <div
        v-if="showOverrideModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="showOverrideModal = false" />
        <div class="relative w-full max-w-xl rounded-xl border border-border bg-card p-6 shadow-xl" role="dialog" aria-modal="true">
          <h2 class="text-lg font-semibold text-foreground">Override Subscription</h2>
          <p class="mt-1 text-sm text-muted-foreground">Change plan, status, or period end for this subscription.</p>
          <form class="mt-5 space-y-4" @submit.prevent="handleOverrideSubmit">
            <!-- Change Plan -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Change Plan</label>
              <select v-model.number="overrideForm.plan_id" class="input-field" :disabled="plansLoading">
                <option :value="subscription?.plan_id" disabled>
                  Current: {{ subscription?.plan_name }}
                </option>
                <option
                  v-for="plan in availablePlans.filter(p => p.id !== subscription?.plan_id)"
                  :key="plan.id"
                  :value="plan.id"
                >
                  {{ plan.name }} ({{ formatCents(plan.price_cents, plan.currency) }}/{{ plan.billing_cycle }})
                </option>
              </select>
              <p v-if="plansLoading" class="mt-1 text-xs text-muted-foreground">Loading plans…</p>
            </div>

            <!-- Change Status -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Change Status</label>
              <select v-model="overrideForm.status" class="input-field">
                <option
                  v-for="s in subscriptionStatuses"
                  :key="s"
                  :value="s"
                >
                  {{ s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) }}
                </option>
              </select>
            </div>

            <!-- Change Period End -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Period End</label>
              <input
                v-model="overrideForm.current_period_end"
                type="date"
                class="input-field"
              />
            </div>

            <div v-if="overrideError" class="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400">{{ overrideError }}</div>
            <div class="flex items-center justify-end gap-3 pt-2">
              <button type="button" class="btn-secondary" :disabled="overrideLoading" @click="showOverrideModal = false">Cancel</button>
              <button type="submit" class="btn-primary" :disabled="overrideLoading">
                <svg v-if="overrideLoading" class="mr-2 h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Apply Override
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Extend Subscription Modal                                              -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <Teleport to="body">
      <div
        v-if="showExtendModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="showExtendModal = false" />
        <div class="relative w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-xl" role="dialog" aria-modal="true">
          <h2 class="text-lg font-semibold text-foreground">Extend Subscription</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Extend the current period end by a specified number of days.
          </p>
          <form class="mt-5 space-y-4" @submit.prevent="handleExtendSubmit">
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Extend by (days) <span class="text-destructive">*</span></label>
              <input
                v-model.number="extendForm.extend_days"
                type="number"
                min="1"
                class="input-field"
                placeholder="30"
                required
              />
              <p class="mt-1 text-xs text-muted-foreground">
                New period end: {{ subscription ? formatDate(new Date(new Date(subscription.current_period_end).getTime() + (extendForm.extend_days || 0) * 86400000).toISOString()) : "—" }}
              </p>
            </div>
            <div v-if="extendError" class="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400">{{ extendError }}</div>
            <div class="flex items-center justify-end gap-3 pt-2">
              <button type="button" class="btn-secondary" :disabled="extendLoading" @click="showExtendModal = false">Cancel</button>
              <button type="submit" class="btn-primary" :disabled="extendLoading">
                <svg v-if="extendLoading" class="mr-2 h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Extend
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Cancel Subscription Dialog                                             -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showCancelDialog"
      title="Cancel Subscription"
      message="Are you sure you want to cancel this subscription?"
      detail="The subscription will be marked as canceled. The user may retain access until the current period ends depending on your cancel_at_period_end setting."
      confirm-label="Cancel Subscription"
      :destructive="true"
      :loading="actionLoading === 'cancel'"
      @confirm="confirmCancel"
      @cancel="showCancelDialog = false"
    />

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Expire Subscription Dialog                                             -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showExpireDialog"
      title="Expire Subscription"
      message="Are you sure you want to expire this subscription immediately?"
      detail="This is a destructive action. The subscription will be expired immediately and the user will lose access. This cannot be undone."
      confirm-label="Expire Immediately"
      :destructive="true"
      :loading="actionLoading === 'expire'"
      @confirm="confirmExpire"
      @cancel="showExpireDialog = false"
    />

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Issue Refund Modal                                                     -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <Teleport to="body">
      <div
        v-if="showRefundModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="showRefundModal = false" />
        <div class="relative w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-xl" role="dialog" aria-modal="true">
          <h2 class="text-lg font-semibold text-foreground">Issue Refund</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Create a refund for this subscription's latest payment. Leave amount blank for a full refund.
          </p>

          <!-- Subscription summary -->
          <div class="mt-4 space-y-2 rounded-lg bg-muted/50 p-3 border border-border">
            <div class="flex justify-between text-xs">
              <span class="text-muted-foreground">User</span>
              <span class="text-foreground">{{ subscription?.user_email }}</span>
            </div>
            <div class="flex justify-between text-xs">
              <span class="text-muted-foreground">Product / Plan</span>
              <span class="text-foreground">{{ subscription?.product_name }} / {{ subscription?.plan_name }}</span>
            </div>
          </div>

          <!-- Two-person rule warning -->
          <div class="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/50">
            <div class="flex items-start gap-2">
              <svg class="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <p class="text-sm font-medium text-amber-800 dark:text-amber-300">Two-Person Rule</p>
                <p class="mt-0.5 text-xs text-amber-700 dark:text-amber-400">
                  After you issue this refund, another admin must approve it before it is finalized.
                </p>
              </div>
            </div>
          </div>

          <form class="mt-5 space-y-4" @submit.prevent="handleRefundSubmit">
            <!-- Amount -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Refund Amount (cents)</label>
              <input
                v-model.number="refundForm.amount_cents"
                type="number"
                min="1"
                class="input-field"
                placeholder="Leave blank for full refund"
              />
              <p class="mt-1 text-xs text-muted-foreground">
                Amount in cents (e.g. 1000 = $10.00). Leave empty to refund the full payment amount.
              </p>
            </div>

            <!-- Reason Category -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Reason Category</label>
              <select v-model="refundForm.reason_category" class="input-field">
                <option value="">Select a category...</option>
                <option
                  v-for="cat in REFUND_REASON_CATEGORIES"
                  :key="cat.value"
                  :value="cat.value"
                >
                  {{ cat.label }}
                </option>
              </select>
            </div>

            <!-- Reason -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Reason</label>
              <textarea
                v-model="refundForm.reason"
                rows="2"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600 resize-none"
                placeholder="Describe the reason for this refund..."
              />
            </div>

            <!-- Admin Notes -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Admin Notes (internal)</label>
              <textarea
                v-model="refundForm.admin_notes"
                rows="2"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600 resize-none"
                placeholder="Internal notes not visible to the customer..."
              />
            </div>

            <div v-if="refundError" class="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400">{{ refundError }}</div>
            <div class="flex items-center justify-end gap-3 pt-2">
              <button type="button" class="btn-secondary" :disabled="refundLoading" @click="showRefundModal = false">Cancel</button>
              <button type="submit" class="btn-primary inline-flex items-center" :disabled="refundLoading">
                <svg v-if="refundLoading" class="mr-2 h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Issue Refund
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>
