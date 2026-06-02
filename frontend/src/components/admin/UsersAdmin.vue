<script setup lang="ts">
/**
 * UsersAdmin — User list management page for /admin/users.
 *
 * Features:
 *   - Searchable, filterable data table with users
 *   - Filters: role dropdown, status dropdown, email verified toggle, search by email/name
 *   - Row click navigates to user detail
 *   - Actions: view (navigate), activate/deactivate, change role
 *   - Server-side pagination and filtering
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable, AdminFilterBar,
 * AdminConfirmDialog, AdminStatusBadge.
 */

import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { authHelpers } from "@/lib/api";
import { showToast } from "@/lib/toast";
import { adminApi, formatDateTime } from "@/lib/admin";
import type {
  UserItem,
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

const users = ref<UserItem[]>([]);
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
const roleFilter = ref("");
const statusFilter = ref("");
const verifiedFilter = ref("");
const currentPage = ref(1);

// Status change dialog
const showStatusDialog = ref(false);
const statusTargetUser = ref<UserItem | null>(null);
const statusNewValue = ref(false);
const statusReason = ref("");

// Role change dialog
const showRoleDialog = ref(false);
const roleTargetUser = ref<UserItem | null>(null);
const roleNewValue = ref("");
const roleReason = ref("");

// ─── Column definitions ──────────────────────────────────────────────────────

const columns = computed<ColumnDef[]>(() => [
  { key: "full_name", label: "User", sortable: true, defaultSort: "asc" },
  { key: "role", label: "Role", align: "center", width: "100px" },
  { key: "is_email_verified", label: "Verified", align: "center", width: "100px", hideOnMobile: true },
  { key: "subscription_count", label: "Subs", align: "center", width: "80px", hideOnMobile: true },
  { key: "is_active", label: "Status", align: "center", width: "100px" },
  { key: "last_login_at", label: "Last Login", sortable: true, width: "140px", hideOnMobile: true },
  { key: "actions", label: "", align: "right", width: "120px" },
]);

// ─── Filter definitions ──────────────────────────────────────────────────────

const filters = computed<FilterDef[]>(() => [
  {
    key: "role",
    label: "Role",
    options: [
      { value: "owner", label: "Owner" },
      { value: "admin", label: "Admin" },
      { value: "member", label: "Member" },
    ],
    value: roleFilter.value,
    placeholder: "All Roles",
  },
  {
    key: "status",
    label: "Status",
    options: [
      { value: "true", label: "Active" },
      { value: "false", label: "Inactive" },
    ],
    value: statusFilter.value,
    placeholder: "All Statuses",
  },
  {
    key: "verified",
    label: "Email Verified",
    options: [
      { value: "true", label: "Verified" },
      { value: "false", label: "Not Verified" },
    ],
    value: verifiedFilter.value,
    placeholder: "All",
  },
]);

const activeFilterCount = computed(() => {
  let count = 0;
  if (roleFilter.value) count++;
  if (statusFilter.value) count++;
  if (verifiedFilter.value) count++;
  return count;
});

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchUsers() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Record<string, unknown> = {
      page: currentPage.value,
      page_size: 20,
    };
    if (search.value.trim()) params.search = search.value.trim();
    if (roleFilter.value) params.role = roleFilter.value;
    if (statusFilter.value) params.is_active = statusFilter.value === "true";
    if (verifiedFilter.value) params.is_email_verified = verifiedFilter.value === "true";

    const data = await adminApi.listUsers(params);
    users.value = data.results;
    meta.value = data.meta;
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchUsers();
});

// ─── Navigation ──────────────────────────────────────────────────────────────

// VUE 3 CONVENTION: Use authHelpers.navigateTo() (Astro's navigate())
// instead of window.location.href to avoid the "querySelector null" error
// during View Transitions. Defer with setTimeout to avoid race conditions.
function handleRowClick(row: Record<string, unknown>) {
  const user = row as UserItem;
  setTimeout(() => authHelpers.navigateTo(`/admin/users/${user.id}`), 0);
}

function viewUser(id: number) {
  setTimeout(() => authHelpers.navigateTo(`/admin/users/${id}`), 0);
}

// ─── Pagination ──────────────────────────────────────────────────────────────

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchUsers();
}

// ─── Filter events ───────────────────────────────────────────────────────────

