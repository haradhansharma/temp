<script setup lang="ts">
/**
 * CreditManagement — Admin credit pools management page.
 *
 * Features:
 *   - Paginated, searchable list of all credit pools
 *   - Filters by status, source, and product
 *   - Actions: view details, refund, adjust balance
 *   - Create new credit purchase record (admin entry)
 *
 * Used on: /admin/credits
 */

import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { creditsApi } from "@/lib/credits";
import type { CreditPool, CreditTransaction, PaginatedResponse } from "@/lib/credits";

import AdminPageHeader from "@/components/admin/AdminPageHeader.vue";
import AdminFilterBar from "@/components/admin/AdminFilterBar.vue";
import AdminDataTable from "@/components/admin/AdminDataTable.vue";
import type { ColumnDef } from "@/components/admin/AdminDataTable.vue";
import type { FilterDef } from "@/components/admin/AdminFilterBar.vue";
import AdminConfirmDialog from "@/components/admin/AdminConfirmDialog.vue";
import AdminStatusBadge from "@/components/admin/AdminStatusBadge.vue";

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const loadError = ref<string | null>(null);
const actionLoading = ref<string | null>(null);

const credits = ref<CreditPool[]>([]);
const meta = ref({
  total_items: 0,
  total_pages: 1,
  current_page: 1,
  page_size: 20,
  has_next: false,
  has_previous: false,
});

// Filters
const search = ref("");
const statusFilter = ref("");
const sourceFilter = ref("");
const currentPage = ref(1);

// Detail modal
const showDetailModal = ref(false);
const selectedCredit = ref<(CreditPool & { transactions: CreditTransaction[] }) | null>(null);
const detailLoading = ref(false);

// Refund modal
const showRefundModal = ref(false);
const refundTarget = ref<CreditPool | null>(null);
const refundReason = ref("");

// Adjust modal
const showAdjustModal = ref(false);
const adjustTarget = ref<CreditPool | null>(null);
const adjustPeriods = ref(0);
const adjustReason = ref("");

// Create modal
const showCreateModal = ref(false);
const createForm = ref({
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
const createLoading = ref(false);

// ─── Column definitions ──────────────────────────────────────────────────────

const columns = computed<ColumnDef[]>(() => [
  { key: "id", label: "ID", sortable: true, width: "70px" },
  { key: "user_email", label: "User", sortable: true },
  { key: "product_name", label: "Product", hideOnMobile: true },
  { key: "plan_name", label: "Plan", hideOnMobile: true },
  { key: "status", label: "Status", align: "center", width: "100px" },
  { key: "periods_remaining", label: "Periods", align: "center", width: "90px" },
  { key: "amount", label: "Amount", align: "right", width: "100px" },
  { key: "created_at", label: "Created", sortable: true, width: "120px", hideOnMobile: true },
  { key: "actions", label: "", align: "right", width: "130px" },
]);

// ─── Filter definitions ──────────────────────────────────────────────────────

const filters = computed<FilterDef[]>(() => [
  {
    key: "status",
    label: "Status",
    options: [
      { value: "active", label: "Active" },
      { value: "exhausted", label: "Exhausted" },
      { value: "expired", label: "Expired" },
      { value: "refunded", label: "Refunded" },
      { value: "cancelled", label: "Cancelled" },
    ],
    value: statusFilter.value,
    placeholder: "All Statuses",
  },
  {
    key: "source",
    label: "Source",
    options: [
      { value: "manual", label: "Manual" },
      { value: "bank_transfer", label: "Bank Transfer" },
      { value: "local_gateway", label: "Local Gateway" },
      { value: "cash", label: "Cash" },
    ],
    value: sourceFilter.value,
    placeholder: "All Sources",
  },
]);

const activeFilterCount = computed(() => {
  let count = 0;
  if (statusFilter.value) count++;
  if (sourceFilter.value) count++;
  return count;
});

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchCredits() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Record<string, unknown> = {
      page: currentPage.value,
      page_size: 20,
    };
    if (search.value.trim()) params.search = search.value.trim();
    if (statusFilter.value) params.status = statusFilter.value;
    if (sourceFilter.value) params.source = sourceFilter.value;

    const data: PaginatedResponse<CreditPool> = await creditsApi.adminListCredits(params);
    credits.value = data.items;
    const totalPages = Math.ceil(data.total / data.page_size) || 1;
    meta.value = {
      total_items: data.total,
      total_pages: totalPages,
      current_page: data.page,
      page_size: data.page_size,
      has_next: data.has_next,
      has_previous: data.has_previous,
    };
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchCredits();
});

