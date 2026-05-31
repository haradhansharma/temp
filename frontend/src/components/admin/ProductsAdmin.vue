<script setup lang="ts">
/**
 * ProductsAdmin — Product list management page for /admin/products.
 *
 * Features:
 *   - Searchable, filterable data table with products
 *   - Create new product (modal form)
 *   - Edit product (modal form)
 *   - Toggle active/inactive
 *   - Delete product (with confirmation)
 *   - Navigate to product detail (click row)
 *
 * Uses 10.2 components: AdminPageHeader, AdminDataTable, AdminFilterBar,
 * AdminConfirmDialog, AdminStatusBadge, AdminEmptyState.
 */

import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { adminApi, formatDateTime } from "@/lib/admin";
import type {
  ProductItem,
  ProductDetail,
  ProductCreatePayload,
  ProductUpdatePayload,
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

const products = ref<ProductItem[]>([]);
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

// Create/Edit modal
const showFormModal = ref(false);
const isEditing = ref(false);
const editingProduct = ref<ProductItem | null>(null);
const formLoading = ref(false);
const formError = ref<string | null>(null);

const form = ref({
  name: "",
  slug: "",
  description: "",
  home_url: "",
});

// Delete dialog
const showDeleteDialog = ref(false);
const deletingProduct = ref<ProductItem | null>(null);

// ─── Column definitions ──────────────────────────────────────────────────────

const columns = computed<ColumnDef[]>(() => [
  { key: "name", label: "Product", sortable: true, defaultSort: "asc" },
  { key: "slug", label: "Slug", sortable: true, hideOnMobile: true },
  { key: "plan_count", label: "Plans", align: "center", width: "80px" },
  { key: "subscriber_count", label: "Subscribers", align: "center", width: "110px" },
  { key: "is_active", label: "Status", align: "center", width: "100px" },
  { key: "actions", label: "", align: "right", width: "160px" },
]);

// ─── Filter definitions ──────────────────────────────────────────────────────

const filters = computed<FilterDef[]>(() => [
  {
    key: "status",
    label: "Status",
    options: [
      { value: "", label: "All" },
      { value: "active", label: "Active" },
      { value: "inactive", label: "Inactive" },
    ],
    value: statusFilter.value,
    placeholder: "All Statuses",
  },
]);

const activeFilterCount = computed(() => (statusFilter.value ? 1 : 0));

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchProducts() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Record<string, unknown> = {
      page: currentPage.value,
      page_size: 20,
    };
    if (statusFilter.value === "active") params.is_active = true;
    if (statusFilter.value === "inactive") params.is_active = false;

    const data = await adminApi.listProducts(params);
    products.value = data.results;
    meta.value = data.meta;
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchProducts();
});

// ─── Client-side search filter ───────────────────────────────────────────────

const filteredProducts = computed(() => {
  if (!search.value.trim()) return products.value;
  const q = search.value.toLowerCase();
  return products.value.filter(
    (p) =>
      p.name.toLowerCase().includes(q) ||
      p.slug.toLowerCase().includes(q) ||
      p.description?.toLowerCase().includes(q)
  );
});

// ─── Navigation ──────────────────────────────────────────────────────────────

function handleRowClick(row: Record<string, unknown>) {
  const product = row as ProductItem;
  window.location.href = `/admin/products/${product.id}`;
}

// ─── Pagination ──────────────────────────────────────────────────────────────

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchProducts();
}

// ─── Filter events ───────────────────────────────────────────────────────────

function handleFilterUpdate({ key, value }: { key: string; value: string }) {
  if (key === "status") statusFilter.value = value;
  currentPage.value = 1;
  fetchProducts();
}

function handleClearFilters() {
  search.value = "";
  statusFilter.value = "";
  currentPage.value = 1;
  fetchProducts();
}

// ─── Sort ────────────────────────────────────────────────────────────────────