function handleFilterUpdate({ key, value }: { key: string; value: string }) {
  if (key === "role") roleFilter.value = value;
  if (key === "status") statusFilter.value = value;
  if (key === "verified") verifiedFilter.value = value;
  currentPage.value = 1;
  fetchUsers();
}

function handleClearFilters() {
  search.value = "";
  roleFilter.value = "";
  statusFilter.value = "";
  verifiedFilter.value = "";
  currentPage.value = 1;
  fetchUsers();
}

// ─── Sort ────────────────────────────────────────────────────────────────────

function handleSort({ key, direction }: { key: string; direction: "asc" | "desc" }) {
  users.value.sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[key];
    const bVal = (b as Record<string, unknown>)[key];
    if (aVal == null || bVal == null) return 0;
    const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
    return direction === "asc" ? cmp : -cmp;
  });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getRoleBadgeColor(role: string): string {
  switch (role) {
    case "owner": return "purple";
    case "admin": return "amber";
    case "member": return "gray";
    default: return "gray";
  }
}

function formatLastLogin(user: UserItem): string {
  if (!user.last_login_at) return "Never";
  return formatDateTime(user.last_login_at);
}

// ─── Activate / Deactivate User ──────────────────────────────────────────────

function openStatusDialog(user: UserItem, newStatus: boolean) {
  statusTargetUser.value = user;
  statusNewValue.value = newStatus;
  statusReason.value = "";
  showStatusDialog.value = true;
}

