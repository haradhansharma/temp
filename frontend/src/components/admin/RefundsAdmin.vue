<script setup lang="ts">
/**
 * RefundsAdmin — Refund management page for /admin/refunds.
 *
 * Features:
 *   - Searchable, filterable data table with refunds
 *   - Filters: status dropdown, reason category dropdown, date range
 *   - Approve/reject modals with refund details, notes textarea, confirm button
 *   - Two-person rule enforcement (approver cannot be same as initiator)
 *   - Server-side pagination and filtering
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable, AdminFilterBar,
 * AdminConfirmDialog, AdminStatusBadge.
 */

import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage, getCurrentUser } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import {
  adminApi,
  formatDateTime,
  getRefundStatusColor,
} from "@/lib/admin";
import type {
  RefundItem,
  PaginationMeta,
} from "@/lib/admin";

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

const refunds = ref<RefundItem[]>([]);
const meta = ref<PaginationMeta>({
  total_items: 0,
  total_pages: 1,
  current_page: 1,
  page_size: 20,
  has_next: false,
  has_previous: false,
});

// Current admin user (for two-person rule)
const currentAdminId = ref<number | null>(null);

// Filters
const search = ref("");
const statusFilter = ref("");
const categoryFilter = ref("");
const dateFrom = ref("");
const dateTo = ref("");
const currentPage = ref(1);

// Approve dialog
const showApproveDialog = ref(false);
const approveTargetRefund = ref<RefundItem | null>(null);
const approveNotes = ref("");

// Reject dialog
const showRejectDialog = ref(false);
const rejectTargetRefund = ref<RefundItem | null>(null);
const rejectNotes = ref("");

// Detail modal (view full refund details)
const showDetailModal = ref(false);
const detailRefund = ref<RefundItem | null>(null);

// ─── Reason categories (synced with backend Refund.reason_category) ────────

const REASON_CATEGORIES = [
  { value: "customer_request", label: "Customer Request" },
  { value: "billing_error", label: "Billing Error" },
  { value: "goodwill", label: "Goodwill" },
  { value: "policy", label: "Policy" },
  { value: "chargeback", label: "Chargeback" },
];

const REFUND_STATUSES = [
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

// ─── Column definitions ──────────────────────────────────────────────────────

const columns = computed<ColumnDef[]>(() => [
  { key: "subscription_info", label: "Subscription", sortable: false },
  { key: "amount_cents", label: "Amount", align: "right", width: "120px" },
  { key: "status", label: "Status", align: "center", width: "110px" },
  { key: "reason_category", label: "Category", width: "130px", hideOnMobile: true },
  { key: "initiated_by_email", label: "Initiated By", width: "160px", hideOnMobile: true },
  { key: "approved_by_email", label: "Approved By", width: "160px", hideOnMobile: true },
  { key: "created_at", label: "Date", sortable: true, width: "140px", hideOnMobile: true },
  { key: "actions", label: "", align: "right", width: "110px" },
]);

// ─── Filter definitions ──────────────────────────────────────────────────────

const filters = computed<FilterDef[]>(() => [
  {
    key: "status",
    label: "Status",
    options: REFUND_STATUSES,
    value: statusFilter.value,
    placeholder: "All Statuses",
  },
  {
    key: "category",
    label: "Category",
    options: REASON_CATEGORIES,
    value: categoryFilter.value,
    placeholder: "All Categories",
  },
]);

const activeFilterCount = computed(() => {
  let count = 0;
  if (statusFilter.value) count++;
  if (categoryFilter.value) count++;
  if (dateFrom.value) count++;
  if (dateTo.value) count++;
  return count;
});

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchRefunds() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Record<string, unknown> = {
      page: currentPage.value,
      page_size: 20,
    };
    if (statusFilter.value) params.status = statusFilter.value;
    if (categoryFilter.value) params.reason_category = categoryFilter.value;
    if (dateFrom.value) params.date_from = dateFrom.value;
    if (dateTo.value) params.date_to = dateTo.value;

    const data = await adminApi.listRefunds(params);
    refunds.value = data.results;
    meta.value = data.meta;
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;

  // Fetch current admin user for two-person rule
  try {
    const user = await getCurrentUser();
    currentAdminId.value = user.id;
  } catch {
    // Non-blocking — two-person rule will still be enforced server-side
  }

  await fetchRefunds();
});