function handleSort({ key, direction }: { key: string; direction: "asc" | "desc" }) {
  // Client-side sort for current page
  products.value.sort((a, b) => {
    const aVal = (a as Record<string, unknown>)[key];
    const bVal = (b as Record<string, unknown>)[key];
    if (aVal == null || bVal == null) return 0;
    const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
    return direction === "asc" ? cmp : -cmp;
  });
}

// ─── Create Product ──────────────────────────────────────────────────────────

function openCreateModal() {
  isEditing.value = false;
  editingProduct.value = null;
  form.value = { name: "", slug: "", description: "", home_url: "" };
  formError.value = null;
  showFormModal.value = true;
}

// ─── Edit Product ────────────────────────────────────────────────────────────

function openEditModal(product: ProductItem) {
  isEditing.value = true;
  editingProduct.value = product;
  form.value = {
    name: product.name,
    slug: product.slug,
    description: product.description || "",
    home_url: product.home_url || "",
  };
  formError.value = null;
  showFormModal.value = true;
}

// ─── Auto-generate slug ─────────────────────────────────────────────────────

function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function handleNameInput() {
  if (!isEditing.value) {
    form.value.slug = generateSlug(form.value.name);
  }
}

// ─── Submit form ─────────────────────────────────────────────────────────────

async function handleFormSubmit() {
  formLoading.value = true;
  formError.value = null;

  try {
    if (isEditing.value && editingProduct.value) {
      const payload: ProductUpdatePayload = {
        name: form.value.name,
        slug: form.value.slug,
        description: form.value.description || undefined,
        home_url: form.value.home_url || undefined,
      };
      await adminApi.updateProduct(editingProduct.value.id, payload);
      showToast("Product updated successfully.", "success");
    } else {
      const payload: ProductCreatePayload = {
        name: form.value.name,
        slug: form.value.slug || undefined,
        description: form.value.description || undefined,
        home_url: form.value.home_url || undefined,
      };
      await adminApi.createProduct(payload);
      showToast("Product created successfully.", "success");
    }

    showFormModal.value = false;
    await fetchProducts();
  } catch (err) {
    formError.value = getErrorMessage(err);
  } finally {
    formLoading.value = false;
  }
}

// ─── Toggle Active ───────────────────────────────────────────────────────────

async function handleToggle(product: ProductItem) {
  actionLoading.value = `toggle-${product.id}`;
  try {
    await adminApi.toggleProduct(product.id);
    showToast(
      `Product ${product.is_active ? "deactivated" : "activated"}.`,
      "success"
    );
    await fetchProducts();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    actionLoading.value = null;
  }
}

// ─── Delete Product ──────────────────────────────────────────────────────────

function openDeleteDialog(product: ProductItem) {
  deletingProduct.value = product;
  showDeleteDialog.value = true;
}