async function confirmStatusChange() {
  if (!statusTargetUser.value) return;
  actionLoading.value = `status-${statusTargetUser.value.id}`;
  try {
    await adminApi.updateUserStatus(statusTargetUser.value.id, {
      is_active: statusNewValue.value,
      reason: statusReason.value,
    });
    showToast(
      `User ${statusNewValue.value ? "activated" : "deactivated"}.`,
      "success",
    );
    showStatusDialog.value = false;
    statusTargetUser.value = null;
    await fetchUsers();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Change Role ─────────────────────────────────────────────────────────────

function openRoleDialog(user: UserItem, newRole: string) {
  roleTargetUser.value = user;
  roleNewValue.value = newRole;
  roleReason.value = "";
  showRoleDialog.value = true;
}

async function confirmRoleChange() {
  if (!roleTargetUser.value) return;
  actionLoading.value = `role-${roleTargetUser.value.id}`;
  try {
    await adminApi.updateUserRole(roleTargetUser.value.id, {
      role: roleNewValue.value,
      reason: roleReason.value,
    });
    showToast(`User role changed to ${roleNewValue.value}.`, "success");
    showRoleDialog.value = false;
    roleTargetUser.value = null;
    await fetchUsers();
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
      title="Users"
      description="Search users, view profiles, and manage roles."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Users' }]"
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
        <p class="font-medium text-foreground">Failed to load users</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchUsers">Try again</button>
    </div>

    <template v-else>
      <!-- Filter Bar -->
      <AdminFilterBar
        v-model:search="search"
        :filters="filters"
        :active-count="activeFilterCount"
        search-placeholder="Search by email or name..."
        @update:filter="handleFilterUpdate"
        @clear="handleClearFilters"
      />

      <!-- Data Table -->
      <AdminDataTable
        :columns="columns"
        :rows="users"
        :meta="meta"
        :loading="loading"
        :clickable="true"
        row-key="id"
        empty-message="No users found"
        empty-description="No users match the current filters."
        @row-click="handleRowClick"
        @page-change="handlePageChange"
        @sort="handleSort"
      >
        <!-- User name/email cell -->
        <template #cell-full_name="{ row }">
          <div class="min-w-0">
            <p class="truncate font-medium text-foreground">{{ row.full_name || row.email }}</p>
            <p v-if="row.full_name" class="truncate text-xs text-muted-foreground">{{ row.email }}</p>
          </div>
        </template>

        <!-- Role cell -->
        <template #cell-role="{ row }">
          <AdminStatusBadge
            :status="row.role"
            type="custom"
            :custom-color="getRoleBadgeColor(row.role)"
          />
        </template>

        <!-- Verified cell -->
        <template #cell-is_email_verified="{ row }">
          <span v-if="row.is_email_verified" class="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
            <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            <span class="text-xs font-medium">Yes</span>
          </span>
          <span v-else class="text-xs text-muted-foreground">No</span>
        </template>

        <!-- Subscription count cell -->
        <template #cell-subscription_count="{ row }">
          <span class="text-sm text-foreground">
            {{ row.subscription_count }}
            <span v-if="row.active_subscription_count > 0" class="text-xs text-muted-foreground">
              ({{ row.active_subscription_count }} active)
            </span>
          </span>
        </template>

        <!-- Status cell -->
        <template #cell-is_active="{ row }">
          <AdminStatusBadge
            :status="row.is_active ? 'active' : 'inactive'"
            type="active-inactive"
          />
        </template>

        <!-- Last login cell -->
        <template #cell-last_login_at="{ row }">
          <span class="text-muted-foreground">{{ formatLastLogin(row) }}</span>
        </template>

        <!-- Actions cell -->
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end gap-1" @click.stop>
            <!-- View -->
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="View"
              @click="viewUser(row.id)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </button>

            <!-- Activate/Deactivate -->
            <button
              v-if="row.is_active"
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
              title="Deactivate"
              :disabled="actionLoading === `status-${row.id}`"
              @click="openStatusDialog(row, false)"
            >
              <svg v-if="actionLoading === `status-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
            </button>
            <button
              v-else
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-green-50 hover:text-green-600 dark:hover:bg-green-950 dark:hover:text-green-400"
              title="Activate"
              :disabled="actionLoading === `status-${row.id}`"
              @click="openStatusDialog(row, true)"
            >
              <svg v-if="actionLoading === `status-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            </button>

            <!-- Change Role -->
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-amber-50 hover:text-amber-600 dark:hover:bg-amber-950 dark:hover:text-amber-400"
              title="Change Role"
              :disabled="actionLoading === `role-${row.id}`"
              @click="openRoleDialog(row, row.role === 'member' ? 'admin' : 'member')"
            >
              <svg v-if="actionLoading === `role-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
          </div>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Activate/Deactivate Confirmation Dialog                                -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showStatusDialog"
      :title="statusNewValue ? 'Activate User' : 'Deactivate User'"
      :message="'Are you sure you want to ' + (statusNewValue ? 'activate' : 'deactivate') + ' the account for \'' + (statusTargetUser?.email ?? '') + '\'?'"
      :detail="statusNewValue
        ? 'The user will regain access to their account.'
        : 'The user will lose access to their account. Active subscriptions are NOT automatically canceled.'"
      :confirm-label="statusNewValue ? 'Activate' : 'Deactivate'"
      :destructive="!statusNewValue"
      :loading="actionLoading?.startsWith('status-')"
      @confirm="confirmStatusChange"
    >
      <div class="mt-3">
        <label class="block text-xs font-medium text-muted-foreground mb-1">Reason (optional)</label>
        <input
          v-model="statusReason"
          type="text"
          class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
          placeholder="Reason for this change..."
        />
      </div>
    </AdminConfirmDialog>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Change Role Confirmation Dialog                                        -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showRoleDialog"
      title="Change User Role"
      :message="'Change role for \'' + (roleTargetUser?.email ?? '') + '\' from ' + (roleTargetUser?.role ?? '') + ' to ' + roleNewValue + '?'"
      :detail="roleNewValue === 'owner'
        ? 'Owners have full access to all admin features and billing.'
        : roleNewValue === 'admin'
          ? 'Admins can access the admin panel and manage resources.'
          : 'Members cannot access the admin panel.'"
      :confirm-label="'Change to ' + roleNewValue"
      :destructive="roleNewValue === 'member'"
      :loading="actionLoading?.startsWith('role-')"
      @confirm="confirmRoleChange"
    >
      <div class="space-y-3 mt-3">
        <div>
          <label class="block text-xs font-medium text-muted-foreground mb-1">New Role</label>
          <select
            v-model="roleNewValue"
            class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
          >
            <option value="owner">Owner</option>
            <option value="admin">Admin</option>
            <option value="member">Member</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-muted-foreground mb-1">Reason (optional)</label>
          <input
            v-model="roleReason"
            type="text"
            class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
            placeholder="Reason for this change..."
          />
        </div>
      </div>
    </AdminConfirmDialog>
  </div>
</template>
