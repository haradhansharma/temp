<script setup lang="ts">
/**
 * SubscriptionsAdmin — Subscription list management page for /admin/subscriptions.
 *
 * Features:
 *   - Searchable, filterable data table with subscriptions
 *   - Filters: product dropdown, plan dropdown, status dropdown, search by email
 *   - Row click navigates to subscription detail
 *   - Actions: view (navigate), cancel, expire (with confirmation dialogs)
 *   - Server-side pagination and filtering
 *   - Plan filter refreshes when product filter changes
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable, AdminFilterBar,
 * AdminConfirmDialog, AdminStatusBadge.
 */

import { ref, computed, onMounted, watch } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { adminApi, formatDateTime } from "@/lib/admin";
import type {
  SubscriptionItem,
  PaginationMeta,
  ProductItem,
  PlanItem,
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

const subscriptions = ref<SubscriptionItem[]>([]);
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
const productFilter = ref("");
const planFilter = ref("");
const currentPage = ref(1);

// Filter dropdown options (populated from API)
const productOptions = ref<ProductItem[]>([]);
const planOptions = ref<PlanItem[]>([]);

// Cancel dialog
const showCancelDialog = ref(false);
const cancelingSubscription = ref<SubscriptionItem | null>(null);

// Expire dialog
const showExpireDialog = ref(false);
const expiringSubscription = ref<SubscriptionItem | null>(null);

// ─── Column definitions ──────────────────────────────────────────────────────

const columns = computed<ColumnDef[]>(() => [
  { key: "user_email", label: "User", sortable: true, defaultSort: "asc" },
  { key: "product_name", label: "Product", sortable: true, hideOnMobile: true },
  { key: "plan_name", label: "Plan", sortable: true, hideOnMobile: true },
  { key: "status", label: "Status", align: "center", width: "120px" },
  { key: "current_period_end", label: "Period End", sortable: true, width: "140px", hideOnMobile: true },
  { key: "actions", label: "", align: "right", width: "120px" },
]);

// ─── Filter definitions ──────────────────────────────────────────────────────

const filters = computed<FilterDef[]>(() => [
  {
    key: "product",
    label: "Product",
    options: productOptions.value.map((p) => ({
      value: String(p.id),
      label: p.name,
    })),
    value: productFilter.value,
    placeholder: "All Products",
  },
  {
    key: "plan",
    label: "Plan",
    options: planOptions.value.map((p) => ({
      value: String(p.id),
      label: p.name,
    })),
    value: planFilter.value,
    placeholder: "All Plans",
  },
  {
    key: "status",
    label: "Status",
    options: [
      { value: "active", label: "Active" },
      { value: "trialing", label: "Trialing" },
      { value: "past_due", label: "Past Due" },
      { value: "canceled", label: "Canceled" },
      { value: "expired", label: "Expired" },
      { value: "paused", label: "Paused" },
    ],
    value: statusFilter.value,
    placeholder: "All Statuses",
  },
]);

const activeFilterCount = computed(() => {
  let count = 0;
  if (productFilter.value) count++;
  if (planFilter.value) count++;
  if (statusFilter.value) count++;
  return count;
});

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchSubscriptions() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Record<string, unknown> = {
      page: currentPage.value,
      page_size: 20,
    };
    if (search.value.trim()) params.search = search.value.trim();
    if (statusFilter.value) params.status = statusFilter.value;
    if (productFilter.value) params.product_id = Number(productFilter.value);
    if (planFilter.value) params.plan_id = Number(planFilter.value);

    const data = await adminApi.listSubscriptions(params);
    subscriptions.value = data.results;
    meta.value = data.meta;
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

async function fetchProducts() {
  try {
    const data = await adminApi.listProducts({ page: 1, page_size: 100 });
    productOptions.value = data.results;
  } catch {
    // Silently fail — filter dropdown will just be empty
  }
}

async function fetchPlans(productId: number) {
  try {
    const data = await adminApi.listPlans(productId, {
      page: 1,
      page_size: 100,
    });
    planOptions.value = data.results;
  } catch {
    planOptions.value = [];
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await Promise.all([fetchSubscriptions(), fetchProducts()]);
});

// ─── Watch product filter to refresh plans ────────────────────────────────────

watch(productFilter, async (newProductId) => {
  if (newProductId) {
    await fetchPlans(Number(newProductId));
  } else {
    planOptions.value = [];
  }
  // Reset plan filter when product changes
  if (planFilter.value) {
    planFilter.value = "";
    // Re-fetch subscriptions with cleared plan filter
    await fetchSubscriptions();
  }
});

// ─── Navigation ──────────────────────────────────────────────────────────────

function handleRowClick(row: Record<string, unknown>) {
  const subscription = row as SubscriptionItem;
  window.location.href = `/admin/subscriptions/${subscription.id}`;
}

function viewSubscription(id: number) {
  window.location.href = `/admin/subscriptions/${id}`;
}

// ─── Pagination ──────────────────────────────────────────────────────────────

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchSubscriptions();
}

// ─── Filter events ───────────────────────────────────────────────────────────

function handleFilterUpdate({ key, value }: { key: string; value: string }) {
  if (key === "status") statusFilter.value = value;
  if (key === "product") productFilter.value = value;
  if (key === "plan") planFilter.value = value;
  currentPage.value = 1;
  fetchSubscriptions();
}

function handleClearFilters() {
  search.value = "";
  statusFilter.value = "";
  productFilter.value = "";
  planFilter.value = "";
  planOptions.value = [];
  currentPage.value = 1;
  fetchSubscriptions();
}

// ─── Sort ────────────────────────────────────────────────────────────────────

