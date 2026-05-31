<script setup lang="ts">
/**
 * WebhooksAdmin — Webhook event monitoring page for /admin/webhooks.
 *
 * Features:
 *   - Data table with webhook events: event ID, event type, status badge, date, error
 *   - Filters: event type dropdown, status dropdown (processed/failed), date range
 *   - Retry action for failed webhooks with confirmation dialog
 *   - Detail modal showing full event info including payload
 *   - Server-side pagination and filtering
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable, AdminFilterBar,
 * AdminConfirmDialog, AdminStatusBadge.
 */

import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import {
  adminApi,
  formatDateTime,
  formatRelativeTime,
  getWebhookStatusColor,
} from "@/lib/admin";
import type {
  WebhookEvent,
  PaginationMeta,
} from "@/lib/admin";

import AdminPageHeader from "@/components/admin/AdminPageHeader.vue";
import AdminFilterBar from "@/components/admin/AdminFilterBar.vue";
import AdminDataTable from "@/components/admin/AdminDataTable.vue";
import type { ColumnDef } from "@/components/admin/AdminDataTable.vue";
import type { FilterDef } from "@/components/admin/AdminFilterBar.vue";
import AdminConfirmDialog from "@/components/admin/AdminConfirmDialog.vue";
import AdminStatusBadge from "@/components/admin/AdminStatusBadge.vue";

// ─── Stripe event types (from backend HANDLED_EVENTS) ────────────────────────

const EVENT_TYPES = [
  { value: "checkout.session.completed", label: "Checkout Completed" },
  { value: "customer.subscription.created", label: "Subscription Created" },
  { value: "customer.subscription.updated", label: "Subscription Updated" },
  { value: "customer.subscription.deleted", label: "Subscription Deleted" },
  { value: "invoice.payment_succeeded", label: "Payment Succeeded" },
  { value: "invoice.payment_failed", label: "Payment Failed" },
  { value: "customer.subscription.trial_will_end", label: "Trial Ending" },
  { value: "charge.refunded", label: "Charge Refunded" },
  { value: "customer.updated", label: "Customer Updated" },
  { value: "invoice.created", label: "Invoice Created" },
];

const STATUS_OPTIONS = [
  { value: "processed", label: "Processed" },
  { value: "failed", label: "Failed" },
];

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const loadError = ref<string | null>(null);
const actionLoading = ref<string | null>(null);

const webhooks = ref<WebhookEvent[]>([]);
const totalItems = ref(0);
const failedCount = ref(0);
const currentPage = ref(1);
const pageSize = 20;

// Convert to PaginationMeta for AdminDataTable
const meta = computed<PaginationMeta>(() => ({
  total_items: totalItems.value,
  total_pages: Math.max(1, Math.ceil(totalItems.value / pageSize)),
  current_page: currentPage.value,
  page_size: pageSize,
  has_next: currentPage.value * pageSize < totalItems.value,
  has_previous: currentPage.value > 1,
}));

// Filters
const search = ref("");
const eventTypeFilter = ref("");
const statusFilter = ref("");
const dateFrom = ref("");
const dateTo = ref("");

// Retry dialog
const showRetryDialog = ref(false);
const retryTarget = ref<WebhookEvent | null>(null);

// Detail modal
const showDetailModal = ref(false);
const detailEvent = ref<WebhookEvent | null>(null);

// ─── Column definitions ──────────────────────────────────────────────────────

const columns = computed<ColumnDef[]>(() => [
  { key: "event_id", label: "Event ID", width: "180px" },
  { key: "event_type", label: "Event Type", width: "220px" },
  { key: "status", label: "Status", align: "center", width: "110px" },
  { key: "created_at", label: "Received", sortable: true, width: "160px", hideOnMobile: true },
  { key: "error_message", label: "Error", hideOnMobile: true },
  { key: "actions", label: "", align: "right", width: "80px" },
]);

// ─── Filter definitions ──────────────────────────────────────────────────────

const filters = computed<FilterDef[]>(() => [
  {
    key: "event_type",
    label: "Event Type",
    options: EVENT_TYPES,
    value: eventTypeFilter.value,
    placeholder: "All Event Types",
  },
  {
    key: "status",
    label: "Status",
    options: STATUS_OPTIONS,
    value: statusFilter.value,
    placeholder: "All Statuses",
  },
]);

const activeFilterCount = computed(() => {
  let count = 0;
  if (eventTypeFilter.value) count++;
  if (statusFilter.value) count++;
  if (dateFrom.value) count++;
  if (dateTo.value) count++;
  return count;
});

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchWebhooks() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Record<string, unknown> = {
      page: currentPage.value,
      page_size: pageSize,
    };
    if (eventTypeFilter.value) params.event_type = eventTypeFilter.value;
    // Backend uses "processed" boolean, not "status" string
    if (statusFilter.value === "processed") params.processed = true;
    else if (statusFilter.value === "failed") params.processed = false;

    const data = await adminApi.listWebhooks(params);
    webhooks.value = data.items;
    totalItems.value = data.total;
    failedCount.value = data.failed_count;
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchWebhooks();
});

