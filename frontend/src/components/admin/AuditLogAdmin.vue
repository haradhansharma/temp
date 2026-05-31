<script setup lang="ts">
/**
 * AuditLogAdmin — Admin audit log page for /admin/audit-log.
 *
 * Features:
 *   - Data table with admin actions: admin user, action, method, path, IP, timestamp
 *   - Expandable rows showing request details (JSON)
 *   - Filters: action type dropdown, admin user (text), date range
 *   - Server-side pagination and filtering
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable, AdminFilterBar,
 * AdminStatusBadge.
 */

import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import {
  adminApi,
  formatDateTime,
  formatRelativeTime,
} from "@/lib/admin";
import type {
  AuditLogEntry,
  PaginationMeta,
} from "@/lib/admin";

import AdminPageHeader from "@/components/admin/AdminPageHeader.vue";
import AdminFilterBar from "@/components/admin/AdminFilterBar.vue";
import AdminDataTable from "@/components/admin/AdminDataTable.vue";
import type { ColumnDef } from "@/components/admin/AdminDataTable.vue";
import type { FilterDef } from "@/components/admin/AdminFilterBar.vue";

// ─── Action type groups (for dropdown filter) ────────────────────────────────

const ACTION_TYPES = [
  { value: "product", label: "Product Actions" },
  { value: "plan", label: "Plan Actions" },
  { value: "subscription", label: "Subscription Actions" },
  { value: "refund", label: "Refund Actions" },
  { value: "api_key", label: "API Key Actions" },
  { value: "user", label: "User Actions" },
  { value: "domain", label: "Domain Actions" },
  { value: "access", label: "Access Entry Actions" },
];

const METHOD_COLORS: Record<string, { bg: string; text: string }> = {
  GET: { bg: "bg-blue-100 dark:bg-blue-950", text: "text-blue-700 dark:text-blue-400" },
  POST: { bg: "bg-green-100 dark:bg-green-950", text: "text-green-700 dark:text-green-400" },
  PUT: { bg: "bg-amber-100 dark:bg-amber-950", text: "text-amber-700 dark:text-amber-400" },
  PATCH: { bg: "bg-amber-100 dark:bg-amber-950", text: "text-amber-700 dark:text-amber-400" },
  DELETE: { bg: "bg-red-100 dark:bg-red-950", text: "text-red-700 dark:text-red-400" },
};

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const loadError = ref<string | null>(null);

const entries = ref<AuditLogEntry[]>([]);
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
const actionFilter = ref("");
const dateFrom = ref("");
const dateTo = ref("");
const currentPage = ref(1);

// Detail modal
const showDetailModal = ref(false);
const detailEntry = ref<AuditLogEntry | null>(null);

// ─── Column definitions ──────────────────────────────────────────────────────

const columns = computed<ColumnDef[]>(() => [
  { key: "admin_email", label: "Admin User", width: "180px" },
  { key: "action", label: "Action", width: "180px" },
  { key: "method", label: "Method", align: "center", width: "80px" },
  { key: "path", label: "Path", hideOnMobile: true },
  { key: "ip_address", label: "IP", width: "120px", hideOnMobile: true },
  { key: "status_code", label: "Status", align: "center", width: "70px", hideOnMobile: true },
  { key: "timestamp", label: "Time", sortable: true, width: "160px" },
  { key: "actions", label: "", align: "right", width: "80px" },
]);

// ─── Filter definitions ──────────────────────────────────────────────────────

const filters = computed<FilterDef[]>(() => [
  {
    key: "action",
    label: "Action Type",
    options: ACTION_TYPES,
    value: actionFilter.value,
    placeholder: "All Actions",
  },
]);

const activeFilterCount = computed(() => {
  let count = 0;
  if (actionFilter.value) count++;
  if (dateFrom.value) count++;
  if (dateTo.value) count++;
  return count;
});

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchAuditLog() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Record<string, unknown> = {
      page: currentPage.value,
      page_size: 20,
    };
    if (actionFilter.value) params.action = actionFilter.value;
    if (dateFrom.value) params.date_from = dateFrom.value;
    if (dateTo.value) params.date_to = dateTo.value;

    const data = await adminApi.listAuditLog(params);
    entries.value = data.results;
    meta.value = data.meta;
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchAuditLog();
});

