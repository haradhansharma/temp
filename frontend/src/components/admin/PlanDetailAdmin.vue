<script setup lang="ts">
/**
 * PlanDetailAdmin — Plan detail page for /admin/plans/:planId.
 *
 * Features:
 *   - Plan info card with edit/toggle/feature/duplicate/delete actions
 *   - Access entries read-only table (CRUD is done via product's Access Matrix tab)
 *   - Link to product's Access Matrix for managing entries
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable, AdminConfirmDialog,
 * AdminStatusBadge, AdminEmptyState.
 */

import { ref, computed, onMounted, onUnmounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { adminApi, formatDateTime } from "@/lib/admin";
import type {
  PlanDetail,
  PlanUpdatePayload,
  AccessEntryItem,
} from "@/lib/admin";

import AdminPageHeader from "@/components/admin/AdminPageHeader.vue";
import AdminDataTable from "@/components/admin/AdminDataTable.vue";
import type { ColumnDef } from "@/components/admin/AdminDataTable.vue";
import AdminConfirmDialog from "@/components/admin/AdminConfirmDialog.vue";
import AdminStatusBadge from "@/components/admin/AdminStatusBadge.vue";

// ─── Props & Route ID ────────────────────────────────────────────────────────
//
// With Astro ClientRouter (View Transitions) + client:only="vue", the Astro
// prop can become undefined during client-side page swaps.  We therefore read
// the plan ID from the URL path as the primary source, with the Astro prop
// as a fallback for direct (full-page) loads.

const props = defineProps<{
  planId?: number;
}>();

/** Extract plan ID from /admin/plans/:planId URL path. */
function getPlanIdFromUrl(): number | undefined {
  const match = window.location.pathname.match(/\/admin\/plans\/(\d+)/);
  return match ? Number(match[1]) : undefined;
}

const planId = computed(() => {
  // URL is the most reliable source during View Transition navigations
  const fromUrl = getPlanIdFromUrl();
  if (fromUrl) return fromUrl;
  // Fallback to Astro prop (works on direct full-page loads)
  return props.planId;
});

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const loadError = ref<string | null>(null);
const actionLoading = ref<string | null>(null);

const plan = ref<PlanDetail | null>(null);

// Edit plan modal
const showEditModal = ref(false);
const editLoading = ref(false);
const editError = ref<string | null>(null);
const editForm = ref({
  name: "",
  slug: "",
  priceDollars: 0,
  currency: "usd",
  billing_cycle: "monthly" as "monthly" | "yearly",
  trial_days: 0,
  is_featured: false,
  sort_order: 0,
});

// Delete confirmation
const showDeletePlanDialog = ref(false);

// ─── Column definitions: Access Entries (read-only) ──────────────────────────

const entryColumns = computed<ColumnDef[]>(() => [
  { key: "key", label: "Key", sortable: true, defaultSort: "asc" },
  { key: "value", label: "Value", width: "120px" },
  { key: "value_type", label: "Type", align: "center", width: "90px", hideOnMobile: true },
  { key: "description", label: "Description", hideOnMobile: true },
]);

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchPlan() {
  const id = planId.value;
  if (!id) {
    loadError.value = "Invalid plan ID.";
    loading.value = false;
    return;
  }
  loading.value = true;
  loadError.value = null;
  try {
    plan.value = await adminApi.getPlan(id);
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchPlan();
});

// Re-fetch when navigating between plan detail pages via View Transitions.
// astro:page-load fires on every navigation (initial + client-side swaps).
function handlePageLoad() {
  const newId = getPlanIdFromUrl();
  if (newId && newId !== plan.value?.id) {
    fetchPlan();
  }
}
document.addEventListener("astro:page-load", handlePageLoad);
onUnmounted(() => {
  document.removeEventListener("astro:page-load", handlePageLoad);
});

// ─── Format price ────────────────────────────────────────────────────────────

function formatCents(cents: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency?.toUpperCase() || "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

function dollarsToCents(dollars: number): number {
  return Math.round(dollars * 100);
}

function centsToDollars(cents: number): number {
  return cents / 100;
}

// ─── Edit Plan ───────────────────────────────────────────────────────────────

function openEditModal() {
  if (!plan.value) return;
  editForm.value = {
    name: plan.value.name,
    slug: plan.value.slug,
    priceDollars: centsToDollars(plan.value.price_cents),
    currency: plan.value.currency,
    billing_cycle: plan.value.billing_cycle,
    trial_days: plan.value.trial_days,
    is_featured: plan.value.is_featured,
    sort_order: plan.value.sort_order,
  };
  editError.value = null;
  showEditModal.value = true;
}

async function handleEditSubmit() {
  editLoading.value = true;
  editError.value = null;
  try {
    const payload: PlanUpdatePayload = {
      name: editForm.value.name,
      slug: editForm.value.slug,
      price_cents: dollarsToCents(editForm.value.priceDollars),
      currency: editForm.value.currency,
      billing_cycle: editForm.value.billing_cycle,
      trial_days: editForm.value.trial_days,
      is_featured: editForm.value.is_featured,
      sort_order: editForm.value.sort_order,
    };
    await adminApi.updatePlan(planId.value!, payload);
    showToast("Plan updated.", "success");
    showEditModal.value = false;
    await fetchPlan();
  } catch (err) {
    editError.value = getErrorMessage(err);
  } finally {
    editLoading.value = false;
  }
}

// ─── Plan actions ────────────────────────────────────────────────────────────

async function handleToggle() {
  if (!plan.value) return;
  actionLoading.value = "toggle";
  try {
    await adminApi.togglePlan(planId.value!);
    showToast(`Plan ${plan.value.is_active ? "deactivated" : "activated"}.`, "success");
    await fetchPlan();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

async function handleToggleFeature() {
  if (!plan.value) return;
  actionLoading.value = "feature";
  try {
    await adminApi.togglePlanFeature(planId.value!);
    showToast(`Plan ${plan.value.is_featured ? "unfeatured" : "featured"}.`, "success");
    await fetchPlan();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

async function handleDuplicate() {
  actionLoading.value = "duplicate";
  try {
    await adminApi.duplicatePlan(planId.value!);
    showToast("Plan duplicated.", "success");
    await fetchPlan();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

async function confirmDeletePlan() {
  actionLoading.value = "delete-plan";
  try {
    await adminApi.deletePlan(planId.value!);
    showToast("Plan deleted.", "success");
    showDeletePlanDialog.value = false;
    // Navigate back to product detail
    if (plan.value) {
      window.location.href = `/admin/products/${plan.value.product_id}`;
    } else {
      window.location.href = "/admin/products";
    }
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Sort entries ────────────────────────────────────────────────────────────

function handleEntrySort({ key, direction }: { key: string; direction: "asc" | "desc" }) {
  if (!plan.value) return;
  plan.value.access_entries.sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[key];
    const bVal = (b as Record<string, unknown>)[key];
    if (aVal == null || bVal == null) return 0;
    const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
    return direction === "asc" ? cmp : -cmp;
  });
}

// ─── Navigate to product's Access Matrix tab ────────────────────────────────

function goToAccessMatrix() {
  if (plan.value) {
    // Use Astro's client-side navigation for smooth transition
    window.location.href = `/admin/products/${plan.value.product_id}?tab=matrix`;
  }
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
      <p class="font-medium text-foreground">Failed to load plan</p>
      <p class="text-sm text-muted-foreground">{{ loadError }}</p>
      <button type="button" class="btn-secondary" @click="fetchPlan">Try again</button>
    </div>

    <!-- Plan detail -->
    <template v-else-if="plan">
      <!-- Page Header -->
      <AdminPageHeader
        :title="plan.name"
        :description="`${plan.product_name} — ${formatCents(plan.price_cents, plan.currency)}/${plan.billing_cycle}`"
        :breadcrumbs="[
          { label: 'Admin', href: '/admin' },
          { label: 'Products', href: '/admin/products' },
          { label: plan.product_name, href: `/admin/products/${plan.product_id}` },
          { label: plan.name },
        ]"
      >
        <template #secondary-action>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="btn-secondary inline-flex items-center gap-2"
              @click="openEditModal"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Edit
            </button>
            <button
              type="button"
              class="btn-secondary inline-flex items-center gap-2"
              :disabled="actionLoading === 'feature'"
              @click="handleToggleFeature"
            >
              <svg class="h-4 w-4" :class="plan.is_featured ? 'text-amber-500' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
              </svg>
              {{ plan.is_featured ? "Unfeature" : "Feature" }}
            </button>
          </div>
        </template>
        <template #primary-action>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="btn-secondary inline-flex items-center gap-2"
              :disabled="actionLoading === 'duplicate'"
              @click="handleDuplicate"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Duplicate
            </button>
            <button
              type="button"
              class="btn-secondary inline-flex items-center gap-2"
              :disabled="actionLoading === 'toggle'"
              @click="handleToggle"
            >
              {{ plan.is_active ? "Deactivate" : "Activate" }}
            </button>
            <button
              type="button"
              class="btn-secondary inline-flex items-center gap-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
              @click="showDeletePlanDialog = true"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete
            </button>
          </div>
        </template>
      </AdminPageHeader>

      <!-- Plan Info Card -->
      <div class="card p-5">
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Price</p>
            <p class="mt-1 text-sm font-semibold text-foreground">
              {{ formatCents(plan.price_cents, plan.currency) }}
              <span class="font-normal text-muted-foreground">/ {{ plan.billing_cycle }}</span>
            </p>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Trial</p>
            <p class="mt-1 text-sm text-foreground">
              {{ plan.trial_days > 0 ? `${plan.trial_days} days` : "None" }}
            </p>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Subscribers</p>
            <p class="mt-1 text-sm font-medium text-foreground">{{ plan.subscriber_count }}</p>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Status</p>
            <div class="mt-1 flex items-center gap-2">
              <AdminStatusBadge :status="plan.is_active ? 'active' : 'inactive'" type="active-inactive" />
              <span
                v-if="plan.is_featured"
                class="inline-flex items-center rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950 dark:text-amber-400"
              >
                Featured
              </span>
            </div>
          </div>
          <div>
            <p class="text-xs font-medium uppercase text-muted-foreground">Sort Order</p>
            <p class="mt-1 text-sm text-foreground">{{ plan.sort_order }}</p>
          </div>
        </div>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Access Entries (Read-Only) — CRUD via Product's Access Matrix tab     -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div class="mb-4 flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold text-foreground">Access Entries</h3>
          <p class="text-xs text-muted-foreground">
            {{ plan.access_entries.length }} entries defined for this plan.
          </p>
        </div>
        <button
          type="button"
          class="btn-primary inline-flex items-center gap-2 text-sm"
          @click="goToAccessMatrix"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
          Manage in Access Matrix
        </button>
      </div>

      <!-- Info banner about Access Matrix -->
      <div class="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-900 dark:bg-blue-950/50">
        <div class="flex items-start gap-3">
          <svg class="mt-0.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div class="text-sm">
            <p class="text-blue-800 dark:text-blue-300">
              Access entries are managed through the
              <a
                :href="`/admin/products/${plan.product_id}?tab=matrix`"
                class="font-medium underline underline-offset-2 hover:text-blue-600 dark:hover:text-blue-200"
              >
                {{ plan.product_name }} Access Matrix
              </a>.
              The matrix lets you add, edit, and sync features across all plans at once.
            </p>
          </div>
        </div>
      </div>

      <AdminDataTable
        :columns="entryColumns"
        :rows="plan.access_entries"
        :meta="null"
        :loading="false"
        :clickable="false"
        row-key="id"
        empty-message="No access entries"
        empty-description="Access entries for this plan are managed through the product's Access Matrix tab."
        @sort="handleEntrySort"
      >
        <!-- Key cell -->
        <template #cell-key="{ row }">
          <code class="rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-foreground">{{ row.key }}</code>
        </template>

        <!-- Value cell -->
        <template #cell-value="{ row }">
          <span class="text-sm font-medium text-foreground">{{ row.value }}</span>
        </template>

        <!-- Value type cell -->
        <template #cell-value_type="{ row }">
          <span
            class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold"
            :class="
              row.value_type === 'boolean'
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400'
                : row.value_type === 'integer'
                  ? 'bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-400'
                  : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
            "
          >
            {{ row.value_type }}
          </span>
        </template>

        <!-- Description cell -->
        <template #cell-description="{ row }">
          <span class="text-sm text-muted-foreground">{{ row.description || "—" }}</span>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Edit Plan Modal                                                        -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <Teleport to="body">
      <div
        v-if="showEditModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="showEditModal = false" />
        <div class="relative w-full max-w-xl rounded-xl border border-border bg-card p-6 shadow-xl" role="dialog" aria-modal="true">
          <h2 class="text-lg font-semibold text-foreground">Edit Plan</h2>
          <form class="mt-5 space-y-4" @submit.prevent="handleEditSubmit">
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Name <span class="text-destructive">*</span></label>
              <input v-model="editForm.name" type="text" class="input-field" required />
            </div>
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Slug</label>
              <input v-model="editForm.slug" type="text" class="input-field" />
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="mb-1.5 block text-sm font-medium text-foreground">Price</label>
                <input v-model.number="editForm.priceDollars" type="number" step="0.01" min="0" class="input-field" />
              </div>
              <div>
                <label class="mb-1.5 block text-sm font-medium text-foreground">Currency</label>
                <select v-model="editForm.currency" class="input-field">
                  <option value="usd">USD</option>
                  <option value="eur">EUR</option>
                  <option value="gbp">GBP</option>
                  <option value="bdt">BDT</option>
                </select>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="mb-1.5 block text-sm font-medium text-foreground">Billing Cycle</label>
                <select v-model="editForm.billing_cycle" class="input-field">
                  <option value="monthly">Monthly</option>
                  <option value="yearly">Yearly</option>
                </select>
              </div>
              <div>
                <label class="mb-1.5 block text-sm font-medium text-foreground">Trial Days</label>
                <input v-model.number="editForm.trial_days" type="number" min="0" class="input-field" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div class="flex items-center gap-2">
                <input v-model="editForm.is_featured" type="checkbox" class="h-4 w-4 rounded border-border" />
                <label class="text-sm font-medium text-foreground">Featured</label>
              </div>
              <div>
                <label class="mb-1.5 block text-sm font-medium text-foreground">Sort Order</label>
                <input v-model.number="editForm.sort_order" type="number" min="0" class="input-field" />
              </div>
            </div>
            <div v-if="editError" class="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400">{{ editError }}</div>
            <div class="flex items-center justify-end gap-3 pt-2">
              <button type="button" class="btn-secondary" :disabled="editLoading" @click="showEditModal = false">Cancel</button>
              <button type="submit" class="btn-primary" :disabled="editLoading">Update Plan</button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Confirmation Dialogs                                                   -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showDeletePlanDialog"
      title="Delete Plan"
      :message="'Delete plan \'' + (plan?.name ?? '') + '\'?'"
      detail="Only plans with no active subscribers can be deleted."
      confirm-label="Delete"
      :destructive="true"
      :loading="actionLoading === 'delete-plan'"
      @confirm="confirmDeletePlan"
    />
  </div>
</template>