// ─── Pagination ──────────────────────────────────────────────────────────────

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchWebhooks();
}

// ─── Filter events ───────────────────────────────────────────────────────────

function handleFilterUpdate({ key, value }: { key: string; value: string }) {
  if (key === "event_type") eventTypeFilter.value = value;
  if (key === "status") statusFilter.value = value;
  currentPage.value = 1;
  fetchWebhooks();
}

function handleDateFromUpdate(value: string) {
  dateFrom.value = value;
  currentPage.value = 1;
  fetchWebhooks();
}

function handleDateToUpdate(value: string) {
  dateTo.value = value;
  currentPage.value = 1;
  fetchWebhooks();
}

function handleClearFilters() {
  search.value = "";
  eventTypeFilter.value = "";
  statusFilter.value = "";
  dateFrom.value = "";
  dateTo.value = "";
  currentPage.value = 1;
  fetchWebhooks();
}

// ─── Sort ────────────────────────────────────────────────────────────────────

function handleSort({ key, direction }: { key: string; direction: "asc" | "desc" }) {
  webhooks.value.sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[key];
    const bVal = (b as Record<string, unknown>)[key];
    if (aVal == null || bVal == null) return 0;
    const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
    return direction === "asc" ? cmp : -cmp;
  });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Derive a display-friendly status from the processed boolean.
 * processed=true → "processed", processed=false with error → "failed",
 * processed=false without error → "pending"
 */
function getWebhookStatus(event: WebhookEvent): string {
  if (event.processed) return "processed";
  if (event.error_message) return "failed";
  return "pending";
}

/**
 * Format event type for display (replace dots with arrows).
 */
function formatEventType(eventType: string): string {
  return eventType
    .split(".")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" → ");
}

/**
 * Truncate event ID for display.
 */
function truncateEventId(eventId: string): string {
  if (eventId.length <= 20) return eventId;
  return eventId.slice(0, 8) + "..." + eventId.slice(-8);
}

/**
 * Check if a webhook can be retried (not processed).
 */
function canRetry(event: WebhookEvent): boolean {
  return !event.processed;
}

// ─── Detail modal ────────────────────────────────────────────────────────────

function openDetailModal(event: WebhookEvent) {
  detailEvent.value = event;
  showDetailModal.value = true;
}

function closeDetailModal() {
  showDetailModal.value = false;
  detailEvent.value = null;
}

// ─── Retry webhook ───────────────────────────────────────────────────────────

function openRetryDialog(event: WebhookEvent) {
  retryTarget.value = event;
  showRetryDialog.value = true;
}

