<script setup lang="ts">
/**
 * AdminDataTable — Reusable data table for admin pages.
 *
 * Features:
 *   - Sortable columns (click header to sort asc/desc)
 *   - Server-side pagination (Previous/Next + page indicator)
 *   - Per-column filters (rendered via filter slot)
 *   - Bulk selection with checkboxes (select-all + individual)
 *   - Loading skeleton with shimmer animation
 *   - Empty state slot
 *   - Row click action support
 *
 * Usage:
 *   <AdminDataTable
 *     :columns="columns"
 *     :rows="items"
 *     :meta="paginationMeta"
 *     :loading="isLoading"
 *     :selectable="true"
 *     @sort="onSort"
 *     @page-change="onPageChange"
 *     @selection-change="onSelectionChange"
 *   >
 *     <template #cell-name="{ row }">{{ row.name }}</template>
 *     <template #cell-status="{ row }">
 *       <AdminStatusBadge :status="row.status" />
 *     </template>
 *     <template #actions="{ row }">
 *       <button @click="edit(row)">Edit</button>
 *     </template>
 *   </AdminDataTable>
 */

import { ref, computed, watch } from "vue";
import type { PaginationMeta } from "@/lib/admin";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ColumnDef {
  /** Unique key matching a property on the row object */
  key: string;
  /** Display label in the table header */
  label: string;
  /** Whether this column is sortable (emits @sort) */
  sortable?: boolean;
  /** Default sort direction when first clicked */
  defaultSort?: "asc" | "desc";
  /** Column width hint — any CSS width value */
  width?: string;
  /** Text alignment for cell content */
  align?: "left" | "center" | "right";
  /** Hide this column on small screens */
  hideOnMobile?: boolean;
}

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    /** Column definitions */
    columns: ColumnDef[];
    /** Row data — each object should have properties matching column keys */
    rows: Record<string, unknown>[];
    /** Pagination metadata from the API */
    meta?: PaginationMeta | null;
    /** Whether the table is loading data */
    loading?: boolean;
    /** Whether to show checkboxes for bulk selection */
    selectable?: boolean;
    /** Currently selected row IDs */
    selectedIds?: (string | number)[];
    /** Unique key property on each row (for selection tracking) */
    rowKey?: string;
    /** Whether rows are clickable (emits @row-click) */
    clickable?: boolean;
    /** Empty state message */
    emptyMessage?: string;
    /** Empty state description */
    emptyDescription?: string;
  }>(),
  {
    loading: false,
    selectable: false,
    selectedIds: () => [],
    rowKey: "id",
    clickable: false,
    emptyMessage: "No items found",
    emptyDescription: "",
    meta: null,
  },
);

const emit = defineEmits<{
  sort: [{ key: string; direction: "asc" | "desc" }];
  "page-change": [page: number];
  "selection-change": [ids: (string | number)[]];
  "row-click": [row: Record<string, unknown>];
}>();

// ─── Sort State ──────────────────────────────────────────────────────────────

const sortKey = ref<string | null>(null);
const sortDirection = ref<"asc" | "desc">("asc");

function handleSort(column: ColumnDef) {
  if (!column.sortable) return;

  if (sortKey.value === column.key) {
    // Toggle direction
    sortDirection.value = sortDirection.value === "asc" ? "desc" : "asc";
  } else {
    sortKey.value = column.key;
    sortDirection.value = column.defaultSort || "asc";
  }

  emit("sort", { key: sortKey.value, direction: sortDirection.value });
}

function getSortIcon(column: ColumnDef): "none" | "asc" | "desc" {
  if (!column.sortable || sortKey.value !== column.key) return "none";
  return sortDirection.value;
}

// ─── Selection ───────────────────────────────────────────────────────────────

const allSelected = computed(() => {
  if (props.rows.length === 0) return false;
  return props.rows.every((row) =>
    props.selectedIds.includes(row[props.rowKey] as string | number),
  );
});

const someSelected = computed(
  () => !allSelected.value && props.selectedIds.length > 0,
);

function toggleSelectAll() {
  if (allSelected.value) {
    emit("selection-change", []);
  } else {
    const ids = props.rows.map((row) => row[props.rowKey] as string | number);
    emit("selection-change", ids);
  }
}

function toggleRow(row: Record<string, unknown>) {
  const rowId = row[props.rowKey] as string | number;
  const current = [...props.selectedIds];
  const idx = current.indexOf(rowId);

  if (idx >= 0) {
    current.splice(idx, 1);
  } else {
    current.push(rowId);
  }

  emit("selection-change", current);
}

function isRowSelected(row: Record<string, unknown>): boolean {
  return props.selectedIds.includes(row[props.rowKey] as string | number);
}

// ─── Pagination ──────────────────────────────────────────────────────────────

function goToPage(page: number) {
  if (!props.meta) return;
  if (page < 1 || page > props.meta.total_pages) return;
  emit("page-change", page);
}

// ─── Alignment helper ────────────────────────────────────────────────────────

function alignClass(align?: string): string {
  switch (align) {
    case "center":
      return "text-center";
    case "right":
      return "text-right";
    default:
      return "text-left";
  }
}
</script>

