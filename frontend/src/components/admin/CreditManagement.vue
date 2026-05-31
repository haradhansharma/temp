<!-- CreditManagement.vue — Admin panel for managing credit pools and invoices. -->
<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
          Credit Pools
        </h2>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Manage prepaid credit purchases for users who pay via local/offline methods.
        </p>
      </div>
      <button
        @click="openPurchaseModal"
        class="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors"
      >
        <span>+ Record Payment</span>
      </button>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3 items-end">
      <div>
        <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Search (email)</label>
        <input
          v-model="search"
          type="email"
          placeholder="user@example.com"
          class="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          @keyup.enter="fetchCredits"
        />
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Status</label>
        <select
          v-model="filterStatus"
          class="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-brand-500"
          @change="fetchCredits"
        >
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="exhausted">Exhausted</option>
          <option value="expired">Expired</option>
          <option value="refunded">Refunded</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Source</label>
        <select
          v-model="filterSource"
          class="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-brand-500"
          @change="fetchCredits"
        >
          <option value="">All</option>
          <option value="manual">Manual</option>
          <option value="local_gateway">Local Gateway</option>
          <option value="bank_transfer">Bank Transfer</option>
          <option value="cash">Cash</option>
        </select>
      </div>
      <button
        @click="fetchCredits"
        class="rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
      >
        Filter
      </button>
    </div>

    <!-- Credit Pools Table -->
    <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
      <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead class="bg-gray-50 dark:bg-gray-900/50">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">User</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Product / Plan</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Amount</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Periods</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Source</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Period End</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
          <tr v-for="pool in creditPools" :key="pool.id" class="hover:bg-gray-50 dark:hover:bg-gray-700/50">
            <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">{{ pool.user_email }}</td>
            <td class="px-4 py-3 text-sm">
              <span class="text-gray-900 dark:text-white">{{ pool.product_name }}</span>
              <span class="text-gray-400"> / </span>
              <span class="text-brand-600 dark:text-brand-400 font-medium">{{ pool.plan_name }}</span>
            </td>
            <td class="px-4 py-3 text-sm text-gray-900 dark:text-white font-mono">{{ pool.display_amount }}</td>
            <td class="px-4 py-3 text-sm">
              <span class="text-gray-600 dark:text-gray-300">{{ pool.periods_consumed }}/{{ pool.credit_periods }}</span>
              <span class="text-gray-400 ml-1">({{ pool.periods_remaining }} left)</span>
            </td>
            <td class="px-4 py-3 text-sm">
              <span class="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs font-medium text-gray-700 dark:text-gray-300">
                {{ pool.source }}
              </span>
            </td>
            <td class="px-4 py-3 text-sm">
              <span
                :class="[
                  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                  pool.status === 'active' ? 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300' : '',
                  pool.status === 'refunded' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300' : '',
                  pool.status === 'cancelled' ? 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300' : '',
                  pool.status === 'exhausted' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300' : '',
                  pool.status === 'expired' ? 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300' : '',
                ]"
              >
                {{ pool.status }}
              </span>
            </td>
            <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
              {{ pool.current_period_end ? formatDate(pool.current_period_end) : "—" }}
            </td>
            <td class="px-4 py-3 text-sm space-x-2">
              <button
                @click="viewTransactions(pool)"
                class="text-brand-600 hover:text-brand-800 dark:text-brand-400 dark:hover:text-brand-300 text-xs"
              >
                Transactions
              </button>
              <button
                v-if="pool.status === 'active'"
                @click="openRefundModal(pool)"
                class="text-orange-600 hover:text-orange-800 dark:text-orange-400 dark:hover:text-orange-300 text-xs"
              >
                Refund
              </button>
              <button
                v-if="pool.status === 'active'"
                @click="openAdjustModal(pool)"
                class="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 text-xs"
              >
                Adjust
              </button>
            </td>
          </tr>
          <tr v-if="creditPools.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
              No credit pools found.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex items-center justify-between">
      <span class="text-sm text-gray-600 dark:text-gray-400">
        Page {{ page }} of {{ totalPages }} ({{ totalItems }} total)
      </span>
      <div class="flex gap-2">
        <button
          @click="page--; fetchCredits()"
          :disabled="page <= 1"
          class="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          Previous
        </button>
        <button
          @click="page++; fetchCredits()"
          :disabled="page >= totalPages"
          class="rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>

    <!-- ── Purchase Modal ──────────────────────────────────────────────────── -->
    <div
      v-if="showPurchaseModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="showPurchaseModal = false"
    >
      <div class="w-full max-w-lg rounded-xl bg-white dark:bg-gray-800 p-6 shadow-xl mx-4">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Record Credit Purchase</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">User Email *</label>
            <input
              v-model="purchaseForm.user_email"
              type="email"
              placeholder="user@example.com"
              class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
            />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Product Slug *</label>
              <input
                v-model="purchaseForm.product_slug"
                type="text"
                placeholder="finance"
                class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Plan Slug *</label>
              <input
                v-model="purchaseForm.plan_slug"
                type="text"
                placeholder="standard"
                class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
              />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Amount (cents) *</label>
              <input
                v-model.number="purchaseForm.amount_cents"
                type="number"
                min="0"
                placeholder="900"
                class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Source</label>
              <select
                v-model="purchaseForm.source"
                class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
              >
                <option value="manual">Manual</option>
                <option value="local_gateway">Local Gateway</option>
                <option value="bank_transfer">Bank Transfer</option>
                <option value="cash">Cash</option>
              </select>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Payment Reference</label>
            <input
              v-model="purchaseForm.payment_reference"
              type="text"
              placeholder="TXN-20260529-001"
              class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tax (cents)</label>
            <input
              v-model.number="purchaseForm.tax_cents"
              type="number"
              min="0"
              placeholder="0"
              class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Admin Notes</label>
            <textarea
              v-model="purchaseForm.notes"
              rows="2"
              placeholder="Internal notes..."
              class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
            />
          </div>
          <p v-if="purchaseError" class="text-sm text-red-600 dark:text-red-400">{{ purchaseError }}</p>
        </div>
        <div class="mt-6 flex justify-end gap-3">
          <button
            @click="showPurchaseModal = false"
            class="rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            @click="handlePurchase"
            :disabled="purchaseLoading"
            class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {{ purchaseLoading ? "Saving..." : "Record Purchase" }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── Refund Modal ────────────────────────────────────────────────────── -->
    <div
      v-if="showRefundModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="showRefundModal = false"
    >
      <div class="w-full max-w-md rounded-xl bg-white dark:bg-gray-800 p-6 shadow-xl mx-4">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Refund Credit Pool</h3>
        <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
          This will void all remaining periods for pool #{{ selectedPool?.id }}.
          <strong>{{ selectedPool?.periods_remaining }}</strong> period(s) will be refunded.
        </p>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Reason *</label>
          <textarea
            v-model="refundReason"
            rows="3"
            placeholder="Reason for refund..."
            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
          />
        </div>
        <p v-if="refundError" class="text-sm text-red-600 dark:text-red-400 mt-2">{{ refundError }}</p>
        <div class="mt-6 flex justify-end gap-3">
          <button
            @click="showRefundModal = false"
            class="rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            @click="handleRefund"
            :disabled="refundLoading || !refundReason"
            class="rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50"
          >
            {{ refundLoading ? "Refunding..." : "Refund" }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── Adjust Modal ────────────────────────────────────────────────────── -->
    <div
      v-if="showAdjustModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="showAdjustModal = false"
    >
      <div class="w-full max-w-md rounded-xl bg-white dark:bg-gray-800 p-6 shadow-xl mx-4">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Adjust Credit Balance</h3>
        <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
          Pool #{{ selectedPool?.id }} — currently {{ selectedPool?.credit_periods }} periods, {{ selectedPool?.periods_remaining }} remaining.
        </p>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Period Delta * (positive to add, negative to remove)</label>
          <input
            v-model.number="adjustPayload.periods_delta"
            type="number"
            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
          />
        </div>
        <div class="mt-3">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Reason *</label>
          <textarea
            v-model="adjustPayload.reason"
            rows="2"
            placeholder="Reason for adjustment..."
            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white"
          />
        </div>
        <p v-if="adjustError" class="text-sm text-red-600 dark:text-red-400 mt-2">{{ adjustError }}</p>
        <div class="mt-6 flex justify-end gap-3">
          <button
            @click="showAdjustModal = false"
            class="rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            @click="handleAdjust"
            :disabled="adjustLoading || !adjustPayload.reason || adjustPayload.periods_delta === 0"
            class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {{ adjustLoading ? "Adjusting..." : "Adjust" }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── Transactions Modal ──────────────────────────────────────────────── -->
    <div
      v-if="showTransactionsModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="showTransactionsModal = false"
    >
      <div class="w-full max-w-2xl rounded-xl bg-white dark:bg-gray-800 p-6 shadow-xl mx-4 max-h-[80vh] overflow-y-auto">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Transaction History — Pool #{{ selectedPool?.id }}
        </h3>
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
          <thead>
            <tr>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Action</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Δ Periods</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Balance</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Reason</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr v-for="tx in poolTransactions" :key="tx.id">
              <td class="px-3 py-2 text-gray-900 dark:text-white">{{ tx.action }}</td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-400 font-mono">{{ tx.periods_delta }}</td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-400 font-mono">{{ tx.periods_balance }}</td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-400">{{ tx.reason || "—" }}</td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-400">{{ formatDate(tx.created_at) }}</td>
            </tr>
            <tr v-if="poolTransactions.length === 0">
              <td colspan="5" class="px-3 py-6 text-center text-gray-500">No transactions.</td>
            </tr>
          </tbody>
        </table>
        <div class="mt-4 flex justify-end">
          <button
            @click="showTransactionsModal = false"
            class="rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { creditsApi, type CreditPool, type CreditTransaction } from "@/lib/credits";

// ── State ───────────────────────────────────────────────────────────────────

const creditPools = ref<CreditPool[]>([]);
const search = ref("");
const filterStatus = ref("");
const filterSource = ref("");
const page = ref(1);
const page_size = ref(20);
const totalItems = ref(0);
const totalPages = ref(1);

// Purchase modal
const showPurchaseModal = ref(false);
const purchaseLoading = ref(false);
const purchaseError = ref<string | null>(null);
const purchaseForm = reactive({
  user_email: "",
  product_slug: "",
  plan_slug: "",
  amount_cents: 0,
  currency: "USD",
  source: "manual",
  payment_reference: "",
  tax_cents: 0,
  notes: "",
});

// Refund modal
const showRefundModal = ref(false);
const refundLoading = ref(false);
const refundError = ref<string | null>(null);
const refundReason = ref("");

// Adjust modal
const showAdjustModal = ref(false);
const adjustLoading = ref(false);
const adjustError = ref<string | null>(null);
const adjustPayload = reactive({
  periods_delta: 0,
  reason: "",
});

// Transactions modal
const showTransactionsModal = ref(false);
const poolTransactions = ref<CreditTransaction[]>([]);

const selectedPool = ref<CreditPool | null>(null);

// ── Methods ─────────────────────────────────────────────────────────────────

async function fetchCredits() {
  try {
    const res = await creditsApi.adminListCredits({
      page: page.value,
      page_size: page.value_size,
      status: filterStatus.value || undefined,
      source: filterSource.value || undefined,
      search: search.value || undefined,
    });
    creditPools.value = res.items || (res as unknown as CreditPool[]);
    totalItems.value = res.total || res.items.length;
    totalPages.value = Math.ceil(totalItems.value / page.value_size) || 1;
  } catch (err) {
    console.error("Failed to fetch credit pools:", err);
  }
}

function openPurchaseModal() {
  purchaseForm.user_email = "";
  purchaseForm.product_slug = "";
  purchaseForm.plan_slug = "";
  purchaseForm.amount_cents = 0;
  purchaseForm.source = "manual";
  purchaseForm.payment_reference = "";
  purchaseForm.tax_cents = 0;
  purchaseForm.notes = "";
  purchaseError.value = null;
  showPurchaseModal.value = true;
}

async function handlePurchase() {
  if (!purchaseForm.user_email || !purchaseForm.product_slug || !purchaseForm.plan_slug || purchaseForm.amount_cents <= 0) {
    purchaseError.value = "Please fill in all required fields.";
    return;
  }
  purchaseLoading.value = true;
  purchaseError.value = null;
  try {
    await creditsApi.adminPurchaseCredit(purchaseForm);
    showPurchaseModal.value = false;
    await fetchCredits();
  } catch (err: any) {
    purchaseError.value = err?.message || "Failed to create credit purchase.";
  } finally {
    purchaseLoading.value = false;
  }
}

function openRefundModal(pool: CreditPool) {
  selectedPool.value = pool;
  refundReason.value = "";
  refundError.value = null;
  showRefundModal.value = true;
}

async function handleRefund() {
  if (!selectedPool.value || !refundReason.value) return;
  refundLoading.value = true;
  refundError.value = null;
  try {
    await creditsApi.adminRefundCredit(selectedPool.value.id, { reason: refundReason.value });
    showRefundModal.value = false;
    await fetchCredits();
  } catch (err: any) {
    refundError.value = err?.message || "Failed to refund.";
  } finally {
    refundLoading.value = false;
  }
}

function openAdjustModal(pool: CreditPool) {
  selectedPool.value = pool;
  adjustPayload.periods_delta = 0;
  adjustPayload.reason = "";
  adjustError.value = null;
  showAdjustModal.value = true;
}

async function handleAdjust() {
  if (!selectedPool.value || adjustPayload.periods_delta === 0 || !adjustPayload.reason) return;
  adjustLoading.value = true;
  adjustError.value = null;
  try {
    await creditsApi.adminAdjustCredit(selectedPool.value.id, adjustPayload);
    showAdjustModal.value = false;
    await fetchCredits();
  } catch (err: any) {
    adjustError.value = err?.message || "Failed to adjust.";
  } finally {
    adjustLoading.value = false;
  }
}

async function viewTransactions(pool: CreditPool) {
  selectedPool.value = pool;
  showTransactionsModal.value = true;
  poolTransactions.value = [];
  try {
    const detail = await creditsApi.adminGetCreditPool(pool.id);
    poolTransactions.value = detail.transactions || [];
  } catch (err) {
    console.error("Failed to fetch transactions:", err);
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(fetchCredits);
</script>