async function confirmDelete() {
  if (!deletingProduct.value) return;
  actionLoading.value = `delete-${deletingProduct.value.id}`;
  try {
    await adminApi.deleteProduct(deletingProduct.value.id);
    showToast("Product deleted.", "success");
    showDeleteDialog.value = false;
    deletingProduct.value = null;
    await fetchProducts();
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
      title="Products"
      description="Manage products, plans, service domains, and access entries."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Products' }]"
    >
      <template #primary-action>
        <button type="button" class="btn-primary inline-flex items-center gap-2" @click="openCreateModal">
          <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          New Product
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
        <p class="font-medium text-foreground">Failed to load products</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchProducts">Try again</button>
    </div>

    <template v-else>
      <!-- Filter Bar -->
      <AdminFilterBar
        v-model:search="search"
        :filters="filters"
        :active-count="activeFilterCount"
        search-placeholder="Search products..."
        @update:filter="handleFilterUpdate"
        @clear="handleClearFilters"
      />

      <!-- Data Table -->
      <AdminDataTable
        :columns="columns"
        :rows="filteredProducts"
        :meta="meta"
        :loading="loading"
        :clickable="true"
        row-key="id"
        empty-message="No products found"
        empty-description="Create your first product to get started."
        @row-click="handleRowClick"
        @page-change="handlePageChange"
        @sort="handleSort"
      >
        <!-- Product name cell -->
        <template #cell-name="{ row }">
          <div class="flex items-center gap-3">
            <div
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-600 dark:bg-amber-950 dark:text-amber-400"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
            </div>
            <div class="min-w-0">
              <p class="truncate font-medium text-foreground">{{ row.name }}</p>
              <p v-if="row.description" class="truncate text-xs text-muted-foreground">{{ row.description }}</p>
            </div>
          </div>
        </template>

        <!-- Status cell -->
        <template #cell-is_active="{ row }">
          <AdminStatusBadge :status="row.is_active ? 'active' : 'inactive'" type="active-inactive" />
        </template>

        <!-- Actions cell -->
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end gap-1" @click.stop>
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="Edit"
              @click="openEditModal(row)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              :title="row.is_active ? 'Deactivate' : 'Activate'"
              :disabled="actionLoading === `toggle-${row.id}`"
              @click="handleToggle(row)"
            >
              <svg v-if="actionLoading === `toggle-${row.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <svg v-else-if="row.is_active" class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
              <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </button>
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
              title="Delete"
              @click="openDeleteDialog(row)"
            >
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </template>
      </AdminDataTable>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Create / Edit Product Modal                                           -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <Teleport to="body">
      <div
        v-if="showFormModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-black/50 backdrop-blur-sm"
          @click="showFormModal = false"
        />

        <!-- Modal -->
        <div
          class="relative w-full max-w-xl rounded-xl border border-border bg-card p-6 shadow-xl"
          role="dialog"
          aria-modal="true"
        >
          <h2 class="text-lg font-semibold text-foreground">
            {{ isEditing ? "Edit Product" : "New Product" }}
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            {{ isEditing ? "Update product details below." : "Create a new product with plans and access entries." }}
          </p>

          <form class="mt-5 space-y-4" @submit.prevent="handleFormSubmit">
            <!-- Name -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">
                Name <span class="text-destructive">*</span>
              </label>
              <input
                v-model="form.name"
                type="text"
                class="input-field"
                placeholder="e.g. Finance Tracker"
                required
                @input="handleNameInput"
              />
            </div>

            <!-- Slug -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Slug</label>
              <input
                v-model="form.slug"
                type="text"
                class="input-field"
                placeholder="auto-generated from name"
              />
              <p class="mt-1 text-xs text-muted-foreground">Used in URLs and API references. Auto-generated from name if left empty.</p>
            </div>

            <!-- Description -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Description</label>
              <textarea
                v-model="form.description"
                class="input-field min-h-[80px]"
                placeholder="Brief description of the product..."
                rows="3"
              />
            </div>

            <!-- Home URL -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Home URL</label>
              <input
                v-model="form.home_url"
                type="url"
                class="input-field"
                placeholder="https://finance.sattabase.tld"
              />
            </div>

            <!-- Error -->
            <div
              v-if="formError"
              class="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-400"
            >
              {{ formError }}
            </div>

            <!-- Actions -->
            <div class="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                class="btn-secondary"
                :disabled="formLoading"
                @click="showFormModal = false"
              >
                Cancel
              </button>
              <button
                type="submit"
                class="btn-primary inline-flex items-center gap-2"
                :disabled="formLoading"
              >
                <svg
                  v-if="formLoading"
                  class="h-4 w-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ isEditing ? "Update Product" : "Create Product" }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════════════════════════════════════════════════════════════════ -->
    <!--  Delete Confirmation Dialog                                            -->
    <!-- ═══════════════════════════════════════════════════════════════════════ -->

    <AdminConfirmDialog
      v-model:open="showDeleteDialog"
      title="Delete Product"
      :message="'Delete \'' + (deletingProduct?.name ?? '') + '\'?'"
      detail="This will soft-delete the product. Only products with no active subscriptions can be deleted."
      confirm-label="Delete"
      :destructive="true"
      :loading="actionLoading?.startsWith('delete-')"
      @confirm="confirmDelete"
    />
  </div>
</template>
