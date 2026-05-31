<script setup lang="ts">
/**
 * DashboardHome — The central account hub after login.
 *
 * Shows real data from the system:
 *  - Account overview (email, member since, verification status)
 *  - Subscription status with plan details
 *  - Quick actions (Manage Billing, View Plans, Profile, Settings)
 *  - Recent billing history from Stripe
 *  - Getting Started checklist based on real user state
 */

import { ref, computed, onMounted } from "vue";
import { useAuth } from "@/composables";
import { useSubscription } from "@/composables";
import { getErrorMessage } from "@/lib/auth";
import {
  billingApi,
  getStatusStyle,
  formatPrice,
  formatDate,
} from "@/lib/billing";
import { showToast } from "@/lib/toast";
import type { SubscriptionOutputSchema, TransactionItemSchema } from "@/lib/billing";

const { user, loading, initAuth } = useAuth();
const { subscriptions: subs, fetchSubscriptions, refetchSubscriptions } = useSubscription();
const transactions = ref<TransactionItemSchema[]>([]);
const portalLoading = ref(false);

// ── Computed ──

const activeSubs = computed(() =>
  subs.value.filter((s) =>
    ["active", "trialing", "past_due"].includes(s.status)
  )
);

const hasPaidSub = computed(() =>
  subs.value.some(
    (s) => ["active", "trialing", "past_due"].includes(s.status) && s.plan_slug !== "free"
  )
);

const primarySub = computed(() => {
  const paid = subs.value.find(
    (s) => ["active", "trialing"].includes(s.status) && s.plan_slug !== "free"
  );
  return paid || subs.value[0] || null;
});