function handleSort({ key, direction }: { key: string; direction: "asc" | "desc" }) {
  // Client-side sort for current page
  subscriptions.value.sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[key];
    const bVal = (b as Record<string, unknown>)[key];
    if (aVal == null || bVal == null) return 0;
    const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
    return direction === "asc" ? cmp : -cmp;
  });
}

// ─── Period end helper ───────────────────────────────────────────────────────

function formatPeriodEnd(subscription: SubscriptionItem): string {
  if (subscription.status === "canceled") return "Canceled";
  if (subscription.status === "expired") return "Expired";
  return formatDateTime(subscription.current_period_end);
}

// ─── Action visibility helpers ────────────────────────────────────────────────

const cancellableStatuses = new Set(["active", "trialing", "past_due"]);
const expirableStatuses = new Set(["active", "trialing", "past_due", "paused"]);

function canCancel(status: string): boolean {
  return cancellableStatuses.has(status);
}

function canExpire(status: string): boolean {
  return expirableStatuses.has(status);
}

// ─── Cancel Subscription ─────────────────────────────────────────────────────

function openCancelDialog(subscription: SubscriptionItem) {
  cancelingSubscription.value = subscription;
  showCancelDialog.value = true;
}

async function confirmCancel() {
  if (!cancelingSubscription.value) return;
  actionLoading.value = `cancel-${cancelingSubscription.value.id}`;
  try {
    await adminApi.cancelSubscription(cancelingSubscription.value.id);
    showToast("Subscription canceled.", "success");
    showCancelDialog.value = false;
    cancelingSubscription.value = null;
    await fetchSubscriptions();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Expire Subscription ─────────────────────────────────────────────────────

function openExpireDialog(subscription: SubscriptionItem) {
  expiringSubscription.value = subscription;
  showExpireDialog.value = true;
}

async function confirmExpire() {
  if (!expiringSubscription.value) return;
  actionLoading.value = `expire-${expiringSubscription.value.id}`;
  try {
    await adminApi.expireSubscription(expiringSubscription.value.id);
    showToast("Subscription expired.", "success");
    showExpireDialog.value = false;
    expiringSubscription.value = null;
    await fetchSubscriptions();
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
      title="Subscriptions"
      description="View and manage user subscriptions across products and plans."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Subscriptions' }]"
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
        <p class="font-medium text-foreground">Failed to load subscriptions</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchSubscriptions">Try again</button>
    </div>

    <template v-else>
      <!-- Filter Bar -->
      <AdminFilterBar
        v-model:search="search"
        :filters="filters"
        :active-count="activeFilterCount"
        search-placeholder="Search by email..."
        @update:filter="handleFilterUpdate"
        @clear="handleClearFilters"
      />

      <!-- Data Table -->
      <AdminDataTable
        :columns="columns"
        :rows="subscriptions"
        :meta="meta"
        :loading="loading"
        :clickable="true"
        row-key="id"
        empty-message="No subscriptions found"
        empty-description="No subscriptions match the current filters."
        @row-click="handleRowClick"
        @page-change="handlePageChange"
        @sort="handleSort"
      >
        <!-- User email cell -->
        <template #cell-user_email="{ row }">
          <div class="min-w-0">
            <p class="truncate font-medium text-foreground">{{ row.user_email }}</p>
            <p v-if="row.user_name" class="truncate text-xs text-muted-foreground">{{ row.user_name }}</p>
          </div>
        </template>

        <!-- Status cell -->
        <template #cell-status="{ row }">
          <AdminStatusBadge :status="row.status" type="subscription" />
        </template>

        <!-- Period end cell -->
        <template #cell-current_period_end="{ row }">
          <span
            :class="{
              'text-muted-foreground': row.status === 'canceled' || row.status === 'expired',
            }"
          >
            {{ formatPeriodEnd(row) }}
          </span>
        </template>

        <!-- Actions cell -->
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end gap-1" @click.stop>
            <!-- View -->
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="View"
              @click="viewSubscription(row.id)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </button>

            <!-- Cancel (only for active/trialing/past_due) -->
            <button
              v-if="canCancel(row.status)"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-amber-50 hover:text-amber-600 dark:hover:bg-amber-950 dark:hover:text-amber-400"
              title="Cancel"
              :disabled="actionLoading === `cancel-${row.id}`"
              @click="openCancelDialog(row)"
            >
              <svg v-if="actionLoading === `cancel-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
            </button>

            <!-- Expire (only for active/trialing/past_due/paused) -->
            <button
              v-if="canExpire(row.status)"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
              title="Expire"
              :disabled="actionLoading === `expire-${row.id}`"
              @click="openExpireDialog(row)"
            >
              <svg v-if="actionLoading === `expire-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </button>
          </div>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Cancel Subscription Confirmation Dialog                                -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showCancelDialog"
      title="Cancel Subscription"
      :message="'Cancel subscription for \'' + (cancelingSubscription?.user_email ?? '') + '\'?'"
      detail="The subscription will be canceled at the end of the current billing period. The user will retain access until then."
      confirm-label="Cancel Subscription"
      :destructive="true"
      :loading="actionLoading?.startsWith('cancel-')"
      @confirm="confirmCancel"
    />

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Expire Subscription Confirmation Dialog                                -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showExpireDialog"
      title="Expire Subscription"
      :message="'Expire subscription for \'' + (expiringSubscription?.user_email ?? '') + '\'?'"
      detail="The subscription will be expired immediately. The user will lose access right away."
      confirm-label="Expire Subscription"
      :destructive="true"
      :loading="actionLoading?.startsWith('expire-')"
      @confirm="confirmExpire"
    />
  </div>
</template>
