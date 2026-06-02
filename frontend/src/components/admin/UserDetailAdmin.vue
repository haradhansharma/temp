<script setup lang="ts">
/**
 * UserDetailAdmin — User detail page for /admin/users/:id.
 *
 * Features:
 *   - User profile card (avatar, name, email, role, status, joined date)
 *   - Tab navigation: Profile | Subscriptions | Audit Trail
 *   - Profile tab: user details, activate/deactivate, change role
 *   - Subscriptions tab: all subscriptions across products
 *   - Audit tab: compiled audit timeline (logins, plan changes, refunds)
 *   - Activate/deactivate confirmation dialog
 *   - Change role confirmation dialog
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable,
 * AdminConfirmDialog, AdminStatusBadge, AdminEmptyState, AdminAuditTimeline.
 */

import { ref, computed, onMounted, watch, onUnmounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { authHelpers } from "@/lib/api";
import { showToast } from "@/lib/toast";
import { adminApi, formatDateTime } from "@/lib/admin";
import type {
  UserDetail,
  UserItem,
  UserSubscriptionItem,
  UserAuditEntry,
  PaginationMeta,
} from "@/lib/admin";

import AdminPageHeader from "@/components/admin/AdminPageHeader.vue";
import AdminDataTable from "@/components/admin/AdminDataTable.vue";
import type { ColumnDef } from "@/components/admin/AdminDataTable.vue";
import AdminConfirmDialog from "@/components/admin/AdminConfirmDialog.vue";
import AdminStatusBadge from "@/components/admin/AdminStatusBadge.vue";
import AdminEmptyState from "@/components/admin/AdminEmptyState.vue";
import AdminAuditTimeline from "@/components/admin/AdminAuditTimeline.vue";

// ─── Props & Route ID ────────────────────────────────────────────────────────

const props = defineProps<{
  userId?: number;
}>();

/** Extract user ID from /admin/users/:id URL path. */
function getUserIdFromUrl(): number | undefined {
  const match = window.location.pathname.match(/\/admin\/users\/(\d+)/);
  return match ? Number(match[1]) : undefined;
}

const userId = computed(() => {
  const fromUrl = getUserIdFromUrl();
  if (fromUrl) return fromUrl;
  return props.userId;
});

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const loadError = ref<string | null>(null);
const actionLoading = ref<string | null>(null);

const user = ref<UserDetail | null>(null);
const activeTab = ref<"profile" | "subscriptions" | "audit">("profile");

// Audit tab data (lazy-loaded)
const auditEvents = ref<UserAuditEntry[]>([]);
const auditMeta = ref<PaginationMeta>({
  total_items: 0,
  total_pages: 1,
  current_page: 1,
  page_size: 20,
  has_next: false,
  has_previous: false,
});
const auditLoading = ref(false);
const auditLoaded = ref(false);

// Status change dialog
const showStatusDialog = ref(false);
const statusNewValue = ref(false);
const statusReason = ref("");

// Role change dialog
const showRoleDialog = ref(false);
const roleNewValue = ref("");
const roleReason = ref("");

// ─── Column definitions ──────────────────────────────────────────────────────

const subscriptionColumns = computed<ColumnDef[]>(() => [
  { key: "product_name", label: "Product", sortable: true },
  { key: "plan_name", label: "Plan", sortable: true },
  { key: "status", label: "Status", align: "center", width: "110px" },
  { key: "current_period_end", label: "Period End", width: "140px", hideOnMobile: true },
  { key: "actions", label: "", align: "right", width: "80px" },
]);

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchUser() {
  const id = userId.value;
  if (!id) {
    loadError.value = "Invalid user ID.";
    loading.value = false;
    return;
  }
  loading.value = true;
  loadError.value = null;
  try {
    user.value = await adminApi.getUser(id);
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

async function fetchAudit(page = 1) {
  const id = userId.value;
  if (!id) return;
  auditLoading.value = true;
  try {
    const data = await adminApi.getUserAudit(id, { page, page_size: 20 });
    auditEvents.value = data.results;
    auditMeta.value = data.meta;
    auditLoaded.value = true;
  } catch (err) {
    console.warn("Failed to load audit trail:", err);
  } finally {
    auditLoading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchUser();
});

// Re-fetch when navigating between user detail pages via View Transitions.
function handlePageLoad() {
  const newId = getUserIdFromUrl();
  if (newId && newId !== user.value?.id) {
    activeTab.value = "profile";
    auditLoaded.value = false;
    auditEvents.value = [];
    fetchUser();
  }
}
document.addEventListener("astro:page-load", handlePageLoad);
onUnmounted(() => {
  document.removeEventListener("astro:page-load", handlePageLoad);
});

// Lazy-load audit tab data when tab is selected
watch(activeTab, (tab) => {
  if (tab === "audit" && !auditLoaded.value) {
    fetchAudit();
  }
});

// ─── Format helpers ──────────────────────────────────────────────────────────

function getRoleBadgeColor(role: string): string {
  switch (role) {
    case "owner": return "purple";
    case "admin": return "amber";
    case "member": return "gray";
    default: return "gray";
  }
}

function formatPeriodEnd(sub: UserSubscriptionItem): string {
  if (sub.status === "canceled") return "Canceled";
  if (sub.status === "expired") return "Expired";
  if (!sub.current_period_end) return "—";
  return formatDateTime(sub.current_period_end);
}

/** Format date only (no time) */
function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const locale =
    typeof navigator !== "undefined" ? navigator.language : "en-US";
  return new Date(dateStr).toLocaleDateString(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ─── Activate / Deactivate User ──────────────────────────────────────────────

function openStatusDialog(newStatus: boolean) {
  statusNewValue.value = newStatus;
  statusReason.value = "";
  showStatusDialog.value = true;
}

async function confirmStatusChange() {
  const id = userId.value;
  if (!id) return;
  actionLoading.value = "status";
  try {
    await adminApi.updateUserStatus(id, {
      is_active: statusNewValue.value,
      reason: statusReason.value,
    });
    showToast(
      `User ${statusNewValue.value ? "activated" : "deactivated"}.`,
      "success",
    );
    showStatusDialog.value = false;
    await fetchUser();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Change Role ─────────────────────────────────────────────────────────────

function openRoleDialog(newRole: string) {
  roleNewValue.value = newRole;
  roleReason.value = "";
  showRoleDialog.value = true;
}

async function confirmRoleChange() {
  const id = userId.value;
  if (!id) return;
  actionLoading.value = "role";
  try {
    await adminApi.updateUserRole(id, {
      role: roleNewValue.value,
      reason: roleReason.value,
    });
    showToast(`User role changed to ${roleNewValue.value}.`, "success");
    showRoleDialog.value = false;
    await fetchUser();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Audit tab pagination ────────────────────────────────────────────────────

function handleAuditPageChange(page: number) {
  fetchAudit(page);
}
</script>

<template>
  <div class="space-y-6">
    <!-- Loading -->
    <div v-if="loading" class="space-y-6 animate-pulse">
      <div class="h-8 w-64 rounded skeleton" />
      <div class="h-48 rounded skeleton" />
    </div>

    <!-- Error -->
    <div
      v-else-if="loadError"
      class="card flex flex-col items-center gap-4 p-10 text-center"
    >
      <svg class="h-12 w-12 text-destructive/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <p class="font-medium text-foreground">Failed to load user</p>
      <p class="text-sm text-muted-foreground">{{ loadError }}</p>
      <button type="button" class="btn-secondary" @click="fetchUser">Try again</button>
    </div>

    <!-- User detail -->
    <template v-else-if="user">
      <!-- Page Header -->
      <AdminPageHeader
        :title="user.full_name || user.email"
        :description="user.email"
        :breadcrumbs="[
          { label: 'Admin', href: '/admin' },
          { label: 'Users', href: '/admin/users' },
          { label: user.full_name || `#${user.id}` },
        ]"
      >
        <template #secondary-action>
          <button
            type="button"
            class="btn-secondary inline-flex items-center gap-2"
            @click="openRoleDialog(user!.role === 'member' ? 'admin' : 'member')"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Change Role
          </button>
        </template>
        <template #primary-action>
          <div class="flex items-center gap-2">
            <button
              v-if="user.is_active"
              type="button"
              class="btn-secondary inline-flex items-center gap-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
              :disabled="actionLoading === 'status'"
              @click="openStatusDialog(false)"
            >
              <svg v-if="actionLoading === 'status'" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
              Deactivate
            </button>
            <button
              v-else
              type="button"
              class="btn-secondary inline-flex items-center gap-2 text-green-600 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-950"
              :disabled="actionLoading === 'status'"
              @click="openStatusDialog(true)"
            >
              <svg v-if="actionLoading === 'status'" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
              Activate
            </button>
          </div>
        </template>
      </AdminPageHeader>

      <!-- Info Card -->
      <div class="card p-5">
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">User</p>
            <p class="mt-1 text-sm font-medium text-foreground">{{ user.full_name || "—" }}</p>
            <p class="text-xs text-muted-foreground">{{ user.email }}</p>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Role / Status</p>
            <div class="mt-1 flex items-center gap-2">
              <AdminStatusBadge
                :status="user.role"
                type="custom"
                :custom-color="getRoleBadgeColor(user.role)"
              />
              <AdminStatusBadge
                :status="user.is_active ? 'active' : 'inactive'"
                type="active-inactive"
              />
            </div>
            <p v-if="user.is_staff" class="mt-1 text-xs text-purple-600 dark:text-purple-400">
              Staff access enabled
            </p>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Email Verified</p>
            <div class="mt-1">
              <span v-if="user.is_email_verified" class="inline-flex items-center gap-1 text-sm text-green-600 dark:text-green-400">
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                Verified
              </span>
              <span v-else class="text-sm text-muted-foreground">Not verified</span>
            </div>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Subscriptions</p>
            <p class="mt-1 text-sm text-foreground">
              {{ user.subscription_count }} total
              <span v-if="user.active_subscription_count > 0" class="text-xs text-muted-foreground">
                ({{ user.active_subscription_count }} active)
              </span>
            </p>
          </div>
        </div>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Tab Navigation                                                        -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div class="border-b border-border">
        <nav class="flex gap-6" aria-label="User detail tabs">
          <button
            v-for="tab in (['profile', 'subscriptions', 'audit'] as const)"
            :key="tab"
            class="border-b-2 pb-3 text-sm font-medium transition-colors"
            :class="
              activeTab === tab
                ? 'border-brand-600 text-brand-600 dark:border-brand-400 dark:text-brand-400'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            "
            @click="activeTab = tab"
          >
            {{
              tab === 'profile'
                ? 'Profile'
                : tab === 'subscriptions'
                  ? 'Subscriptions'
                  : 'Audit Trail'
            }}
            <span
              v-if="tab === 'subscriptions' && user.subscriptions.length"
              class="ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-muted px-1.5 text-[10px] font-semibold text-foreground"
            >
              {{ user.subscriptions.length }}
            </span>
            <span
              v-if="tab === 'audit' && auditLoaded && auditMeta.total_items"
              class="ml-1.5 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-muted px-1.5 text-[10px] font-semibold text-foreground"
            >
              {{ auditMeta.total_items }}
            </span>
          </button>
        </nav>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Profile Tab                                                           -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div v-if="activeTab === 'profile'">
        <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <!-- User Details -->
          <div class="card p-5">
            <h3 class="text-sm font-semibold text-foreground mb-4">User Details</h3>
            <dl class="space-y-3">
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">ID</dt>
                <dd class="text-sm font-mono text-foreground">#{{ user.id }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Full Name</dt>
                <dd class="text-sm text-foreground">{{ user.full_name || "—" }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Email</dt>
                <dd class="text-sm text-foreground">{{ user.email }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Role</dt>
                <dd>
                  <AdminStatusBadge :status="user.role" type="custom" :custom-color="getRoleBadgeColor(user.role)" />
                </dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Status</dt>
                <dd>
                  <AdminStatusBadge :status="user.is_active ? 'active' : 'inactive'" type="active-inactive" />
                </dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Email Verified</dt>
                <dd class="text-sm text-foreground">
                  <span v-if="user.is_email_verified" class="text-green-600 dark:text-green-400">Yes</span>
                  <span v-else class="text-muted-foreground">No</span>
                </dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Staff Access</dt>
                <dd class="text-sm text-foreground">
                  <span v-if="user.is_staff" class="text-purple-600 dark:text-purple-400">Yes</span>
                  <span v-else class="text-muted-foreground">No</span>
                </dd>
              </div>
              <div v-if="user.phone" class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Phone</dt>
                <dd class="text-sm text-foreground">{{ user.phone }}</dd>
              </div>
              <div v-if="user.timezone" class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Timezone</dt>
                <dd class="text-sm text-foreground">{{ user.timezone }}</dd>
              </div>
              <div v-if="user.currency" class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Currency</dt>
                <dd class="text-sm text-foreground">{{ user.currency }}</dd>
              </div>
              <div v-if="user.language" class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Language</dt>
                <dd class="text-sm text-foreground">{{ user.language }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Last Login</dt>
                <dd class="text-sm text-foreground">{{ user.last_login_at ? formatDateTime(user.last_login_at) : "Never" }}</dd>
              </div>
              <div class="flex items-center justify-between">
                <dt class="text-xs font-medium uppercase text-muted-foreground">Joined</dt>
                <dd class="text-sm text-foreground">{{ user.created_at ? formatDate(user.created_at) : "—" }}</dd>
              </div>
            </dl>
          </div>

          <!-- Quick Actions -->
          <div class="space-y-4">
            <div class="card p-5">
              <h3 class="text-sm font-semibold text-foreground mb-4">Quick Actions</h3>
              <div class="space-y-3">
                <button
                  v-if="user.is_active"
                  type="button"
                  class="w-full btn-secondary inline-flex items-center justify-center gap-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                  @click="openStatusDialog(false)"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                  </svg>
                  Deactivate User
                </button>
                <button
                  v-else
                  type="button"
                  class="w-full btn-secondary inline-flex items-center justify-center gap-2 text-green-600 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-950"
                  @click="openStatusDialog(true)"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  Activate User
                </button>
                <button
                  type="button"
                  class="w-full btn-secondary inline-flex items-center justify-center gap-2"
                  @click="openRoleDialog(user!.role === 'member' ? 'admin' : 'member')"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  Change Role
                </button>
              </div>
            </div>

            <!-- Subscription Summary Card -->
            <div class="card p-5">
              <h3 class="text-sm font-semibold text-foreground mb-3">Subscription Summary</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between text-sm">
                  <span class="text-muted-foreground">Total subscriptions</span>
                  <span class="font-medium text-foreground">{{ user.subscription_count }}</span>
                </div>
                <div class="flex items-center justify-between text-sm">
                  <span class="text-muted-foreground">Active / Trialing</span>
                  <span class="font-medium text-green-600 dark:text-green-400">{{ user.active_subscription_count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Subscriptions Tab                                                     -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div v-if="activeTab === 'subscriptions'">
        <AdminEmptyState
          v-if="user.subscriptions.length === 0"
          title="No subscriptions"
          description="This user has no subscriptions across any products."
          icon="document"
        />

        <AdminDataTable
          v-else
          :columns="subscriptionColumns"
          :rows="user.subscriptions as unknown as Record<string, unknown>[]"
          :meta="null"
          :loading="false"
          :clickable="true"
          row-key="id"
          empty-message="No subscriptions"
          @row-click="(row: Record<string, unknown>) => { const sub = row as UserSubscriptionItem; setTimeout(() => authHelpers.navigateTo(`/admin/subscriptions/${sub.id}`), 0); }"
        >
          <!-- Product cell -->
          <template #cell-product_name="{ row }">
            <span class="text-foreground">{{ (row as unknown as UserSubscriptionItem).product_name }}</span>
          </template>

          <!-- Plan cell -->
          <template #cell-plan_name="{ row }">
            <span class="font-medium text-foreground">{{ (row as unknown as UserSubscriptionItem).plan_name }}</span>
          </template>

          <!-- Status cell -->
          <template #cell-status="{ row }">
            <AdminStatusBadge :status="(row as unknown as UserSubscriptionItem).status" type="subscription" />
          </template>

          <!-- Period end cell -->
          <template #cell-current_period_end="{ row }">
            <span
              :class="{
                'text-muted-foreground': (row as unknown as UserSubscriptionItem).status === 'canceled' || (row as unknown as UserSubscriptionItem).status === 'expired',
              }"
            >
              {{ formatPeriodEnd(row as unknown as UserSubscriptionItem) }}
            </span>
          </template>

          <!-- Actions cell -->
          <template #cell-actions="{ row }">
            <div class="flex items-center justify-end gap-1" @click.stop>
              <a
                :href="`/admin/subscriptions/${(row as unknown as UserSubscriptionItem).id}`"
                class="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-brand-600 transition-colors hover:bg-brand-50 dark:text-brand-400 dark:hover:bg-brand-950"
              >
                <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                View
              </a>
            </div>
          </template>
        </AdminDataTable>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Audit Trail Tab                                                       -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div v-if="activeTab === 'audit'">
        <!-- Loading -->
        <div v-if="auditLoading" class="card animate-pulse p-6">
          <div class="space-y-4">
            <div class="h-4 w-40 rounded skeleton" />
            <div class="h-4 w-full rounded skeleton" />
            <div class="h-4 w-full rounded skeleton" />
          </div>
        </div>

        <template v-else-if="auditLoaded">
          <AdminEmptyState
            v-if="auditEvents.length === 0"
            title="No audit events"
            description="No activity recorded for this user."
            icon="clipboard"
          />

          <template v-else>
            <AdminAuditTimeline :entries="auditEvents" :loading="auditLoading" />

            <!-- Pagination -->
            <div
              v-if="auditMeta.total_pages > 1"
              class="mt-4 flex items-center justify-between"
            >
              <p class="text-sm text-muted-foreground">
                Page {{ auditMeta.current_page }} of {{ auditMeta.total_pages }}
                ({{ auditMeta.total_items }} events)
              </p>
              <div class="flex gap-2">
                <button
                  type="button"
                  class="btn-secondary text-sm"
                  :disabled="!auditMeta.has_previous"
                  @click="handleAuditPageChange(auditMeta.current_page - 1)"
                >
                  Previous
                </button>
                <button
                  type="button"
                  class="btn-secondary text-sm"
                  :disabled="!auditMeta.has_next"
                  @click="handleAuditPageChange(auditMeta.current_page + 1)"
                >
                  Next
                </button>
              </div>
            </div>
          </template>
        </template>
      </div>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Activate/Deactivate Confirmation Dialog                                -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showStatusDialog"
      :title="statusNewValue ? 'Activate User' : 'Deactivate User'"
      :message="'Are you sure you want to ' + (statusNewValue ? 'activate' : 'deactivate') + ' this account?'"
      :detail="statusNewValue
        ? 'The user will regain access to their account.'
        : 'The user will lose access to their account. Active subscriptions are NOT automatically canceled.'"
      :confirm-label="statusNewValue ? 'Activate' : 'Deactivate'"
      :destructive="!statusNewValue"
      :loading="actionLoading === 'status'"
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
      :message="'Change role from ' + (user?.role ?? '') + ' to ' + roleNewValue + '?'"
      :detail="roleNewValue === 'owner'
        ? 'Owners have full access to all admin features and billing.'
        : roleNewValue === 'admin'
          ? 'Admins can access the admin panel and manage resources.'
          : 'Members cannot access the admin panel.'"
      :confirm-label="'Change to ' + roleNewValue"
      :destructive="roleNewValue === 'member'"
      :loading="actionLoading === 'role'"
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
