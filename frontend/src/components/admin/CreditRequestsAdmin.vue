<script setup lang="ts">
/**
 * CreditRequestsAdmin — Admin credit purchase requests management.
 *
 * Features:
 *   - List all pending/approved/rejected credit purchase requests
 *   - View request details with user and payment info
 *   - Approve request (creates CreditPool + CreditInvoice)
 *   - Reject request with reason
 *   - Filter by status and search by user email
 *
 * Used on: /admin/credit-requests
 */

import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { creditsApi } from "@/lib/credits";
import type { CreditRequest, PaginationMeta } from "@/lib/credits";

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

const requests = ref<CreditRequest[]>([]);
const meta = ref<PaginationMeta>({
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
const currentPage = ref(1);

// Detail modal
const showDetailModal = ref(false);
const selectedRequest = ref<CreditRequest | null>(null);

// Approve modal
const showApproveModal = ref(false);
const approveTarget = ref<CreditRequest | null>(null);

// Reject modal
const showRejectModal = ref(false);
const rejectTarget = ref<CreditRequest | null>(null);
const rejectReason = ref("");

// ─── Column definitions ──────────────────────────────────────────────────────

const columns = computed<ColumnDef[]>(() => [
  { key: "id", label: "ID", sortable: true, width: "70px" },
  { key: "user_email", label: "User", sortable: true },
  { key: "product_name", label: "Product", hideOnMobile: true },
  { key: "plan_name", label: "Plan", hideOnMobile: true },
  { key: "amount", label: "Amount", align: "right", width: "100px" },
  { key: "status", label: "Status", align: "center", width: "100px" },
  { key: "created_at", label: "Submitted", sortable: true, width: "120px", hideOnMobile: true },
  { key: "actions", label: "", align: "right", width: "130px" },
]);

// ─── Filter definitions ──────────────────────────────────────────────────────

const filters = computed<FilterDef[]>(() => [
  {
    key: "status",
    label: "Status",
    options: [
      { value: "pending", label: "Pending" },
      { value: "approved", label: "Approved" },
      { value: "rejected", label: "Rejected" },
    ],
    value: statusFilter.value,
    placeholder: "All Statuses",
  },
]);

const activeFilterCount = computed(() => {
  return statusFilter.value ? 1 : 0;
});

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchRequests() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Record<string, unknown> = {
      page: currentPage.value,
      page_size: 20,
    };
    if (search.value.trim()) params.search = search.value.trim();
    if (statusFilter.value) params.status = statusFilter.value;

    const data = await creditsApi.adminListCreditRequests(params);
    requests.value = data.results;
    meta.value = data.meta;
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchRequests();
});

// ─── Pagination ──────────────────────────────────────────────────────────────

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchRequests();
}

// ─── Filter events ───────────────────────────────────────────────────────────

function handleFilterUpdate({ key, value }: { key: string; value: string }) {
  if (key === "status") statusFilter.value = value;
  currentPage.value = 1;
  fetchRequests();
}