async function confirmRetry() {
  if (!retryTarget.value) return;
  const eventId = retryTarget.value.id;
  actionLoading.value = `retry-${eventId}`;
  try {
    const result = await adminApi.retryWebhook(eventId);
    showToast(result.message || "Webhook retried successfully.", "success");
    showRetryDialog.value = false;
    retryTarget.value = null;
    await fetchWebhooks();
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
      title="Webhooks"
      description="Monitor Stripe webhook delivery events and retry failed processing."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Webhooks' }]"
    >
      <template #primary-action>
        <div v-if="failedCount > 0" class="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 dark:border-red-800 dark:bg-red-950/50">
          <svg class="h-4 w-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span class="text-sm font-medium text-red-700 dark:text-red-400">
            {{ failedCount }} failed event{{ failedCount !== 1 ? 's' : '' }}
          </span>
        </div>
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
        <p class="font-medium text-foreground">Failed to load webhooks</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchWebhooks">Try again</button>
    </div>

    <template v-else>
      <!-- Filter Bar -->
      <AdminFilterBar
        v-model:search="search"
        :filters="filters"
        :active-count="activeFilterCount"
        search-placeholder="Filter webhooks..."
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
        :rows="webhooks"
        :meta="meta"
        :loading="loading"
        row-key="id"
        empty-message="No webhook events found"
        empty-description="No webhook events match the current filters."
        @page-change="handlePageChange"
        @sort="handleSort"
      >
        <!-- Event ID cell -->
        <template #cell-event_id="{ row }">
          <div class="min-w-0">
            <p class="truncate font-mono text-xs text-foreground" :title="row.event_id">
              {{ truncateEventId(row.event_id) }}
            </p>
          </div>
        </template>

        <!-- Event type cell -->
        <template #cell-event_type="{ row }">
          <span class="text-sm text-foreground">
            {{ formatEventType(row.event_type) }}
          </span>
        </template>

        <!-- Status cell -->
        <template #cell-status="{ row }">
          <AdminStatusBadge
            :status="getWebhookStatus(row)"
            type="webhook"
          />
        </template>

        <!-- Received date cell -->
        <template #cell-created_at="{ row }">
          <div class="min-w-0">
            <p class="text-sm text-foreground">{{ formatRelativeTime(row.created_at) }}</p>
            <p class="text-xs text-muted-foreground">{{ formatDateTime(row.created_at) }}</p>
          </div>
        </template>

        <!-- Error message cell -->
        <template #cell-error_message="{ row }">
          <p v-if="row.error_message" class="truncate text-xs text-red-600 dark:text-red-400" :title="row.error_message">
            {{ row.error_message }}
          </p>
          <span v-else class="text-xs text-muted-foreground">—</span>
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

            <!-- Retry button (only for failed/pending) -->
            <button
              v-if="canRetry(row)"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-amber-50 hover:text-amber-600 dark:hover:bg-amber-950 dark:hover:text-amber-400"
              title="Retry Webhook"
              :disabled="actionLoading === `retry-${row.id}`"
              @click="openRetryDialog(row)"
            >
              <svg v-if="actionLoading === `retry-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Webhook Detail Modal                                                    -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <Teleport to="body">
      <div
        v-if="showDetailModal && detailEvent"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Webhook Event Details"
      >
        <!-- Backdrop -->
        <div
          class="fixed inset-0 bg-black/60 backdrop-blur-sm"
          @click="closeDetailModal"
        />

        <!-- Panel -->
        <div class="relative z-10 w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl animate-scale-in">
          <div class="flex items-start justify-between mb-4">
            <h3 class="text-lg font-semibold text-foreground">Webhook Event Details</h3>
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
            <!-- Status + event type row -->
            <div class="flex items-center justify-between">
              <AdminStatusBadge
                :status="getWebhookStatus(detailEvent)"
                type="webhook"
              />
              <span class="text-sm font-medium text-foreground">
                {{ formatEventType(detailEvent.event_type) }}
              </span>
            </div>

            <!-- Detail grid -->
            <div class="grid grid-cols-2 gap-3 text-sm">
              <div class="col-span-2">
                <p class="text-xs font-medium text-muted-foreground">Stripe Event ID</p>
                <p class="font-mono text-xs text-foreground break-all">{{ detailEvent.event_id }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Event Type</p>
                <p class="font-mono text-xs text-foreground">{{ detailEvent.event_type }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Processed</p>
                <p class="text-foreground">{{ detailEvent.processed ? 'Yes' : 'No' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Received</p>
                <p class="text-foreground">{{ formatDateTime(detailEvent.created_at) }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Relative</p>
                <p class="text-foreground">{{ formatRelativeTime(detailEvent.created_at) }}</p>
              </div>
              <div v-if="detailEvent.error_message" class="col-span-2">
                <p class="text-xs font-medium text-muted-foreground">Error Message</p>
                <div class="mt-1 rounded-lg bg-red-50 p-3 text-xs text-red-700 border border-red-200 dark:bg-red-950/50 dark:text-red-400 dark:border-red-800 whitespace-pre-wrap">
                  {{ detailEvent.error_message }}
                </div>
              </div>
            </div>

            <!-- Action buttons -->
            <div class="flex items-center justify-end gap-2 border-t border-border pt-4">
              <button
                type="button"
                class="btn-ghost px-4 py-2 text-sm"
                @click="closeDetailModal"
              >
                Close
              </button>
              <button
                v-if="canRetry(detailEvent)"
                type="button"
                class="btn-primary px-4 py-2 text-sm"
                :disabled="actionLoading === `retry-${detailEvent.id}`"
                @click="closeDetailModal(); openRetryDialog(detailEvent)"
              >
                <svg v-if="actionLoading === `retry-${detailEvent.id}`" class="mr-1.5 h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Retry Event
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Retry Webhook Confirmation Dialog                                       -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showRetryDialog"
      title="Retry Failed Webhook"
      :message="retryTarget ? `Retry processing webhook event ${truncateEventId(retryTarget.event_id)}?` : 'Retry webhook?'"
      detail="This will re-process the Stripe event. If the underlying issue is resolved, the event should process successfully. If the issue persists, the event will remain in a failed state."
      confirm-label="Retry Event"
      :destructive="false"
      :loading="actionLoading?.startsWith('retry-')"
      @confirm="confirmRetry"
    >
      <!-- Event summary in dialog -->
      <div v-if="retryTarget" class="mt-3 space-y-2 rounded-lg bg-muted/50 p-3 border border-border">
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Event Type</span>
          <span class="text-foreground">{{ formatEventType(retryTarget.event_type) }}</span>
        </div>
        <div v-if="retryTarget.error_message" class="flex justify-between text-xs gap-4">
          <span class="text-muted-foreground shrink-0">Last Error</span>
          <span class="text-red-600 dark:text-red-400 text-right truncate max-w-[250px]" :title="retryTarget.error_message">{{ retryTarget.error_message }}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-muted-foreground">Received</span>
          <span class="text-foreground">{{ formatRelativeTime(retryTarget.created_at) }}</span>
        </div>
      </div>
    </AdminConfirmDialog>
  </div>
</template>
