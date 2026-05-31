<script setup lang="ts">
/**
 * TransactionHistory — Dedicated billing transactions page.
 *
 * H3: Full transaction history with:
 *  - Paginated loading via Stripe cursor (starting_after)
 *  - Status filters (All, Paid, Pending, Failed)
 *  - Date range display with period start/end
 *  - Tax breakdown per line
 *  - PDF download and hosted invoice links
 *  - Payment method details (card brand, last 4)
 *  - Responsive table/card layout
 *  - Summary stats (total spent, invoice count)
 *  - Empty states for free/non-billed users
 */

import { ref, computed, onMounted, watch } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { useSubscription } from "@/composables";
import { showToast } from "@/lib/toast";
import {
  billingApi,
  formatPrice,
  formatDate,
  getUserCurrency,
} from "@/lib/billing";
import type { TransactionItemSchema } from "@/lib/billing";

// ── State ──

const loading = ref(true);
const transactions = ref<TransactionItemSchema[]>([]);
const transactionsLoading = ref(false);
const hasMore = ref(false);
const currency = ref("USD");
const activeFilter = ref<"all" | "paid" | "pending" | "failed">("all");

const { subscriptions, fetchSubscriptions } = useSubscription();

// ── Filtered list ──

const filteredTransactions = computed(() => {
  if (activeFilter.value === "all") return transactions.value;
  switch (activeFilter.value) {
    case "paid":
      return transactions.value.filter((tx) => tx.status === "paid");
    case "pending":
      return transactions.value.filter((tx) => tx.status === "open" || tx.status === "draft");
    case "failed":
      return transactions.value.filter((tx) => tx.status === "uncollectible" || tx.status === "void");
    default:
      return transactions.value;
  }
});

// ── Summary stats ──

const totalSpent = computed(() => {
  return transactions.value
    .filter((tx) => tx.status === "paid")
    .reduce((sum, tx) => sum + tx.amount_paid, 0);
});

const totalTax = computed(() => {
  return transactions.value
    .filter((tx) => tx.status === "paid")
    .reduce((sum, tx) => sum + tx.tax, 0);
});

const paidCount = computed(() =>
  transactions.value.filter((tx) => tx.status === "paid").length,
);

const pendingCount = computed(() =>
  transactions.value.filter((tx) => tx.status === "open" || tx.status === "draft").length,
);

const failedCount = computed(() =>
  transactions.value.filter((tx) => tx.status === "uncollectible" || tx.status === "void").length,
);

// ── Lifecycle ──

onMounted(async () => {
  if (!requireAuth()) return;

  try {
    await fetchSubscriptions();
  } catch {
    // Non-critical for transaction viewing
  }

  // Always try to load transactions (even free users may have legacy invoices)
  await loadInitialTransactions();
});