function handleClearFilters() {
  search.value = "";
  statusFilter.value = "";
  currentPage.value = 1;
  fetchRequests();
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function viewDetail(request: CreditRequest) {
  selectedRequest.value = request;
  showDetailModal.value = true;
}

function openApproveModal(request: CreditRequest) {
  approveTarget.value = request;
  showApproveModal.value = true;
}

async function confirmApprove() {
  if (!approveTarget.value) return;
  actionLoading.value = `approve-${approveTarget.value.id}`;
  try {
    const result = await creditsApi.adminApproveCreditRequest(approveTarget.value.id);
    showToast(result.message || "Credit request approved successfully", "success");
    showApproveModal.value = false;
    approveTarget.value = null;
    await fetchRequests();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

function openRejectModal(request: CreditRequest) {
  rejectTarget.value = request;
  rejectReason.value = "";
  showRejectModal.value = true;
}

async function confirmReject() {
  if (!rejectTarget.value) return;
  if (!rejectReason.value.trim()) {
    showToast("Please provide a reason for rejection", "error");
    return;
  }
  actionLoading.value = `reject-${rejectTarget.value.id}`;
  try {
    const result = await creditsApi.adminRejectCreditRequest(
      rejectTarget.value.id,
      rejectReason.value
    );
    showToast(result.message || "Credit request rejected", "success");
    showRejectModal.value = false;
    rejectTarget.value = null;
    await fetchRequests();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
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

function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat(navigator.language, {
    style: "currency",
    currency: currency,
  }).format(cents / 100);
}

function getStatusColor(status: string): string {
  switch (status) {
    case "pending": return "amber";
    case "approved": return "green";
    case "rejected": return "red";
    default: return "gray";
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Page Header -->
    <AdminPageHeader
      title="Credit Requests"
      description="Review and manage bank transfer credit purchase requests."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Credit Requests' }]"
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
        <p class="font-medium text-foreground">Failed to load credit requests</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchRequests">Try again</button>
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
        @search="fetchRequests"
      />

      <!-- Data Table -->
      <AdminDataTable
        :columns="columns"
        :rows="requests"
        :meta="meta"
        :loading="loading"
        :clickable="false"
        row-key="id"
        empty-message="No credit requests found"
        empty-description="No credit requests match the current filters."
        @page-change="handlePageChange"
      >
        <!-- ID cell -->
        <template #cell-id="{ row }">
          <span class="font-mono text-sm">{{ row.id }}</span>
        </template>

        <!-- User email cell -->
        <template #cell-user_email="{ row }">
          <div class="min-w-0">
            <p class="truncate font-medium text-foreground">{{ row.user_email }}</p>
          </div>
        </template>

        <!-- Product cell -->
        <template #cell-product_name="{ row }">
          <p class="truncate">{{ row.product_name }}</p>
        </template>

        <!-- Plan cell -->
        <template #cell-plan_name="{ row }">
          <span class="text-sm">{{ row.plan_name }}</span>
        </template>

        <!-- Amount cell -->
        <template #cell-amount="{ row }">
          <p class="font-medium">{{ formatPrice(row.amount_cents, row.currency) }}</p>
        </template>

        <!-- Status cell -->
        <template #cell-status="{ row }">
          <AdminStatusBadge
            :status="row.status"
            type="custom"
            :custom-color="getStatusColor(row.status)"
          />
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
              @click="viewDetail(row)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </button>

            <!-- Approve -->
            <button
              v-if="row.status === 'pending'"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-green-50 hover:text-green-600 dark:hover:bg-green-950 dark:hover:text-green-400"
              title="Approve"
              :disabled="actionLoading === `approve-${row.id}`"
              @click="openApproveModal(row)"
            >
              <svg v-if="actionLoading === `approve-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            </button>

            <!-- Reject -->
            <button
              v-if="row.status === 'pending'"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
              title="Reject"
              :disabled="actionLoading === `reject-${row.id}`"
              @click="openRejectModal(row)"
            >
              <svg v-if="actionLoading === `reject-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <!-- View created pool -->
            <a
              v-if="row.status === 'approved' && row.created_credit_pool_id"
              :href="`/admin/credits`"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-brand-50 hover:text-brand-600 dark:hover:bg-brand-950 dark:hover:text-brand-400"
              title="View Credit Pool"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Detail Modal                                                            -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <div v-if="showDetailModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" @click.self="showDetailModal = false">
      <div class="bg-background rounded-lg shadow-xl max-w-xl w-full">
        <div class="p-6 border-b border-border">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">Request Details</h2>
            <button type="button" class="text-muted-foreground hover:text-foreground" @click="showDetailModal = false">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div v-if="selectedRequest" class="p-6 space-y-4">
          <!-- Status Banner -->
          <div
            :class="{
              'bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800': selectedRequest.status === 'pending',
              'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800': selectedRequest.status === 'approved',
              'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800': selectedRequest.status === 'rejected',
            }"
            class="rounded-lg border p-4"
          >
            <div class="flex items-center gap-2">
              <svg
                v-if="selectedRequest.status === 'pending'"
                class="h-5 w-5 text-amber-600 dark:text-amber-400"
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <svg
                v-else-if="selectedRequest.status === 'approved'"
                class="h-5 w-5 text-green-600 dark:text-green-400"
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
              <svg
                v-else
                class="h-5 w-5 text-red-600 dark:text-red-400"
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
              <span
                :class="{
                  'text-amber-800 dark:text-amber-300': selectedRequest.status === 'pending',
                  'text-green-800 dark:text-green-300': selectedRequest.status === 'approved',
                  'text-red-800 dark:text-red-300': selectedRequest.status === 'rejected',
                }"
                class="font-medium capitalize"
              >
                {{ selectedRequest.status }}
              </span>
            </div>
            <p
              v-if="selectedRequest.review_note"
              :class="{
                'text-amber-700 dark:text-amber-400': selectedRequest.status === 'pending',
                'text-green-700 dark:text-green-400': selectedRequest.status === 'approved',
                'text-red-700 dark:text-red-400': selectedRequest.status === 'rejected',
              }"
              class="mt-2 text-sm"
            >
              {{ selectedRequest.review_note }}
            </p>
          </div>

          <!-- Info Grid -->
          <div class="grid grid-cols-2 gap-4">
            <div>
              <p class="text-xs text-muted-foreground">Request ID</p>
              <p class="font-mono text-sm">#{{ selectedRequest.id }}</p>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">User</p>
              <p class="text-sm font-medium">{{ selectedRequest.user_email }}</p>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">Product</p>
              <p class="text-sm">{{ selectedRequest.product_name }}</p>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">Plan</p>
              <p class="text-sm">{{ selectedRequest.plan_name }}</p>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">Amount</p>
              <p class="text-sm font-semibold">{{ formatPrice(selectedRequest.amount_cents, selectedRequest.currency) }}</p>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">Submitted</p>
              <p class="text-sm">{{ formatDate(selectedRequest.created_at) }}</p>
            </div>
          </div>

          <!-- Bank Details -->
          <div class="border-t border-border pt-4">
            <h3 class="text-sm font-semibold mb-3">Bank Transfer Details</h3>
            <div class="rounded-lg bg-muted p-4 space-y-2 font-mono text-sm">
              <div class="flex justify-between">
                <span class="text-muted-foreground">Bank:</span>
                <span>{{ selectedRequest.bank_name }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-muted-foreground">Account Holder:</span>
                <span>{{ selectedRequest.account_holder_name }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-muted-foreground">Account Number:</span>
                <span>{{ selectedRequest.account_number }}</span>
              </div>
              <div v-if="selectedRequest.routing_number" class="flex justify-between">
                <span class="text-muted-foreground">Routing:</span>
                <span>{{ selectedRequest.routing_number }}</span>
              </div>
              <div class="flex justify-between border-t border-border pt-2 mt-2">
                <span class="text-muted-foreground">Transaction Ref:</span>
                <span class="font-semibold">{{ selectedRequest.transaction_reference }}</span>
              </div>
            </div>
            <p v-if="selectedRequest.payment_proof_note" class="mt-2 text-sm text-muted-foreground">
              <span class="font-medium">Note:</span> {{ selectedRequest.payment_proof_note }}
            </p>
          </div>

          <!-- Actions -->
          <div v-if="selectedRequest.status === 'pending'" class="flex justify-end gap-3 pt-2">
            <button
              type="button"
              class="btn-secondary text-sm"
              @click="showDetailModal = false"
            >
              Close
            </button>
            <button
              type="button"
              class="btn-secondary text-sm !text-red-600 hover:!bg-red-50 dark:hover:!bg-red-950"
              @click="showDetailModal = false; openRejectModal(selectedRequest)"
            >
              Reject
            </button>
            <button
              type="button"
              class="btn-primary text-sm"
              @click="showDetailModal = false; openApproveModal(selectedRequest)"
            >
              Approve
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Approve Confirmation Dialog                                             -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showApproveModal"
      title="Approve Credit Request"
      :message="'Approve credit request #' + (approveTarget?.id || '') + '?'"
      :detail="'This will create a credit pool for ' + (approveTarget?.user_email || '') + ' worth ' + (approveTarget ? formatPrice(approveTarget.amount_cents, approveTarget.currency) : '') + '.'"
      confirm-label="Approve"
      :loading="actionLoading?.startsWith('approve-')"
      @confirm="confirmApprove"
    />

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Reject Confirmation Dialog                                              -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showRejectModal"
      title="Reject Credit Request"
      :message="'Reject credit request #' + (rejectTarget?.id || '') + '?'"
      detail="The user will be notified via email. Please provide a reason."
      confirm-label="Reject"
      :destructive="true"
      :loading="actionLoading?.startsWith('reject-')"
      @confirm="confirmReject"
    >
      <div class="mt-3">
        <label class="block text-xs font-medium text-muted-foreground mb-1">Rejection Reason *</label>
        <textarea
          v-model="rejectReason"
          rows="3"
          class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm resize-none"
          placeholder="Reason for rejecting this request..."
        />
      </div>
    </AdminConfirmDialog>
  </div>
</template>