<template>
  <div class="w-full">
    <!-- Loading Skeleton -->
    <div v-if="loading && rows.length === 0" class="space-y-3">
      <div class="card animate-pulse overflow-hidden">
        <!-- Skeleton header -->
        <div class="border-b border-border px-4 py-3">
          <div class="flex items-center gap-4">
            <div v-if="selectable" class="h-4 w-4 rounded skeleton" />
            <div
              v-for="col in columns"
              :key="col.key"
              class="h-4 rounded skeleton"
              :style="{ width: col.width || '100px' }"
            />
          </div>
        </div>
        <!-- Skeleton rows -->
        <div v-for="i in 5" :key="i" class="border-b border-border px-4 py-3">
          <div class="flex items-center gap-4">
            <div v-if="selectable" class="h-4 w-4 rounded skeleton" />
            <div
              v-for="col in columns"
              :key="col.key"
              class="h-4 rounded skeleton"
              :style="{ width: col.width || '100px' }"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Data Table -->
    <div v-else class="card overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-border bg-muted/50">
              <!-- Select All Checkbox -->
              <th
                v-if="selectable"
                class="w-10 px-4 py-3"
                scope="col"
              >
                <input
                  type="checkbox"
                  :checked="allSelected"
                  :indeterminate="someSelected"
                  class="h-4 w-4 rounded border-input text-primary focus:ring-ring"
                  @change="toggleSelectAll"
                />
              </th>

              <!-- Column Headers -->
              <th
                v-for="col in columns"
                :key="col.key"
                :scope="col.key === 'actions' ? undefined : 'col'"
                class="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                :class="[
                  alignClass(col.align),
                  { 'cursor-pointer select-none hover:text-foreground': col.sortable },
                  { 'hidden sm:table-cell': col.hideOnMobile },
                ]"
                :style="col.width ? { width: col.width } : {}"
                @click="handleSort(col)"
              >
                <div class="flex items-center gap-1" :class="col.align === 'right' ? 'justify-end' : col.align === 'center' ? 'justify-center' : ''">
                  <span>{{ col.label }}</span>
                  <!-- Sort Icons -->
                  <span v-if="col.sortable" class="inline-flex flex-col ml-0.5">
                    <!-- Ascending arrow -->
                    <svg
                      class="h-2.5 w-2.5 -mb-0.5"
                      :class="getSortIcon(col) === 'asc' ? 'text-foreground' : 'text-muted-foreground/40'"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path d="M10 4l6 6H4l6-6z" />
                    </svg>
                    <!-- Descending arrow -->
                    <svg
                      class="h-2.5 w-2.5 -mt-0.5"
                      :class="getSortIcon(col) === 'desc' ? 'text-foreground' : 'text-muted-foreground/40'"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path d="M10 16l-6-6h12l-6 6z" />
                    </svg>
                  </span>
                </div>
              </th>
            </tr>
          </thead>

          <tbody class="divide-y divide-border">
            <!-- Rows -->
            <tr
              v-for="(row, rowIndex) in rows"
              :key="row[rowKey] as string || rowIndex"
              class="transition-colors hover:bg-muted/30"
              :class="{
                'bg-brand-50/50 dark:bg-brand-950/20': isRowSelected(row),
                'cursor-pointer': clickable,
              }"
              @click="clickable && emit('row-click', row)"
            >
              <!-- Row Checkbox -->
              <td v-if="selectable" class="w-10 px-4 py-3" @click.stop>
                <input
                  type="checkbox"
                  :checked="isRowSelected(row)"
                  class="h-4 w-4 rounded border-input text-primary focus:ring-ring"
                  @change="toggleRow(row)"
                />
              </td>

              <!-- Data Cells -->
              <td
                v-for="col in columns"
                :key="col.key"
                class="px-4 py-3"
                :class="[
                  alignClass(col.align),
                  { 'hidden sm:table-cell': col.hideOnMobile },
                  { 'font-medium text-foreground': col.key === columns[0]?.key },
                ]"
              >
                <!-- Named slot for custom cell rendering -->
                <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                  {{ col.key === 'actions' ? '' : (row[col.key] ?? '—') }}
                </slot>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Empty State -->
      <div
        v-if="!loading && rows.length === 0"
        class="flex flex-col items-center gap-3 p-10 text-center"
      >
        <svg
          class="h-10 w-10 text-muted-foreground/30"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="1.5"
            d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
          />
        </svg>
        <div>
          <p class="font-medium text-foreground">{{ emptyMessage }}</p>
          <p v-if="emptyDescription" class="mt-1 text-sm text-muted-foreground">
            {{ emptyDescription }}
          </p>
        </div>
        <slot name="empty-action" />
      </div>

      <!-- Pagination -->
      <div
        v-if="meta && meta.total_pages > 1 && rows.length > 0"
        class="flex items-center justify-between border-t border-border px-4 py-3"
      >
        <p class="text-xs text-muted-foreground">
          {{ meta.total_items }} item{{ meta.total_items !== 1 ? 's' : '' }}
          &middot;
          Page {{ meta.current_page }} of {{ meta.total_pages }}
        </p>
        <div class="flex items-center gap-1">
          <button
            type="button"
            class="btn-ghost px-3 py-1.5 text-xs"
            :disabled="!meta.has_previous || loading"
            @click="goToPage(meta.current_page - 1)"
          >
            <svg class="h-3.5 w-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
            </svg>
            Previous
          </button>
          <button
            type="button"
            class="btn-ghost px-3 py-1.5 text-xs"
            :disabled="!meta.has_next || loading"
            @click="goToPage(meta.current_page + 1)"
          >
            Next
            <svg class="h-3.5 w-3.5 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