// ─── Pagination ──────────────────────────────────────────────────────────────

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchAuditLog();
}

// ─── Filter events ───────────────────────────────────────────────────────────

function handleFilterUpdate({ key, value }: { key: string; value: string }) {
  if (key === "action") actionFilter.value = value;
  currentPage.value = 1;
  fetchAuditLog();
}

function handleDateFromUpdate(value: string) {
  dateFrom.value = value;
  currentPage.value = 1;
  fetchAuditLog();
}

function handleDateToUpdate(value: string) {
  dateTo.value = value;
  currentPage.value = 1;
  fetchAuditLog();
}

function handleClearFilters() {
  search.value = "";
  actionFilter.value = "";
  dateFrom.value = "";
  dateTo.value = "";
  currentPage.value = 1;
  fetchAuditLog();
}

// ─── Sort ────────────────────────────────────────────────────────────────────

function handleSort({ key, direction }: { key: string; direction: "asc" | "desc" }) {
  entries.value.sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[key];
    const bVal = (b as Record<string, unknown>)[key];
    if (aVal == null || bVal == null) return 0;
    const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
    return direction === "asc" ? cmp : -cmp;
  });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Get the method badge color.
 */
function getMethodColor(method: string): { bg: string; text: string } {
  return METHOD_COLORS[method.toUpperCase()] || { bg: "bg-gray-100 dark:bg-gray-900", text: "text-gray-600 dark:text-gray-400" };
}

/**
 * Format action for display (e.g., "product.create" → "Product Create").
 */
function formatAction(action: string): string {
  return action
    .split(".")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" → ");
}

/**
 * Get status code color.
 */
function getStatusCodeColor(code: number | null): string {
  if (!code) return "text-muted-foreground";
  if (code >= 200 && code < 300) return "text-green-600 dark:text-green-400";
  if (code >= 400 && code < 500) return "text-amber-600 dark:text-amber-400";
  if (code >= 500) return "text-red-600 dark:text-red-400";
  return "text-foreground";
}

/**
 * Check if an entry has details to show.
 */
function hasDetails(entry: AuditLogEntry): boolean {
  return entry.details && Object.keys(entry.details).length > 0;
}

/**
 * Pretty-print JSON details.
 */
function formatDetails(details: Record<string, unknown>): string {
  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return String(details);
  }
}

// ─── Detail modal ────────────────────────────────────────────────────────────

function openDetailModal(entry: AuditLogEntry) {
  detailEntry.value = entry;
  showDetailModal.value = true;
}

function closeDetailModal() {
  showDetailModal.value = false;
  detailEntry.value = null;
}
</script>