const daysUntilRenewal = computed(() => {
  if (!primarySub.value?.current_period_end) return null;
  const end = new Date(primarySub.value.current_period_end);
  const now = new Date();
  const diff = Math.ceil((end.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  return Math.max(0, diff);
});

// ── Getting Started Checklist (real state) ──

const checklist = computed(() => {
  if (!user.value) return [];
  const items = [];

  items.push({
    id: "profile",
    label: "Complete your profile",
    description: "Add your first and last name",
    done: !!(user.value.first_name && user.value.last_name),
    href: "/dashboard/profile",
  });

  items.push({
    id: "email",
    label: "Verify your email",
    description: "Confirm your email address for security",
    done: user.value.is_email_verified,
    href: user.value.is_email_verified ? undefined : "/auth/verify-email",
  });

  items.push({
    id: "subscription",
    label: "Choose a plan",
    description: "Select a subscription that fits your needs",
    done: hasPaidSub.value,
    href: "/dashboard/billing",
  });

  items.push({
    id: "settings",
    label: "Set preferences",
    description: "Configure timezone, currency, and language",
    done: !!(user.value.timezone && user.value.timezone !== "UTC"),
    href: "/dashboard/settings",
  });

  return items;
});

const checklistProgress = computed(() => {
  if (checklist.value.length === 0) return 0;
  const done = checklist.value.filter((i) => i.done).length;
  return Math.round((done / checklist.value.length) * 100);
});

// ── Lifecycle ──

onMounted(async () => {
  const authenticated = await initAuth();
  if (!authenticated) return;

  // Fetch subscriptions via shared composable
  try {
    await fetchSubscriptions();

    // Fetch recent transactions for paid users
    if (hasPaidSub.value) {
      try {
        const txResult = await billingApi.getTransactionHistory(5);
        transactions.value = txResult.transactions;
      } catch {
        // Non-critical
      }
    }
  } catch {
    // Billing may not be configured yet
  }
});

// ── Helpers ──

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function getMemberSince(dateStr: string | null | undefined): string {
  if (!dateStr) return "Recently";
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

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

async function openPortal() {
  portalLoading.value = true;
  try {
    const result = await billingApi.createPortalSession();
    if (result.portal_url) {
      window.location.href = result.portal_url;
    }
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    portalLoading.value = false;
  }
}
</script>

<template>
  <div>
    <!-- ══════════════════════════════════════════════════════════════
         LOADING SKELETON
         ══════════════════════════════════════════════════════════════ -->
    <template v-if="loading">
      <div class="mb-8 animate-pulse">
        <div class="h-8 w-56 rounded-lg bg-muted"></div>
        <div class="mt-2 h-4 w-40 rounded bg-muted"></div>
      </div>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mb-8">
        <div v-for="i in 3" :key="'skel-' + i" class="card p-6 animate-pulse">
          <div class="flex items-center justify-between">
            <div class="h-4 w-28 rounded bg-muted"></div>
            <div class="h-8 w-8 rounded-lg bg-muted"></div>
          </div>
          <div class="mt-3 h-7 w-24 rounded bg-muted"></div>
          <div class="mt-2 h-3 w-36 rounded bg-muted"></div>
        </div>
      </div>
      <div class="card p-6 animate-pulse mb-6">
        <div class="h-5 w-40 rounded bg-muted mb-4"></div>
        <div class="space-y-3">
          <div v-for="i in 4" :key="'skel-tx-' + i" class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="h-9 w-9 rounded-lg bg-muted"></div>
              <div class="h-4 w-48 rounded bg-muted"></div>
            </div>
            <div class="h-4 w-16 rounded bg-muted"></div>
          </div>
        </div>
      </div>
    </template>

    <!-- ══════════════════════════════════════════════════════════════
         MAIN CONTENT
         ══════════════════════════════════════════════════════════════ -->
    <template v-else>

      <!-- ── Welcome Header ── -->
      <div class="mb-8">
        <h1 class="text-2xl font-bold tracking-tight md:text-3xl">
          {{ getGreeting() }}{{ user ? `, ${user.first_name || user.display_name}` : "" }}
        </h1>
        <p class="mt-1 text-muted-foreground">
          Manage your account, subscriptions, and billing from here.
        </p>
      </div>

      <!-- ── Email Verification Banner ── -->
      <div
        v-if="user && !user.is_email_verified"
        class="mb-6 rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 dark:border-yellow-800 dark:bg-yellow-950"
      >
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex items-start gap-3">
            <svg class="mt-0.5 h-5 w-5 shrink-0 text-yellow-600 dark:text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
            <div>
              <p class="text-sm font-medium text-yellow-800 dark:text-yellow-200">
                Your email is not verified
              </p>
              <p class="text-xs text-yellow-700 dark:text-yellow-300 mt-0.5">
                Verify your email to unlock all features.
              </p>
            </div>
          </div>
          <a
            href="/auth/verify-email"
            class="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-yellow-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-yellow-700"
          >
            Verify now
          </a>
        </div>
      </div>

      <!-- ── Stats Cards ── -->
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mb-8">

        <!-- Subscription Status -->
        <div class="card p-6 relative overflow-hidden">
          <div class="pointer-events-none absolute -right-3 -top-3 h-20 w-20 rounded-full bg-brand-500/5 dark:bg-brand-500/10"></div>
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-muted-foreground">Subscription</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-100 dark:bg-brand-950">
              <svg class="h-4 w-4 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">
            {{ primarySub ? primarySub.plan_name : 'Free' }}
          </p>
          <div v-if="primarySub" class="mt-1 flex items-center gap-2">
            <span
              :class="[getStatusStyle(primarySub.status).bg, getStatusStyle(primarySub.status).text]"
              class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            >
              <span :class="getStatusStyle(primarySub.status).dot" class="h-1.5 w-1.5 rounded-full"></span>
              {{ primarySub.status }}
            </span>
            <span v-if="daysUntilRenewal !== null && primarySub.status === 'active'" class="text-xs text-muted-foreground">
              {{ daysUntilRenewal === 0 ? 'Renews today' : `${daysUntilRenewal}d left` }}
            </span>
          </div>
          <p v-else class="mt-1 text-xs text-muted-foreground">No active subscription</p>
        </div>

        <!-- Active Plans -->
        <div class="card p-6 relative overflow-hidden">
          <div class="pointer-events-none absolute -right-3 -top-3 h-20 w-20 rounded-full bg-blue-500/5 dark:bg-blue-500/10"></div>
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-muted-foreground">Active Plans</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-950">
              <svg class="h-4 w-4 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">{{ activeSubs.length }}</p>
          <p class="mt-1 text-xs text-muted-foreground">
            {{ hasPaidSub ? 'Premium plan active' : 'Upgrade to unlock features' }}
          </p>
        </div>

        <!-- Account Age -->
        <div class="card p-6 relative overflow-hidden sm:col-span-2 lg:col-span-1">
          <div class="pointer-events-none absolute -right-3 -top-3 h-20 w-20 rounded-full bg-purple-500/5 dark:bg-purple-500/10"></div>
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-muted-foreground">Member Since</p>
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-100 dark:bg-purple-950">
              <svg class="h-4 w-4 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
          </div>
          <p class="mt-2 text-2xl font-bold">{{ user ? getMemberSince(user.created_at) : '—' }}</p>
          <p class="mt-1 text-xs text-muted-foreground">
            {{ user ? user.email : '' }}
          </p>
        </div>
      </div>

      <!-- ── Quick Actions ── -->
      <div class="mb-8">
        <h2 class="text-lg font-semibold mb-4">Quick Actions</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <!-- Manage Billing -->
          <a
            v-if="hasPaidSub"
            href="#"
            @click.prevent="openPortal"
            class="card group flex items-center gap-3 p-4 transition-all duration-200 hover:shadow-md hover:border-brand-300 dark:hover:border-brand-700"
          >
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-100 dark:bg-brand-950 transition-transform group-hover:scale-110">
              <svg class="h-5 w-5 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <div class="min-w-0">
              <p class="text-sm font-medium">Manage Billing</p>
              <p class="text-xs text-muted-foreground">Update payment methods</p>
            </div>
          </a>

          <!-- View Plans -->
          <a
            href="/dashboard/billing"
            class="card group flex items-center gap-3 p-4 transition-all duration-200 hover:shadow-md hover:border-brand-300 dark:hover:border-brand-700"
          >
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-100 dark:bg-blue-950 transition-transform group-hover:scale-110">
              <svg class="h-5 w-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
            </div>
            <div class="min-w-0">
              <p class="text-sm font-medium">View Plans</p>
              <p class="text-xs text-muted-foreground">Compare & switch plans</p>
            </div>
          </a>

          <!-- Profile -->
          <a
            href="/dashboard/profile"
            class="card group flex items-center gap-3 p-4 transition-all duration-200 hover:shadow-md hover:border-brand-300 dark:hover:border-brand-700"
          >
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-purple-100 dark:bg-purple-950 transition-transform group-hover:scale-110">
              <svg class="h-5 w-5 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div class="min-w-0">
              <p class="text-sm font-medium">Profile</p>
              <p class="text-xs text-muted-foreground">Update personal info</p>
            </div>
          </a>

          <!-- Settings -->
          <a
            href="/dashboard/settings"
            class="card group flex items-center gap-3 p-4 transition-all duration-200 hover:shadow-md hover:border-brand-300 dark:hover:border-brand-700"
          >
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-950 transition-transform group-hover:scale-110">
              <svg class="h-5 w-5 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <div class="min-w-0">
              <p class="text-sm font-medium">Settings</p>
              <p class="text-xs text-muted-foreground">Preferences & security</p>
            </div>
          </a>
        </div>
      </div>

      <!-- ── Two Column: Getting Started + Recent Billing ── -->
      <div class="grid gap-6 lg:grid-cols-3">

        <!-- Getting Started Checklist -->
        <div class="card p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold flex items-center gap-2">
              <svg class="h-5 w-5 text-brand-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Getting Started
            </h2>
            <span
              class="text-xs font-semibold"
              :class="checklistProgress === 100 ? 'text-brand-600 dark:text-brand-400' : 'text-muted-foreground'"
            >
              {{ checklistProgress }}%
            </span>
          </div>

          <!-- Progress bar -->
          <div class="mb-4 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500 ease-out"
              :class="checklistProgress === 100 ? 'bg-brand-500 w-full' : 'bg-brand-500'"
              :style="{ width: checklistProgress + '%' }"
            ></div>
          </div>

          <ul class="space-y-3" role="list">
            <li v-for="item in checklist" :key="item.id">
              <component
                :is="item.href && !item.done ? 'a' : 'div'"
                :href="item.href"
                class="flex items-start gap-3 group rounded-lg p-1.5 -mx-1.5 transition-colors"
                :class="item.href && !item.done ? 'cursor-pointer hover:bg-accent' : ''"
              >
                <div
                  class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors"
                  :class="item.done
                    ? 'bg-brand-500 border-brand-500 text-white'
                    : 'border-border bg-background group-hover:border-brand-400'"
                >
                  <svg v-if="item.done" class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div class="min-w-0">
                  <p
                    class="text-sm font-medium leading-tight"
                    :class="item.done ? 'text-muted-foreground line-through' : 'text-foreground'"
                  >
                    {{ item.label }}
                  </p>
                  <p class="text-xs text-muted-foreground mt-0.5">{{ item.description }}</p>
                </div>
              </component>
            </li>
          </ul>
        </div>

        <!-- Recent Billing History -->
        <div class="card lg:col-span-2">
          <div class="flex items-center justify-between border-b border-border px-6 py-4">
            <h2 class="text-lg font-semibold">Recent Billing</h2>
            <a
              v-if="hasPaidSub"
              href="/dashboard/billing/transactions"
              class="text-sm text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 font-medium flex items-center gap-1 transition-colors"
            >
              View all
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </a>
          </div>

          <!-- Has transactions -->
          <div v-if="transactions.length > 0" class="divide-y divide-border">
            <div
              v-for="tx in transactions"
              :key="tx.id"
              class="flex items-center justify-between gap-4 px-6 py-3.5 transition-colors hover:bg-muted/30"
            >
              <div class="flex items-center gap-3 min-w-0">
                <div
                  class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                  :class="tx.status === 'paid'
                    ? 'bg-green-100 dark:bg-green-950/40'
                    : 'bg-amber-100 dark:bg-amber-950/40'"
                >
                  <svg
                    class="h-4 w-4"
                    :class="tx.status === 'paid' ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'"
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                  </svg>
                </div>
                <div class="min-w-0">
                  <p class="text-sm font-medium truncate">{{ tx.description || 'Invoice' }}</p>
                  <p class="text-xs text-muted-foreground">
                    <span v-if="tx.number" class="mr-1">#{{ tx.number }}</span>
                    <span v-if="tx.card_brand">
                      {{ tx.card_brand }} ****{{ tx.payment_method }}
                    </span>
                    <span v-if="tx.period_start && tx.period_end" class="ml-1">
                      · {{ formatPeriodRange(tx.period_start, tx.period_end) }}
                    </span>
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <!-- PDF / View buttons -->
                <div class="flex items-center gap-1">
                  <a
                    v-if="tx.pdf_url"
                    :href="tx.pdf_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center justify-center h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
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
                    class="inline-flex items-center justify-center h-7 w-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                    title="View invoice"
                  >
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>
                <div class="text-right">
                  <p
                    class="text-sm font-semibold"
                    :class="tx.status === 'paid' ? 'text-foreground' : 'text-amber-600 dark:text-amber-400'"
                  >
                    {{ formatPrice(Math.round(tx.amount_paid * 100), tx.currency) }}
                    <span v-if="tx.tax > 0" class="text-[10px] font-normal text-muted-foreground">
                      + {{ formatPrice(Math.round(tx.tax * 100), tx.currency) }} tax
                    </span>
                  </p>
                  <p class="text-[10px] font-semibold uppercase tracking-wide"
                    :class="tx.status === 'paid'
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-amber-600 dark:text-amber-400'"
                  >
                    {{ formatStatusLabel(tx.status) }}
                    <span class="font-normal normal-case tracking-normal">
                      · {{ formatDate(tx.created) }}
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>

          <!-- No transactions -->
          <div v-else class="flex flex-col items-center justify-center py-14 text-center px-6">
            <div class="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-muted">
              <svg class="h-7 w-7 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
            <p v-if="!hasPaidSub" class="text-sm font-medium text-muted-foreground">No billing history</p>
            <p v-else class="text-sm font-medium text-muted-foreground">No invoices yet</p>
            <p v-if="!hasPaidSub" class="mt-1 text-xs text-muted-foreground max-w-xs">
              Subscribe to a plan to start seeing your billing history here.
            </p>
            <a
              v-if="!hasPaidSub"
              href="/dashboard/billing"
              class="mt-3 btn-primary text-xs"
            >
              Browse Plans
            </a>
          </div>
        </div>
      </div>

      <!-- ── Subscription Detail Cards ── -->
      <div v-if="subs.length > 0" class="mt-8">
        <h2 class="text-lg font-semibold mb-4">Your Subscriptions</h2>
        <div class="grid gap-4 sm:grid-cols-2">
          <div
            v-for="sub in subs"
            :key="sub.id"
            class="card p-5 transition-all duration-200 hover:shadow-md"
          >
            <div class="flex items-start gap-3">
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg gradient-brand text-white text-sm font-bold shadow-md shadow-brand-600/20">
                {{ sub.product_name.charAt(0) }}
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <h3 class="text-sm font-semibold truncate">{{ sub.product_name }}</h3>
                  <span
                    :class="[getStatusStyle(sub.status).bg, getStatusStyle(sub.status).text]"
                    class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide shrink-0"
                  >
                    <span :class="getStatusStyle(sub.status).dot" class="h-1.5 w-1.5 rounded-full"></span>
                    {{ sub.status }}
                  </span>
                </div>
                <p class="text-sm text-muted-foreground mt-0.5">{{ sub.plan_name }} Plan</p>
                <div class="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                  <span v-if="sub.current_period_end">
                    {{ sub.status === 'canceled' ? 'Expires' : 'Renews' }} {{ formatDate(sub.current_period_end) }}
                  </span>
                  <span v-if="sub.status === 'trialing' && sub.trial_end">
                    Trial ends {{ formatDate(sub.trial_end) }}
                  </span>
                </div>
              </div>
            </div>
            <div class="mt-3 flex items-center gap-2 pt-3 border-t border-border">
              <a
                :href="`/dashboard/billing/plans/${sub.product_slug}`"
                class="text-xs font-medium text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 transition-colors"
              >
                {{ sub.plan_slug === 'free' ? 'Upgrade' : 'Change Plan' }}
              </a>
              <template v-if="sub.plan_slug !== 'free' && ['active', 'trialing'].includes(sub.status)">
                <span class="text-border">|</span>
                <a
                  href="#"
                  @click.prevent="openPortal"
                  class="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  Manage
                </a>
              </template>
            </div>
          </div>
        </div>
      </div>

    </template>
  </div>
</template>
