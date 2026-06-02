<script setup lang="ts">
// Plans landing page — shows all products/domains with their plans
import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { useSubscription } from "@/composables";
import {
  billingApi,
  formatPrice,
  formatCycle,
  getUserCurrency,
} from "@/lib/billing";
import type { ProductDetailSchema } from "@/lib/billing";
import { showToast } from "@/lib/toast";

const products = ref<ProductDetailSchema[]>([]);
const loading = ref(true);
const { subscriptions, refetchSubscriptions } = useSubscription();

// Get current subscription for a product
function getSubForProduct(productSlug: string) {
  return subscriptions.value.find((s) => s.product_slug === productSlug);
}

// Get a status badge class for subscription
function getStatusClasses(status: string, cancelAtPeriodEnd: boolean) {
  if (cancelAtPeriodEnd && status === "active") {
    return "bg-orange-50 text-orange-700 dark:bg-orange-950/50 dark:text-orange-300";
  }
  const map: Record<string, string> = {
    active: "bg-brand-50 text-brand-700 dark:bg-brand-950/50 dark:text-brand-300",
    trialing: "bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300",
    past_due: "bg-yellow-50 text-yellow-700 dark:bg-yellow-950/50 dark:text-yellow-300",
    canceled: "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300",
    paused: "bg-gray-50 text-gray-700 dark:bg-gray-950/50 dark:text-gray-300",
    expired: "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300",
  };
  return map[status] || map.expired;
}