// ─── Pagination ──────────────────────────────────────────────────────────────

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchCredits();
}

// ─── Filter events ───────────────────────────────────────────────────────────

function handleFilterUpdate({ key, value }: { key: string; value: string }) {
  if (key === "status") statusFilter.value = value;
  if (key === "source") sourceFilter.value = value;
  currentPage.value = 1;
  fetchCredits();
}

function handleClearFilters() {
  search.value = "";
  statusFilter.value = "";
  sourceFilter.value = "";
  currentPage.value = 1;
  fetchCredits();
}

// ─── Actions ─────────────────────────────────────────────────────────────────

async function viewDetail(credit: CreditPool) {
  detailLoading.value = true;
  showDetailModal.value = true;
  try {
    const data = await creditsApi.adminGetCreditPool(credit.id);
    selectedCredit.value = data;
  } catch (err) {
    showToast(getErrorMessage(err), "error");
    showDetailModal.value = false;
  } finally {
    detailLoading.value = false;
  }
}

function openRefundModal(credit: CreditPool) {
  refundTarget.value = credit;
  refundReason.value = "";
  showRefundModal.value = true;
}

async function confirmRefund() {
  if (!refundTarget.value) return;
  actionLoading.value = `refund-${refundTarget.value.id}`;
  try {
    await creditsApi.adminRefundCredit(refundTarget.value.id, {
      reason: refundReason.value,
    });
    showToast("Credit pool refunded successfully", "success");
    showRefundModal.value = false;
    refundTarget.value = null;
    await fetchCredits();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

function openAdjustModal(credit: CreditPool) {
  adjustTarget.value = credit;
  adjustPeriods.value = 0;
  adjustReason.value = "";
  showAdjustModal.value = true;
}

async function confirmAdjust() {
  if (!adjustTarget.value) return;
  actionLoading.value = `adjust-${adjustTarget.value.id}`;
  try {
    await creditsApi.adminAdjustCredit(adjustTarget.value.id, {
      periods_delta: adjustPeriods.value,
      reason: adjustReason.value,
    });
    showToast("Credit pool adjusted successfully", "success");
    showAdjustModal.value = false;
    adjustTarget.value = null;
    await fetchCredits();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

function openCreateModal() {
  createForm.value = {
    user_email: "",
    product_slug: "",
    plan_slug: "",
    amount_cents: 0,
    currency: "USD",
    source: "manual",
    payment_reference: "",
    tax_cents: 0,
    notes: "",
  };
  showCreateModal.value = true;
}

async function confirmCreate() {
  createLoading.value = true;
  try {
    await creditsApi.adminPurchaseCredit(createForm.value);
    showToast("Credit purchase recorded successfully", "success");
    showCreateModal.value = false;
    await fetchCredits();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    createLoading.value = false;
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString(navigator.language, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function getStatusColor(status: string): string {
  switch (status) {
    case "active": return "green";
    case "exhausted": return "gray";
    case "expired": return "red";
    case "refunded": return "amber";
    case "cancelled": return "gray";
    default: return "gray";
  }
}

function getTransactionActionLabel(action: string): string {
  const labels: Record<string, string> = {
    purchase: "Purchase",
    period_consume: "Period Consumed",
    refund: "Refund",
    adjust: "Adjustment",
    expire: "Expired",
  };
  return labels[action] || action;
}
</script>

<template>
  <div class="space-y-6">
    <!-- Page Header -->
    <AdminPageHeader
      title="Credit Pools"
      description="Manage prepaid credit pools for all users."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Credits' }]"
    >
      <template #actions>
        <button type="button" class="btn-primary text-sm" @click="openCreateModal">
          <svg class="h-4 w-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
          </svg>
          Record Payment
        </button>
      </template>
    </AdminPageHeader>

    <!-- Error state -->
    <div
      v-if="loadError"
      class="card flex flex-col items-center gap-4 p-10 text-center"
    >
      <svg class="h-12 w-12 text-destructive/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <div>
        <p class="font-medium text-foreground">Failed to load credit pools</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchCredits">Try again</button>
    </div>

    <template v-else>
      <!-- Filter Bar -->
      <AdminFilterBar
        v-model:search="search"
        :filters="filters"
        :active-count="activeFilterCount"
        search-placeholder="Search by user email..."
        @update:filter="handleFilterUpdate"
        @clear="handleClearFilters"
        @search="fetchCredits"
      />

      <!-- Data Table -->
      <AdminDataTable
        :columns="columns"
        :rows="credits"
        :meta="meta"
        :loading="loading"
        :clickable="false"
        row-key="id"
        empty-message="No credit pools found"
        empty-description="No credit pools match the current filters."
        @page-change="handlePageChange"
      >
        <!-- ID cell -->
        <template #cell-id="{ row }">
          <span class="font-mono text-sm">{{ row.id }}</span>
        </template>

        <!-- User email cell -->
        <template #cell-user_email="{ row }">
          <div class="min-w-0">
            <p class="truncate font-medium text-foreground">{{ row.user_email || `User #${row.user_id}` }}</p>
          </div>
        </template>

        <!-- Product cell -->
        <template #cell-product_name="{ row }">
          <p class="truncate">{{ row.product_name }}</p>
          <p class="text-xs text-muted-foreground">{{ row.plan_name }}</p>
        </template>

        <!-- Plan cell -->
        <template #cell-plan_name="{ row }">
          <span class="text-sm">{{ row.plan_name }}</span>
        </template>

        <!-- Status cell -->
        <template #cell-status="{ row }">
          <AdminStatusBadge
            :status="row.status"
            type="custom"
            :custom-color="getStatusColor(row.status)"
          />
        </template>

        <!-- Periods cell -->
        <template #cell-periods_remaining="{ row }">
          <span class="text-sm">
            {{ row.periods_remaining }} / {{ row.credit_periods }}
          </span>
        </template>

        <!-- Amount cell -->
        <template #cell-amount="{ row }">
          <p class="font-medium">{{ row.display_amount }}</p>
        </template>

        <!-- Created cell -->
        <template #cell-created_at="{ row }">
          <span class="text-muted-foreground text-sm">{{ formatDate(row.created_at) }}</span>
        </template>

        <!-- Actions cell -->
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end gap-1">
            <!-- View -->
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="View Details"
              :disabled="detailLoading"
              @click="viewDetail(row)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </button>

            <!-- Refund -->
            <button
              v-if="row.status === 'active'"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-amber-50 hover:text-amber-600 dark:hover:bg-amber-950 dark:hover:text-amber-400"
              title="Refund"
              :disabled="actionLoading === `refund-${row.id}`"
              @click="openRefundModal(row)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
            </button>

            <!-- Adjust -->
            <button
              v-if="row.status === 'active'"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-950 dark:hover:text-blue-400"
              title="Adjust Balance"
              :disabled="actionLoading === `adjust-${row.id}`"
              @click="openAdjustModal(row)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
          </div>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Detail Modal                                                            -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <div v-if="showDetailModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showDetailModal = false">
      <div class="bg-background rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div class="p-6 border-b border-border">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">Credit Pool Details</h2>
            <button type="button" class="text-muted-foreground hover:text-foreground" @click="showDetailModal = false">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div v-if="detailLoading" class="p-6 animate-pulse space-y-4">
          <div class="h-4 w-32 rounded bg-muted"></div>
          <div class="h-8 w-48 rounded bg-muted"></div>
        </div>

        <template v-else-if="selectedCredit">
          <div class="p-6 space-y-6">
            <!-- Info Grid -->
            <div class="grid grid-cols-2 gap-4">
              <div>
                <p class="text-xs text-muted-foreground">ID</p>
                <p class="font-mono text-sm">{{ selectedCredit.id }}</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Status</p>
                <AdminStatusBadge
                  :status="selectedCredit.status"
                  type="custom"
                  :custom-color="getStatusColor(selectedCredit.status)"
                />
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Product</p>
                <p class="text-sm font-medium">{{ selectedCredit.product_name }}</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Plan</p>
                <p class="text-sm">{{ selectedCredit.plan_name }}</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Amount</p>
                <p class="text-sm font-semibold">{{ selectedCredit.display_amount }}</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Periods</p>
                <p class="text-sm">{{ selectedCredit.periods_remaining }} / {{ selectedCredit.credit_periods }} remaining</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Source</p>
                <p class="text-sm capitalize">{{ selectedCredit.source }}</p>
              </div>
              <div>
                <p class="text-xs text-muted-foreground">Created</p>
                <p class="text-sm">{{ formatDate(selectedCredit.created_at) }}</p>
              </div>
            </div>

            <!-- Transactions -->
            <div v-if="selectedCredit.transactions && selectedCredit.transactions.length > 0">
              <h3 class="text-sm font-semibold mb-3">Transaction History</h3>
              <div class="border border-border rounded-lg overflow-hidden">
                <table class="w-full text-sm">
                  <thead class="bg-muted/50">
                    <tr>
                      <th class="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Action</th>
                      <th class="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Periods</th>
                      <th class="px-3 py-2 text-right text-xs font-medium text-muted-foreground">Balance</th>
                      <th class="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Reason</th>
                      <th class="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Date</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-border">
                    <tr v-for="tx in selectedCredit.transactions" :key="tx.id">
                      <td class="px-3 py-2">{{ getTransactionActionLabel(tx.action) }}</td>
                      <td class="px-3 py-2 text-right font-mono">
                        <span :class="tx.periods_delta > 0 ? 'text-green-600' : tx.periods_delta < 0 ? 'text-red-600' : ''">
                          {{ tx.periods_delta > 0 ? '+' : '' }}{{ tx.periods_delta }}
                        </span>
                      </td>
                      <td class="px-3 py-2 text-right font-mono">{{ tx.periods_balance }}</td>
                      <td class="px-3 py-2 text-muted-foreground">{{ tx.reason || '—' }}</td>
                      <td class="px-3 py-2 text-muted-foreground">{{ formatDate(tx.created_at) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Refund Modal                                                            -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showRefundModal"
      title="Refund Credit Pool"
      :message="'Refund credit pool #' + (refundTarget?.id || '') + '?'"
      detail="This will mark the pool as refunded and the user will lose remaining periods."
      confirm-label="Refund"
      :destructive="true"
      :loading="actionLoading?.startsWith('refund-')"
      @confirm="confirmRefund"
    >
      <div class="mt-3">
        <label class="block text-xs font-medium text-muted-foreground mb-1">Reason *</label>
        <input
          v-model="refundReason"
          type="text"
          class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          placeholder="Reason for refund..."
        />
      </div>
    </AdminConfirmDialog>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Adjust Modal                                                            -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showAdjustModal"
      title="Adjust Credit Balance"
      :message="'Adjust periods for credit pool #' + (adjustTarget?.id || '') + '?'"
      detail="Add or remove billing periods from this credit pool."
      confirm-label="Adjust"
      :loading="actionLoading?.startsWith('adjust-')"
      @confirm="confirmAdjust"
    >
      <div class="space-y-3 mt-3">
        <div>
          <label class="block text-xs font-medium text-muted-foreground mb-1">Periods Delta *</label>
          <input
            v-model.number="adjustPeriods"
            type="number"
            class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            placeholder="e.g., 1 or -1"
          />
          <p class="mt-1 text-xs text-muted-foreground">Positive to add, negative to remove</p>
        </div>
        <div>
          <label class="block text-xs font-medium text-muted-foreground mb-1">Reason *</label>
          <input
            v-model="adjustReason"
            type="text"
            class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            placeholder="Reason for adjustment..."
          />
        </div>
      </div>
    </AdminConfirmDialog>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Create Modal                                                            -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showCreateModal = false">
      <div class="bg-background rounded-lg shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
        <div class="p-6 border-b border-border">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">Record Credit Purchase</h2>
            <button type="button" class="text-muted-foreground hover:text-foreground" @click="showCreateModal = false">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <form @submit.prevent="confirmCreate" class="p-6 space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1">User Email *</label>
            <input
              v-model="createForm.user_email"
              type="email"
              class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder="user@example.com"
              required
            />
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1">Product Slug *</label>
              <input
                v-model="createForm.product_slug"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                placeholder="finance"
                required
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">Plan Slug *</label>
              <input
                v-model="createForm.plan_slug"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                placeholder="standard"
                required
              />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1">Amount (cents) *</label>
              <input
                v-model.number="createForm.amount_cents"
                type="number"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                placeholder="900"
                required
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">Currency</label>
              <select
                v-model="createForm.currency"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
              </select>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1">Source</label>
              <select
                v-model="createForm.source"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="manual">Manual</option>
                <option value="bank_transfer">Bank Transfer</option>
                <option value="cash">Cash</option>
                <option value="local_gateway">Local Gateway</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">Tax (cents)</label>
              <input
                v-model.number="createForm.tax_cents"
                type="number"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                placeholder="0"
              />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">Payment Reference</label>
            <input
              v-model="createForm.payment_reference"
              type="text"
              class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder="TXN-001"
            />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">Notes</label>
            <textarea
              v-model="createForm.notes"
              rows="2"
              class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm resize-none"
              placeholder="Internal notes..."
            />
          </div>

          <div class="flex justify-end gap-3 pt-2">
            <button type="button" class="btn-secondary text-sm" @click="showCreateModal = false">
              Cancel
            </button>
            <button type="submit" :disabled="createLoading" class="btn-primary text-sm">
              {{ createLoading ? "Creating..." : "Create" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