// ─── Pagination ──────────────────────────────────────────────────────────────

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchRefunds();
}

// ─── Filter events ───────────────────────────────────────────────────────────

function handleFilterUpdate({ key, value }: { key: string; value: string }) {
  if (key === "status") statusFilter.value = value;
  if (key === "category") categoryFilter.value = value;
  currentPage.value = 1;
  fetchRefunds();
}

function handleDateFromUpdate(value: string) {
  dateFrom.value = value;
  currentPage.value = 1;
  fetchRefunds();
}

function handleDateToUpdate(value: string) {
  dateTo.value = value;
  currentPage.value = 1;
  fetchRefunds();
}

function handleClearFilters() {
  search.value = "";
  statusFilter.value = "";
  categoryFilter.value = "";
  dateFrom.value = "";
  dateTo.value = "";
  currentPage.value = 1;
  fetchRefunds();
}

// ─── Sort ────────────────────────────────────────────────────────────────────

function handleSort({ key, direction }: { key: string; direction: "asc" | "desc" }) {
  refunds.value.sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[key];
    const bVal = (b as Record<string, unknown>)[key];
    if (aVal == null || bVal == null) return 0;
    const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
    return direction === "asc" ? cmp : -cmp;
  });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Format refund amount from cents to currency display.
 */