function getStatusLabel(status: string, cancelAtPeriodEnd: boolean) {
  if (cancelAtPeriodEnd && (status === "active" || status === "trialing")) return "Canceling";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

onMounted(async () => {
  if (!requireAuth()) return;

  try {
    // Currency is already set by useAuth or Navbar — no separate API call needed.
    const currency = getUserCurrency();

    // Fetch all products with their plans in parallel
    const [productsData] = await Promise.all([
      billingApi.getProducts(),
      refetchSubscriptions(),
    ]);

    // Fetch detailed product data (with plans) for each product
    const detailPromises = productsData.map((p) =>
      billingApi.getProductBySlug(p.slug, currency).catch(() => null)
    );
    const details = await Promise.all(detailPromises);

    // Filter out failed fetches
    products.value = details.filter((d): d is ProductDetailSchema => d !== null);
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div>
    <!-- Header -->
    <div class="mb-8">
      <h1 class="text-2xl font-bold tracking-tight">Plans & Pricing</h1>
      <p class="mt-1 text-sm text-[var(--color-muted-foreground)]">
        Browse plans across all available products. Click on any product to compare plans and manage your subscription.
      </p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="space-y-6">
      <div v-for="i in 2" :key="i" class="card p-6 animate-pulse">
        <div class="flex items-start gap-4">
          <div class="h-12 w-12 rounded-xl bg-[var(--color-muted)]"></div>
          <div class="flex-1 space-y-2">
            <div class="h-5 w-40 rounded bg-[var(--color-muted)]"></div>
            <div class="h-4 w-64 rounded bg-[var(--color-muted)]"></div>
          </div>
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-3">
          <div v-for="j in 3" :key="j" class="h-32 rounded-lg bg-[var(--color-muted)]"></div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="products.length === 0" class="card p-12 text-center">
      <div class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-accent)]">
        <svg class="h-6 w-6 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
      </div>
      <p class="text-[var(--color-muted-foreground)]">No products available yet.</p>
    </div>

    <!-- Product Cards — Domain-wise plan listing -->
    <div v-else class="space-y-6">
      <a
        v-for="product in products"
        :key="product.id"
        :href="`/dashboard/billing/plans/${product.slug}`"
        class="card group block p-6 transition-all duration-200 hover:shadow-md hover:border-brand-300 dark:hover:border-brand-700"
      >
        <!-- Product Header -->
        <div class="flex items-start justify-between gap-4">
          <div class="flex items-start gap-4">
            <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl gradient-brand text-white text-lg font-bold shadow-md shadow-brand-600/20 transition-transform duration-150 group-hover:scale-110">
              {{ product.name.split(' ').map(w => w[0]).join('').slice(0, 2) }}
            </div>
            <div>
              <div class="flex items-center gap-3">
                <h2 class="text-lg font-semibold group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">
                  {{ product.name }}
                </h2>
                <!-- Current subscription status badge -->
                <span
                  v-if="getSubForProduct(product.slug)"
                  :class="getStatusClasses(getSubForProduct(product.slug)!.status, getSubForProduct(product.slug)!.cancel_at_period_end)"
                  class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
                >
                  {{ getStatusLabel(getSubForProduct(product.slug)!.status, getSubForProduct(product.slug)!.cancel_at_period_end) }}
                  — {{ getSubForProduct(product.slug)!.plan_name }}
                </span>
              </div>
              <p v-if="product.description" class="mt-1 text-sm text-[var(--color-muted-foreground)]">
                {{ product.description }}
              </p>
              <!-- Service domains -->
              <div v-if="product.service_domains && product.service_domains.length > 0" class="mt-2 flex flex-wrap gap-1.5">
                <span
                  v-for="domain in product.service_domains"
                  :key="domain.id"
                  class="inline-flex items-center rounded-md bg-[var(--color-accent)] px-2 py-0.5 text-xs text-[var(--color-muted-foreground)] font-mono"
                >
                  {{ domain.domain }}
                </span>
              </div>
            </div>
          </div>
          <svg class="h-5 w-5 shrink-0 text-[var(--color-muted-foreground)] transition-transform group-hover:translate-x-1 group-hover:text-brand-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </div>

        <!-- Plan Summary Cards -->
        <div v-if="product.plans && product.plans.length > 0" class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div
            v-for="plan in product.plans"
            :key="plan.id"
            class="rounded-lg border p-3 transition-colors"
            :class="[
              plan.is_featured
                ? 'border-brand-200 bg-brand-50/50 dark:border-brand-800 dark:bg-brand-950/20'
                : 'border-[var(--color-border)]',
              getSubForProduct(product.slug)?.plan_slug === plan.slug
                ? 'ring-2 ring-brand-500 dark:ring-brand-400'
                : ''
            ]"
          >
            <div class="flex items-center justify-between">
              <span class="font-medium text-sm">{{ plan.name }}</span>
              <span
                v-if="getSubForProduct(product.slug)?.plan_slug === plan.slug"
                class="inline-flex items-center rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700 dark:bg-brand-900 dark:text-brand-300"
              >
                Current
              </span>
              <span
                v-else-if="plan.is_featured"
                class="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900 dark:text-amber-300"
              >
                Popular
              </span>
            </div>
            <div class="mt-1">
              <span class="text-lg font-bold">
                {{ plan.is_free ? 'Free' : formatPrice(plan.converted_price_cents ?? plan.price_cents, plan.user_currency ?? plan.currency) }}
              </span>
              <span v-if="!plan.is_free" class="text-xs text-[var(--color-muted-foreground)]">
                {{ formatCycle(plan.billing_cycle) }}
              </span>
            </div>
            <!-- Feature count -->
            <p v-if="plan.features && Object.keys(plan.features).length > 0" class="mt-1.5 text-xs text-[var(--color-muted-foreground)]">
              {{ Object.keys(plan.features).length }} feature{{ Object.keys(plan.features).length !== 1 ? 's' : '' }} included
            </p>
            <p v-if="plan.trial_days > 0" class="mt-1 text-xs text-brand-600 dark:text-brand-400">
              {{ plan.trial_days }}-day free trial
            </p>
          </div>
        </div>

        <!-- CTA -->
        <div class="mt-4 flex items-center gap-1.5 text-sm font-medium text-brand-600 dark:text-brand-400 group-hover:text-brand-500 dark:group-hover:text-brand-300 transition-colors">
          <span>Compare plans & manage subscription</span>
          <svg class="h-4 w-4 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3" />
          </svg>
        </div>
      </a>
    </div>
  </div>
</template>