<template>
  <div class="space-y-6">
    <!-- Page Header -->
    <AdminPageHeader
      title="Audit Log"
      description="Track admin actions and system changes across the platform."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Audit Log' }]"
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
        <p class="font-medium text-foreground">Failed to load audit log</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchAuditLog">Try again</button>
    </div>

    <template v-else>
      <!-- Filter Bar -->
      <AdminFilterBar
        v-model:search="search"
        :filters="filters"
        :active-count="activeFilterCount"
        search-placeholder="Filter audit log..."
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
        :rows="entries"
        :meta="meta"
        :loading="loading"
        row-key="id"
        empty-message="No audit log entries found"
        empty-description="No audit log entries match the current filters."
        @page-change="handlePageChange"
        @sort="handleSort"
      >
        <!-- Admin email cell -->
        <template #cell-admin_email="{ row }">
          <div class="min-w-0">
            <p class="truncate text-sm font-medium text-foreground">{{ row.admin_email }}</p>
          </div>
        </template>

        <!-- Action cell -->
        <template #cell-action="{ row }">
          <span class="text-sm text-foreground">
            {{ formatAction(row.action) }}
          </span>
        </template>

        <!-- Method cell -->
        <template #cell-method="{ row }">
          <span
            class="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase"
            :class="[getMethodColor(row.method).bg, getMethodColor(row.method).text]"
          >
            {{ row.method }}
          </span>
        </template>

        <!-- Path cell -->
        <template #cell-path="{ row }">
          <p class="truncate font-mono text-xs text-muted-foreground" :title="row.path">
            {{ row.path }}
          </p>
        </template>

        <!-- IP address cell -->
        <template #cell-ip_address="{ row }">
          <span class="font-mono text-xs text-muted-foreground">
            {{ row.ip_address || '—' }}
          </span>
        </template>

        <!-- Status code cell -->
        <template #cell-status_code="{ row }">
          <span v-if="row.status_code" class="text-sm font-mono" :class="getStatusCodeColor(row.status_code)">
            {{ row.status_code }}
          </span>
          <span v-else class="text-xs text-muted-foreground">—</span>
        </template>

        <!-- Timestamp cell -->
        <template #cell-timestamp="{ row }">
          <div class="min-w-0">
            <p class="text-sm text-foreground">{{ formatRelativeTime(row.timestamp) }}</p>
            <p class="text-xs text-muted-foreground">{{ formatDateTime(row.timestamp) }}</p>
          </div>
        </template>

        <!-- Actions cell -->
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end gap-1" @click.stop>
            <!-- View details button (with JSON details indicator) -->
            <button
              type="button"
              class="inline-flex h-7 items-center justify-center rounded-md px-2 text-xs transition-colors"
              :class="hasDetails(row)
                ? 'text-muted-foreground hover:bg-muted hover:text-foreground'
                : 'text-muted-foreground/50 cursor-default'"
              :title="hasDetails(row) ? 'View Details' : 'No Details'"
              @click="hasDetails(row) && openDetailModal(row)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              <span v-if="hasDetails(row)" class="ml-1 text-[10px] text-muted-foreground">JSON</span>
            </button>
          </div>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Audit Log Detail Modal                                                  -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <Teleport to="body">
      <div
        v-if="showDetailModal && detailEntry"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Audit Log Entry Details"
      >
        <!-- Backdrop -->
        <div
          class="fixed inset-0 bg-black/60 backdrop-blur-sm"
          @click="closeDetailModal"
        />

        <!-- Panel -->
        <div class="relative z-10 w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl animate-scale-in">
          <div class="flex items-start justify-between mb-4">
            <h3 class="text-lg font-semibold text-foreground">Audit Log Entry</h3>
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
            <!-- Method + Action row -->
            <div class="flex items-center gap-2">
              <span
                class="inline-flex items-center rounded px-2 py-0.5 text-[11px] font-semibold uppercase"
                :class="[getMethodColor(detailEntry.method).bg, getMethodColor(detailEntry.method).text]"
              >
                {{ detailEntry.method }}
              </span>
              <span class="text-sm font-medium text-foreground">
                {{ formatAction(detailEntry.action) }}
              </span>
            </div>

            <!-- Detail grid -->
            <div class="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p class="text-xs font-medium text-muted-foreground">Admin User</p>
                <p class="text-foreground">{{ detailEntry.admin_email }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Status Code</p>
                <p class="font-mono" :class="getStatusCodeColor(detailEntry.status_code)">
                  {{ detailEntry.status_code || '—' }}
                </p>
              </div>
              <div class="col-span-2">
                <p class="text-xs font-medium text-muted-foreground">API Path</p>
                <p class="font-mono text-xs text-foreground break-all">{{ detailEntry.path }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">IP Address</p>
                <p class="font-mono text-xs text-foreground">{{ detailEntry.ip_address || '—' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Timestamp</p>
                <p class="text-foreground">{{ formatDateTime(detailEntry.timestamp) }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Relative</p>
                <p class="text-foreground">{{ formatRelativeTime(detailEntry.timestamp) }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted-foreground">Action</p>
                <p class="font-mono text-xs text-foreground">{{ detailEntry.action }}</p>
              </div>
            </div>

            <!-- Request Details JSON -->
            <div v-if="hasDetails(detailEntry)">
              <p class="text-xs font-medium text-muted-foreground mb-1">Request Details</p>
              <div class="max-h-64 overflow-auto rounded-lg bg-muted/50 p-3 border border-border">
                <pre class="whitespace-pre-wrap break-words font-mono text-xs text-foreground/80">{{ formatDetails(detailEntry.details) }}</pre>
              </div>
            </div>

            <!-- Close button -->
            <div class="flex items-center justify-end border-t border-border pt-4">
              <button
                type="button"
                class="btn-ghost px-4 py-2 text-sm"
                @click="closeDetailModal"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>