function formatAmount(cents: number, currency: string): string {
  const amount = cents / 100;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
      minimumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency} ${(amount).toFixed(2)}`;
  }
}

/**
 * Format reason category for display.
 */
function formatCategory(category: string): string {
  if (!category) return "—";
  return category
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Check if the current admin is the same person who initiated a refund.
 * Used for client-side two-person rule enforcement.
 */
function isInitiator(refund: RefundItem): boolean {
  if (!currentAdminId.value || !refund.initiated_by_id) return false;
  return currentAdminId.value === refund.initiated_by_id;
}

/**
 * Check if a refund can be approved (pending + not self-initiated).
 */
function canApprove(refund: RefundItem): boolean {
  return refund.status === "pending" && !isInitiator(refund);
}

/**
 * Check if a refund can be rejected (pending only).
 */
function canReject(refund: RefundItem): boolean {
  return refund.status === "pending";
}

// ─── Detail modal ────────────────────────────────────────────────────────────

function openDetailModal(refund: RefundItem) {
  detailRefund.value = refund;
  showDetailModal.value = true;
}

function closeDetailModal() {
  showDetailModal.value = false;
  detailRefund.value = null;
}

// ─── Approve refund ─────────────────────────────────────────────────────────

function openApproveDialog(refund: RefundItem) {
  approveTargetRefund.value = refund;
  approveNotes.value = "";
  showApproveDialog.value = true;
}

async function confirmApprove() {
  if (!approveTargetRefund.value) return;
  const refundId = approveTargetRefund.value.id;
  actionLoading.value = `approve-${refundId}`;
  try {
    await adminApi.approveRefund(refundId, {
      approved: true,
      notes: approveNotes.value,
    });
    showToast("Refund approved successfully.", "success");
    showApproveDialog.value = false;
    approveTargetRefund.value = null;
    await fetchRefunds();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Reject refund ───────────────────────────────────────────────────────────

function openRejectDialog(refund: RefundItem) {
  rejectTargetRefund.value = refund;
  rejectNotes.value = "";
  showRejectDialog.value = true;
}

async function confirmReject() {
  if (!rejectTargetRefund.value) return;
  const refundId = rejectTargetRefund.value.id;
  actionLoading.value = `reject-${refundId}`;
  try {
    await adminApi.rejectRefund(refundId, {
      approved: false,
      notes: rejectNotes.value,
    });
    showToast("Refund rejected.", "success");
    showRejectDialog.value = false;
    rejectTargetRefund.value = null;
    await fetchRefunds();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Page Header -->
    <AdminPageHeader
      title="Refunds"
      description="Review and process refund requests with two-person approval."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Refunds' }]"
    />

    <!-- Error state -->
    <div
      v-if="loadError"
      class="card flex flex-col items-center gap-4 p-10 text-center"
    >
      <svg class="h-12 w-12 text-destructive/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <div>
        <p class="font-medium text-foreground">Failed to load refunds</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchRefunds">Try again</button>
    </div>

    <template v-else>
      <!-- Filter Bar -->
      <AdminFilterBar
        v-model:search="search"
        :filters="filters"
        :active-count="activeFilterCount"
        search-placeholder="Filter refunds..."
        :show-date-range="true"
        :date-from="dateFrom"
        :date-to="dateTo"
        @update:filter="handleFilterUpdate"
        @update:date-from="handleDateFromUpdate"
        @update:date-to="handleDateToUpdate"
        @clear="handleClearFilters"
      />

      <!-- Data Table -->
      <AdminDataTable
        :columns="columns"
        :rows="refunds"
        :meta="meta"
        :loading="loading"
        row-key="id"
        empty-message="No refunds found"
        empty-description="No refunds match the current filters."
        @page-change="handlePageChange"
        @sort="handleSort"
      >
        <!-- Subscription info cell -->
        <template #cell-subscription_info="{ row }">
          <div class="min-w-0">
            <p class="truncate text-sm font-medium text-foreground">{{ row.user_email || '—' }}</p>
            <p v-if="row.product_name" class="truncate text-xs text-muted-foreground">
              {{ row.product_name }}
              <span v-if="row.plan_name"> / {{ row.plan_name }}</span>
            </p>
          </div>
        </template>

        <!-- Amount cell -->
        <template #cell-amount_cents="{ row }">
          <span class="font-mono text-sm font-medium text-foreground">
            {{ formatAmount(row.amount_cents, row.currency) }}
          </span>
        </template>

        <!-- Status cell -->
        <template #cell-status="{ row }">
          <AdminStatusBadge
            :status="row.status"
            type="refund"
          />
        </template>

        <!-- Reason category cell -->
        <template #cell-reason_category="{ row }">
          <span class="text-sm text-muted-foreground">
            {{ formatCategory(row.reason_category) }}
          </span>
        </template>

        <!-- Initiated by cell -->
        <template #cell-initiated_by_email="{ row }">
          <span class="text-sm text-muted-foreground">
            {{ row.initiated_by_email || '—' }}
          </span>
        </template>

        <!-- Approved by cell -->
        <template #cell-approved_by_email="{ row }">
          <span class="text-sm text-muted-foreground">
            {{ row.approved_by_email || '—' }}
          </span>
        </template>

        <!-- Date cell -->
        <template #cell-created_at="{ row }">
          <span class="text-sm text-muted-foreground">
            {{ formatDateTime(row.created_at) }}
          </span>
        </template>

        <!-- Actions cell -->
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end gap-1" @click.stop>
            <!-- View details -->
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="View Details"
              @click="openDetailModal(row)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </button>

            <!-- Approve button (only for pending refunds where current admin is NOT the initiator) -->
            <button
              v-if="canApprove(row)"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-green-50 hover:text-green-600 dark:hover:bg-green-950 dark:hover:text-green-400"
              title="Approve Refund"
              :disabled="actionLoading === `approve-${row.id}`"
              @click="openApproveDialog(row)"
            >
              <svg v-if="actionLoading === `approve-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            </button>

            <!-- Self-approve warning (pending refund initiated by current admin) -->
            <span
              v-if="row.status === 'pending' && isInitiator(row)"
              class="inline-flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-400"
              title="You initiated this refund. Another admin must approve it (two-person rule)."
            >
              <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </span>

            <!-- Reject button (only for pending refunds) -->
            <button
              v-if="canReject(row)"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
              title="Reject Refund"
              :disabled="actionLoading === `reject-${row.id}`"
              @click="openRejectDialog(row)"
            >
              <svg v-if="actionLoading === `reject-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Refund Detail Modal                                                    -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <Teleport to="body">
      <div
        v-if="showDetailModal && detailRefund"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Refund Details"
      >
        <!-- Backdrop -->
        <div
          class="fixed inset-0 bg-black/60 backdrop-blur-sm"
          @click="closeDetailModal"
        />

        <!-- Panel -->
        <div class="relative z-10 w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl animate-scale-in">
          <div class="flex items-start justify-between mb-4">
            <h3 class="text-lg font-semibold text-foreground">Refund Details</h3>
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              @click="closeDetailModal"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div class="space-y-4">
            <!-- Status + Amount row -->
            <div class="flex items-center justify-between">
              <AdminStatusBadge
                :status="detailRefund.status"
                type="refund"
              />
              <span class="font-mono text-lg font-semibold text-foreground">
                {{ formatAmount(detailRefund.amount_cents, detailRefund.currency) }}
              </span>
            </div>

            <!-- Detail grid -->
            <div class="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p class="text-xs font-medium text-muted-foreground">User</p>
                <p class="text-foreground">{{ detailRefund.user_email || '—' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Product / Plan</p>
                <p class="text-foreground">
                  {{ detailRefund.product_name || '—' }}
                  <span v-if="detailRefund.plan_name"> / {{ detailRefund.plan_name }}</span>
                </p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Category</p>
                <p class="text-foreground">{{ formatCategory(detailRefund.reason_category) }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Subscription ID</p>
                <p class="text-foreground">{{ detailRefund.subscription_id }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Initiated By</p>
                <p class="text-foreground">{{ detailRefund.initiated_by_email || '—' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Initiated IP</p>
                <p class="font-mono text-xs text-foreground">{{ detailRefund.initiated_by_ip || '—' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Approved By</p>
                <p class="text-foreground">{{ detailRefund.approved_by_email || '—' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Approved At</p>
                <p class="text-foreground">{{ detailRefund.approved_at ? formatDateTime(detailRefund.approved_at) : '—' }}</p>
              </div>
              <div class="col-span-2">
                <p class="text-xs font-medium text-muted-foreground">Stripe Refund ID</p>
                <p class="font-mono text-xs text-foreground">{{ detailRefund.stripe_refund_id || '—' }}</p>
              </div>
              <div class="col-span-2">
                <p class="text-xs font-medium text-muted-foreground">Stripe Charge ID</p>
                <p class="font-mono text-xs text-foreground">{{ detailRefund.stripe_charge_id || '—' }}</p>
              </div>
              <div class="col-span-2">
                <p class="text-xs font-medium text-muted-foreground">Reason</p>
                <p class="text-foreground">{{ detailRefund.reason || '—' }}</p>
              </div>
              <div v-if="detailRefund.admin_notes" class="col-span-2">
                <p class="text-xs font-medium text-muted-foreground">Admin Notes</p>
                <div class="mt-1 rounded-lg bg-muted/50 p-3 text-xs text-foreground border border-border whitespace-pre-wrap">
                  {{ detailRefund.admin_notes }}
                </div>
              </div>
              <div class="col-span-2">
                <p class="text-xs font-medium text-muted-foreground">Created</p>
                <p class="text-foreground">{{ formatDateTime(detailRefund.created_at) }}</p>
              </div>
            </div>

            <!-- Two-person rule warning -->
            <div
              v-if="detailRefund.status === 'pending' && isInitiator(detailRefund)"
              class="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/50"
            >
              <div class="flex items-start gap-2">
                <svg class="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div>
                  <p class="text-sm font-medium text-amber-800 dark:text-amber-300">Two-Person Rule</p>
                  <p class="mt-0.5 text-xs text-amber-700 dark:text-amber-400">
                    You initiated this refund. Another staff member must approve it.
                  </p>
                </div>
              </div>
            </div>

            <!-- Action buttons for pending refunds -->
            <div
              v-if="detailRefund.status === 'pending'"
              class="flex items-center justify-end gap-2 border-t border-border pt-4"
            >
              <button
                type="button"
                class="btn-ghost px-4 py-2 text-sm"
                @click="closeDetailModal"
              >
                Close
              </button>
              <button
                type="button"
                class="btn-destructive px-4 py-2 text-sm"
                :disabled="actionLoading === `reject-${detailRefund.id}`"
                @click="closeDetailModal(); openRejectDialog(detailRefund)"
              >
                <svg v-if="actionLoading === `reject-${detailRefund.id}`" class="mr-1.5 h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Reject
              </button>
              <button
                v-if="canApprove(detailRefund)"
                type="button"
                class="btn-primary px-4 py-2 text-sm"
                :disabled="actionLoading === `approve-${detailRefund.id}`"
                @click="closeDetailModal(); openApproveDialog(detailRefund)"
              >
                <svg v-if="actionLoading === `approve-${detailRefund.id}`" class="mr-1.5 h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Approve
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Approve Refund Confirmation Dialog                                     -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showApproveDialog"
      title="Approve Refund"
      :message="'Approve refund of ' + (approveTargetRefund ? formatAmount(approveTargetRefund.amount_cents, approveTargetRefund.currency) : '') + ' for ' + (approveTargetRefund?.user_email ?? '') + '?'"
      detail="This will process the refund. The two-person rule ensures you did not initiate this refund. This action will set the refund status to 'completed'."
      confirm-label="Approve Refund"
      :destructive="false"
      :loading="actionLoading?.startsWith('approve-')"
      @confirm="confirmApprove"
    >
      <!-- Refund summary in dialog -->
      <div v-if="approveTargetRefund" class="mt-3 space-y-2 rounded-lg bg-muted/50 p-3 border border-border">
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Product</span>
          <span class="text-foreground">{{ approveTargetRefund.product_name || '—' }}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Plan</span>
          <span class="text-foreground">{{ approveTargetRefund.plan_name || '—' }}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Initiated By</span>
          <span class="text-foreground">{{ approveTargetRefund.initiated_by_email || '—' }}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Reason</span>
          <span class="text-foreground">{{ approveTargetRefund.reason || '—' }}</span>
        </div>
      </div>
      <div class="mt-3">
        <label class="block text-xs font-medium text-muted-foreground mb-1">Approval Notes (optional)</label>
        <textarea
          v-model="approveNotes"
          rows="2"
          class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600 resize-none"
          placeholder="Add notes about this approval..."
        />
      </div>
    </AdminConfirmDialog>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Reject Refund Confirmation Dialog                                      -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showRejectDialog"
      title="Reject Refund"
      :message="'Reject refund of ' + (rejectTargetRefund ? formatAmount(rejectTargetRefund.amount_cents, rejectTargetRefund.currency) : '') + ' for ' + (rejectTargetRefund?.user_email ?? '') + '?'"
      detail="This will set the refund status to 'failed'. The customer will not receive a refund. This action is reversible by creating a new refund."
      confirm-label="Reject Refund"
      :destructive="true"
      :loading="actionLoading?.startsWith('reject-')"
      @confirm="confirmReject"
    >
      <!-- Refund summary in dialog -->
      <div v-if="rejectTargetRefund" class="mt-3 space-y-2 rounded-lg bg-muted/50 p-3 border border-border">
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Product</span>
          <span class="text-foreground">{{ rejectTargetRefund.product_name || '—' }}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Plan</span>
          <span class="text-foreground">{{ rejectTargetRefund.plan_name || '—' }}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Initiated By</span>
          <span class="text-foreground">{{ rejectTargetRefund.initiated_by_email || '—' }}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Reason</span>
          <span class="text-foreground">{{ rejectTargetRefund.reason || '—' }}</span>
        </div>
      </div>
      <div class="mt-3">
        <label class="block text-xs font-medium text-muted-foreground mb-1">Rejection Reason</label>
        <textarea
          v-model="rejectNotes"
          rows="2"
          class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600 resize-none"
          placeholder="Provide a reason for rejecting this refund..."
        />
      </div>
    </AdminConfirmDialog>
  </div>
</template>