async function loadInitialTransactions() {
  loading.value = true;
  try {
    const result = await billingApi.getTransactionHistory(25);
    transactions.value = result.transactions;
    hasMore.value = result.has_more;
    currency.value = result.currency || getUserCurrency();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  if (transactionsLoading.value || !hasMore.value) return;
  transactionsLoading.value = true;
  try {
    const lastId = transactions.value.length > 0
      ? transactions.value[transactions.value.length - 1].id
      : undefined;
    const result = await billingApi.getTransactionHistory(25, lastId);
    transactions.value = [...transactions.value, ...result.transactions];
    hasMore.value = result.has_more;
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    transactionsLoading.value = false;
  }
}

// ── Helpers ──

function formatPeriodRange(start: string | null, end: string | null): string {
  if (!start || !end) return "";
  const locale = typeof navigator !== "undefined" ? navigator.language : "en-US";
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  const s = new Date(start).toLocaleDateString(locale, opts);
  const e = new Date(end).toLocaleDateString(locale, opts);
  return `${s} \u2013 ${e}`;
}

function formatStatusLabel(status: string): string {
  const map: Record<string, string> = {
    paid: "Paid",
    draft: "Pending",
    open: "Pending",
    void: "Void",
    uncollectible: "Uncollectible",
  };
  return map[status] || status.charAt(0).toUpperCase() + status.slice(1);
}

function getStatusColor(status: string) {
  switch (status) {
    case "paid":
      return {
        bg: "bg-green-100 dark:bg-green-950/40",
        text: "text-green-700 dark:text-green-400",
        icon: "text-green-600 dark:text-green-400",
      };
    case "open":
    case "draft":
      return {
        bg: "bg-amber-100 dark:bg-amber-950/40",
        text: "text-amber-700 dark:text-amber-400",
        icon: "text-amber-600 dark:text-amber-400",
      };
    case "void":
    case "uncollectible":
      return {
        bg: "bg-red-100 dark:bg-red-950/40",
        text: "text-red-700 dark:text-red-400",
        icon: "text-red-600 dark:text-red-400",
      };
    default:
      return {
        bg: "bg-gray-100 dark:bg-gray-950/40",
        text: "text-gray-700 dark:text-gray-400",
        icon: "text-gray-600 dark:text-gray-400",
      };
  }
}

// Re-fetch when filter changes (apply locally; pagination always loads all statuses)
</script>

<template>
  <div>
    <!-- Page Header -->
    <div class="mb-8">
      <h1 class="text-2xl font-bold tracking-tight md:text-3xl">Transactions</h1>
      <p class="mt-1 text-[var(--color-muted-foreground)]">
        View your complete billing history, download invoices, and track payments.
      </p>
    </div>

    <!-- Loading Skeleton -->
    <template v-if="loading">
      <div class="grid gap-4 sm:grid-cols-3 mb-8">
        <div v-for="i in 3" :key="'skel-stat-' + i" class="card p-6 animate-pulse">
          <div class="h-4 w-28 rounded bg-[var(--color-muted)]"></div>
          <div class="mt-3 h-7 w-24 rounded bg-[var(--color-muted)]"></div>
        </div>
      </div>
      <div class="card animate-pulse">
        <div class="px-6 py-4 border-b border-border flex items-center justify-between">
          <div class="h-5 w-40 rounded bg-[var(--color-muted)]"></div>
          <div class="h-8 w-48 rounded-full bg-[var(--color-muted)]"></div>
        </div>
        <div class="divide-y divide-border">
          <div v-for="i in 5" :key="'skel-tx-' + i" class="px-6 py-4 flex items-center justify-between">
            <div class="flex items-center gap-4">
              <div class="h-9 w-9 rounded-lg bg-[var(--color-muted)]"></div>
              <div>
                <div class="h-4 w-48 rounded bg-[var(--color-muted)] mb-2"></div>
                <div class="h-3 w-32 rounded bg-[var(--color-muted)]"></div>
              </div>
            </div>
            <div class="flex items-center gap-3">
              <div class="h-4 w-16 rounded bg-[var(--color-muted)]"></div>
              <div class="h-7 w-16 rounded bg-[var(--color-muted)]"></div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <!-- Summary Stats -->
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        <!-- Total Spent -->
        <div class="card p-6">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-[var(--color-muted-foreground)]">Total Spent</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-100 dark:bg-green-950">
              <svg class="h-4 w-4 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">
            {{ totalSpent > 0 ? formatPrice(Math.round(totalSpent * 100), currency) : "\u2014" }}
          </p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">
            {{ paidCount }} paid invoice{{ paidCount !== 1 ? "s" : "" }}
          </p>
        </div>

        <!-- Tax Total -->
        <div class="card p-6">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-[var(--color-muted-foreground)]">Total Tax</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-950">
              <svg class="h-4 w-4 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">
            {{ totalTax > 0 ? formatPrice(Math.round(totalTax * 100), currency) : "\u2014" }}
          </p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">across all invoices</p>
        </div>

        <!-- Pending -->
        <div class="card p-6">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-[var(--color-muted-foreground)]">Pending</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-950">
              <svg class="h-4 w-4 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">{{ pendingCount }}</p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">
            awaiting payment
          </p>
        </div>

        <!-- Total Invoices -->
        <div class="card p-6">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-[var(--color-muted-foreground)]">Invoices</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-100 dark:bg-purple-950">
              <svg class="h-4 w-4 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">{{ transactions.length }}</p>
          <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">
            {{ failedCount > 0 ? `${failedCount} failed` : "no failed payments" }}
          </p>
        </div>
      </div>

      <!-- Transactions Table -->
      <div class="card">
        <!-- Table Header -->
        <div class="px-6 py-4 border-b border-border">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 class="text-lg font-semibold">
              Billing History
              <span class="ml-2 text-sm font-normal text-[var(--color-muted-foreground)]">
                ({{ filteredTransactions.length }} of {{ transactions.length }})
              </span>
            </h2>

            <!-- Filter Tabs -->
            <div class="flex items-center gap-1 rounded-lg bg-[var(--color-muted)] p-1">
              <button
                v-for="f in [
                  { key: 'all', label: 'All', count: transactions.length },
                  { key: 'paid', label: 'Paid', count: paidCount },
                  { key: 'pending', label: 'Pending', count: pendingCount },
                  { key: 'failed', label: 'Failed', count: failedCount },
                ] as const"
                :key="f.key"
                class="rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150"
                :class="activeFilter === f.key
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-[var(--color-muted-foreground)] hover:text-foreground'"
                @click="activeFilter = f.key"
              >
                {{ f.label }}
                <span
                  v-if="f.count > 0"
                  class="ml-1 inline-flex items-center justify-center h-4 min-w-[16px] rounded-full px-1 text-[10px] font-semibold"
                  :class="activeFilter === f.key
                    ? 'bg-brand-100 text-brand-700 dark:bg-brand-950 dark:text-brand-400'
                    : 'bg-background/50'"
                >
                  {{ f.count }}
                </span>
              </button>
            </div>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="transactions.length === 0" class="flex flex-col items-center justify-center py-20 text-center px-6">
          <div class="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[var(--color-muted)]">
            <svg class="h-8 w-8 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 class="text-base font-semibold">No transactions yet</h3>
          <p class="mt-1 text-sm text-[var(--color-muted-foreground)] max-w-sm">
            Your billing history will appear here once you subscribe to a paid plan.
          </p>
          <a href="/dashboard/billing" class="mt-4 btn-primary text-xs">
            Browse Plans
          </a>
        </div>

        <!-- Filter empty state -->
        <div v-else-if="filteredTransactions.length === 0" class="flex flex-col items-center justify-center py-16 text-center px-6">
          <div class="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-muted)]">
            <svg class="h-6 w-6 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
          </div>
          <p class="text-sm font-medium text-[var(--color-muted-foreground)]">
            No {{ activeFilter }} transactions found
          </p>
          <button
            class="mt-2 text-xs text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 font-medium"
            @click="activeFilter = 'all'"
          >
            Show all transactions
          </button>
        </div>

        <!-- Transaction List -->
        <div v-else class="divide-y divide-border">
          <!-- Desktop Table Header -->
          <div class="hidden lg:grid lg:grid-cols-12 gap-4 px-6 py-2.5 text-xs font-semibold uppercase tracking-wider text-[var(--color-muted-foreground)] bg-[var(--color-muted)]/30">
            <div class="col-span-5">Description</div>
            <div class="col-span-2">Status</div>
            <div class="col-span-2 text-right">Amount</div>
            <div class="col-span-2">Date</div>
            <div class="col-span-1 text-right">Actions</div>
          </div>

          <div
            v-for="tx in filteredTransactions"
            :key="tx.id"
            class="group transition-colors hover:bg-[var(--color-muted)]/20"
          >
            <!-- Desktop Row -->
            <div class="hidden lg:grid lg:grid-cols-12 gap-4 items-center px-6 py-4">
              <!-- Description -->
              <div class="col-span-5 min-w-0">
                <div class="flex items-center gap-3">
                  <div
                    class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                    :class="getStatusColor(tx.status).bg"
                  >
                    <svg
                      class="h-4 w-4"
                      :class="getStatusColor(tx.status).icon"
                      fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                    </svg>
                  </div>
                  <div class="min-w-0">
                    <p class="text-sm font-medium truncate">
                      {{ tx.description || (tx.type === "invoice" ? "Invoice" : "Charge") }}
                    </p>
                    <div class="flex items-center gap-2 text-xs text-[var(--color-muted-foreground)] mt-0.5">
                      <span v-if="tx.number">#{{ tx.number }}</span>
                      <span v-if="tx.card_brand">{{ tx.card_brand }} ****{{ tx.payment_method }}</span>
                      <span v-if="tx.period_start && tx.period_end">
                        &middot; {{ formatPeriodRange(tx.period_start, tx.period_end) }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Status -->
              <div class="col-span-2">
                <span
                  class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
                  :class="[getStatusColor(tx.status).bg, getStatusColor(tx.status).text]"
                >
                  <span
                    class="h-1.5 w-1.5 rounded-full"
                    :class="tx.status === 'paid' ? 'bg-green-500' : tx.status === 'open' || tx.status === 'draft' ? 'bg-amber-500' : 'bg-red-500'"
                  />
                  {{ formatStatusLabel(tx.status) }}
                </span>
                <span v-if="tx.attempt_count > 1 && tx.status !== 'paid'" class="ml-2 text-[10px] text-[var(--color-muted-foreground)]">
                  ({{ tx.attempt_count }} attempts)
                </span>
              </div>

              <!-- Amount -->
              <div class="col-span-2 text-right">
                <p class="text-sm font-semibold">
                  {{ formatPrice(Math.round(tx.amount_paid * 100), tx.currency) }}
                </p>
                <p v-if="tx.tax > 0" class="text-[10px] text-[var(--color-muted-foreground)]">
                  incl. {{ formatPrice(Math.round(tx.tax * 100), tx.currency) }} tax
                </p>
              </div>

              <!-- Date -->
              <div class="col-span-2 text-sm text-[var(--color-muted-foreground)]">
                {{ formatDate(tx.created) }}
              </div>

              <!-- Actions -->
              <div class="col-span-1 flex items-center justify-end gap-1">
                <a
                  v-if="tx.pdf_url"
                  :href="tx.pdf_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center justify-center h-8 w-8 rounded-md text-[var(--color-muted-foreground)] hover:text-foreground hover:bg-accent transition-colors"
                  title="Download PDF"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3M3 17v3a2 2 0 002 2h14a2 2 0 002-2v-3" />
                  </svg>
                </a>
                <a
                  v-if="tx.hosted_url"
                  :href="tx.hosted_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center justify-center h-8 w-8 rounded-md text-[var(--color-muted-foreground)] hover:text-foreground hover:bg-accent transition-colors"
                  title="View invoice"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              </div>
            </div>

            <!-- Mobile Row -->
            <div class="lg:hidden px-4 py-3.5">
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-start gap-3 min-w-0 flex-1">
                  <div
                    class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg mt-0.5"
                    :class="getStatusColor(tx.status).bg"
                  >
                    <svg
                      class="h-4 w-4"
                      :class="getStatusColor(tx.status).icon"
                      fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                    </svg>
                  </div>
                  <div class="min-w-0">
                    <p class="text-sm font-medium truncate">
                      {{ tx.description || (tx.type === "invoice" ? "Invoice" : "Charge") }}
                    </p>
                    <div class="flex items-center gap-1.5 text-xs text-[var(--color-muted-foreground)] mt-0.5 flex-wrap">
                      <span v-if="tx.number">#{{ tx.number }}</span>
                      <span v-if="tx.card_brand">{{ tx.card_brand }} ****{{ tx.payment_method }}</span>
                      <span v-if="tx.period_start && tx.period_end">
                        &middot; {{ formatPeriodRange(tx.period_start, tx.period_end) }}
                      </span>
                    </div>
                  </div>
                </div>
                <div class="text-right shrink-0">
                  <p class="text-sm font-semibold">
                    {{ formatPrice(Math.round(tx.amount_paid * 100), tx.currency) }}
                  </p>
                  <p v-if="tx.tax > 0" class="text-[10px] text-[var(--color-muted-foreground)]">
                    + {{ formatPrice(Math.round(tx.tax * 100), tx.currency) }} tax
                  </p>
                </div>
              </div>
              <div class="flex items-center justify-between mt-2 pl-12">
                <div class="flex items-center gap-2">
                  <span
                    class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                    :class="[getStatusColor(tx.status).bg, getStatusColor(tx.status).text]"
                  >
                    <span
                      class="h-1.5 w-1.5 rounded-full"
                      :class="tx.status === 'paid' ? 'bg-green-500' : tx.status === 'open' || tx.status === 'draft' ? 'bg-amber-500' : 'bg-red-500'"
                    />
                    {{ formatStatusLabel(tx.status) }}
                  </span>
                  <span class="text-xs text-[var(--color-muted-foreground)]">
                    {{ formatDate(tx.created) }}
                  </span>
                </div>
                <div class="flex items-center gap-1">
                  <a
                    v-if="tx.pdf_url"
                    :href="tx.pdf_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center justify-center h-7 w-7 rounded-md text-[var(--color-muted-foreground)] hover:text-foreground hover:bg-accent transition-colors"
                    title="Download PDF"
                  >
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3M3 17v3a2 2 0 002 2h14a2 2 0 002-2v-3" />
                    </svg>
                  </a>
                  <a
                    v-if="tx.hosted_url"
                    :href="tx.hosted_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center justify-center h-7 w-7 rounded-md text-[var(--color-muted-foreground)] hover:text-foreground hover:bg-accent transition-colors"
                    title="View invoice"
                  >
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Load More -->
        <div
          v-if="transactions.length > 0 && hasMore"
          class="px-6 py-4 border-t border-border flex items-center justify-center"
        >
          <button
            :disabled="transactionsLoading"
            class="btn-secondary text-sm"
            @click="loadMore"
          >
            <svg
              v-if="transactionsLoading"
              class="h-4 w-4 mr-2 animate-spin"
              fill="none" viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <svg v-else class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {{ transactionsLoading ? "Loading..." : "Load More Transactions" }}
          </button>
        </div>

        <!-- End of list -->
        <div
          v-if="transactions.length > 0 && !hasMore"
          class="px-6 py-3 border-t border-border text-center"
        >
          <p class="text-xs text-[var(--color-muted-foreground)]">
            Showing all {{ transactions.length }} transaction{{ transactions.length !== 1 ? "s" : "" }}
          </p>
        </div>
      </div>
    </template>
  </div>
</template>
