<template>
  <div class="space-y-8">
    <!-- Credit Pools Section -->
    <div>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white">Credit Pools</h2>
        <a
          href="/dashboard/billing/credits/request"
          class="inline-flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors"
        >
          Request Credits
        </a>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-12">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
      </div>

      <div v-else-if="pools.length === 0" class="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-8 text-center">
        <p class="text-gray-500 dark:text-gray-400">No credit pools found.</p>
        <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">Credits can be purchased through the admin panel or via local payment gateways.</p>
      </div>

      <div v-else class="space-y-4">
        <div
          v-for="pool in pools"
          :key="pool.id"
          class="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <div class="flex items-center gap-3">
                <h3 class="font-semibold text-gray-900 dark:text-white">
                  {{ pool.product_name }} — {{ pool.plan_name }}
                </h3>
                <span
                  :class="[
                    'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
                    pool.status === 'active' && pool.is_effectively_active
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300'
                      : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                  ]"
                >
                  {{ pool.is_effectively_active ? 'Active' : pool.status }}
                </span>
              </div>
              <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
                Paid {{ pool.display_amount }} via {{ pool.source }}
              </p>
            </div>
            <div class="text-right">
              <p class="text-lg font-bold text-gray-900 dark:text-white">{{ pool.periods_remaining }}</p>
              <p class="text-xs text-gray-500 dark:text-gray-400">of {{ pool.credit_periods }} periods left</p>
            </div>
          </div>

          <!-- Period expiry -->
          <div class="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-500 dark:text-gray-400">
                Source: <span class="font-medium text-gray-700 dark:text-gray-300">{{ pool.source }}</span>
              </span>
              <span v-if="pool.current_period_end" class="text-gray-500 dark:text-gray-400">
                Expires: <span class="font-medium text-gray-700 dark:text-gray-300">{{ formatDate(pool.current_period_end) }}</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Credit Invoices Section -->
    <div>
      <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Invoice History</h2>

      <div v-if="invoicesLoading" class="flex items-center justify-center py-12">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
      </div>

      <div v-else-if="invoices.length === 0" class="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-8 text-center">
        <p class="text-gray-500 dark:text-gray-400">No invoices yet.</p>
      </div>

      <div v-else class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-900/50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Invoice #</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Plan</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Amount</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Tax</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Total</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Date</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700 bg-white dark:bg-gray-800">
            <tr v-for="inv in invoices" :key="inv.id" class="hover:bg-gray-50 dark:hover:bg-gray-700/30">
              <td class="px-4 py-3 text-sm font-mono text-brand-600 dark:text-brand-400">{{ inv.invoice_number }}</td>
              <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">{{ inv.plan_name }}</td>
              <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">{{ formatCurrency(inv.amount_cents) }}</td>
              <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{{ formatCurrency(inv.tax_cents) }}</td>
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">{{ formatCurrency(inv.total_cents) }}</td>
              <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">{{ formatDate(inv.issued_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import type { CreditPool, CreditInvoice } from "@/lib/credits";

const pools = ref<CreditPool[]>([]);
const invoices = ref<CreditInvoice[]>([]);
const loading = ref(true);
const invoicesLoading = ref(true);

onMounted(async () => {
  try {
    const { apiClient } = await import("@/lib/api");
    const [poolsRes, invoicesRes] = await Promise.all([
      apiClient.get<CreditPool[]>("/billing/credits"),
      apiClient.get<CreditInvoice[]>("/billing/credits/invoices"),
    ]);
    pools.value = poolsRes.data || [];
    invoices.value = invoicesRes.data || [];
  } catch (err) {
    console.error("Failed to fetch credits:", err);
  } finally {
    loading.value = false;
    invoicesLoading.value = false;
  }
});

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });
  } catch { return dateStr; }
}

function formatCurrency(cents: number): string {
  return "$" + (cents / 100).toFixed(2);
}
</script>
