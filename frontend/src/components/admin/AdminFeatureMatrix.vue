<script setup lang="ts">
/**
 * AdminFeatureMatrix — Interactive feature comparison table for product plans.
 *
 * Renders a matrix with:
 *   - Access keys as rows (with edit/delete actions)
 *   - Plans as columns
 *   - Clickable cells for quick value editing
 *
 * Emits events for CRUD operations; parent handles API calls.
 */

import type { AccessMatrixRow } from "@/lib/admin";

// ─── Props ───────────────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    /** Plan columns */
    plans: { slug: string; name: string; is_active?: boolean }[];
    /** Matrix row data */
    rows: AccessMatrixRow[];
    /** Product name for the header */
    productName?: string;
    /** Whether data is loading */
    loading?: boolean;
    /** Whether CRUD actions are enabled */
    editable?: boolean;
  }>(),
  {
    productName: "",
    loading: false,
    editable: false,
  },
);

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  /** User clicked a cell to edit the value for a specific plan+key */
  (e: "edit-cell", row: AccessMatrixRow, planSlug: string): void;
  /** User clicked "add entry" button */
  (e: "add-entry"): void;
  /** User clicked edit (pencil) on a row — edit key/description */
  (e: "edit-row", row: AccessMatrixRow): void;
  /** User clicked delete on a row — delete the key across all plans */
  (e: "delete-row", row: AccessMatrixRow): void;
}>();

// ─── Cell value rendering ────────────────────────────────────────────────────

function getCellValue(row: AccessMatrixRow, planSlug: string): string | null {
  return row.values[planSlug] ?? null;
}

function isCheckmark(value: string | null): boolean {
  if (value === null) return false;
  const lower = String(value).toLowerCase();
  return lower === "true" || lower === "1";
}

function isFalsy(value: string | null): boolean {
  if (value === null) return true;
  const lower = String(value).toLowerCase();
  return lower === "false" || lower === "0" || lower === "";
}

function formatCellValue(value: string | null): string {
  if (value === null) return "—";
  const lower = String(value).toLowerCase();
  if (lower === "true") return "Yes";
  if (lower === "false") return "No";
  return String(value);
}

/** Whether this cell has a value set (not null/undefined) */
function hasValue(row: AccessMatrixRow, planSlug: string): boolean {
  const v = row.values[planSlug];
  return v !== null && v !== undefined;
}
</script>

<template>
  <div class="w-full">
    <!-- Loading skeleton -->
    <div v-if="loading" class="card animate-pulse overflow-hidden">
      <div class="border-b border-border px-4 py-3">
        <div class="h-4 w-40 rounded skeleton" />
      </div>
      <div v-for="i in 5" :key="i" class="border-b border-border px-4 py-3">
        <div class="flex items-center gap-4">
          <div class="h-4 w-32 rounded skeleton" />
          <div v-for="j in plans.length" :key="j" class="h-4 w-12 rounded skeleton" />
        </div>
      </div>
    </div>

    <!-- Matrix table -->
    <div v-else-if="rows && rows.length > 0" class="card overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-border bg-muted/50">
              <th
                class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                scope="col"
                :style="editable ? 'min-width: 200px' : ''"
              >
                Feature
              </th>
              <th
                v-for="plan in plans"
                :key="plan.slug"
                class="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                scope="col"
              >
                <div class="flex flex-col items-center gap-0.5">
                  <span>{{ plan.name }}</span>
                  <span
                    v-if="plan.is_active === false"
                    class="text-[10px] font-normal text-muted-foreground/60"
                  >
                    inactive
                  </span>
                </div>
              </th>
              <th
                v-if="editable"
                class="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                scope="col"
                style="width: 80px"
              >
                Actions
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            <tr
              v-for="row in rows"
              :key="row.key"
              class="group hover:bg-muted/30 transition-colors"
            >
              <!-- Feature key + description -->
              <td class="px-4 py-3">
                <div>
                  <p class="font-medium text-foreground text-sm">{{ row.key }}</p>
                  <p v-if="row.description" class="text-xs text-muted-foreground mt-0.5">
                    {{ row.description }}
                  </p>
                </div>
              </td>

              <!-- Plan value cells -->
              <td
                v-for="plan in plans"
                :key="plan.slug"
                class="px-4 py-3 text-center"
                :class="editable ? 'cursor-pointer hover:bg-muted/50 transition-colors relative' : ''"
                @click="editable && emit('edit-cell', row, plan.slug)"
              >
                <!-- Has value indicator dot for editable mode -->
                <div v-if="editable && hasValue(row, plan.slug)" class="absolute top-1.5 right-1.5">
                  <span class="block h-1.5 w-1.5 rounded-full bg-green-500 dark:bg-green-400" />
                </div>

                <!-- Boolean true → checkmark -->
                <svg
                  v-if="isCheckmark(getCellValue(row, plan.slug))"
                  class="mx-auto h-5 w-5 text-green-600 dark:text-green-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                <!-- Falsy/empty → dash -->
                <span
                  v-else-if="isFalsy(getCellValue(row, plan.slug))"
                  class="text-muted-foreground/40"
                >
                  &mdash;
                </span>
                <!-- Integer/string value -->
                <span v-else class="font-medium text-foreground">
                  {{ formatCellValue(getCellValue(row, plan.slug)) }}
                </span>
              </td>

              <!-- Row actions (editable mode only) -->
              <td v-if="editable" class="px-3 py-3 text-right" @click.stop>
                <div class="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    type="button"
                    class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    title="Edit feature"
                    @click="emit('edit-row', row)"
                  >
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950 dark:hover:text-red-400"
                    title="Delete feature"
                    @click="emit('delete-row', row)"
                  >
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="card flex flex-col items-center gap-3 p-10 text-center">
      <svg
        class="h-10 w-10 text-muted-foreground/30"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
      </svg>
      <p class="font-medium text-foreground">No access entries</p>
      <p class="text-sm text-muted-foreground">
        Add access entries to plans to see the feature matrix.
      </p>
      <button
        v-if="editable"
        type="button"
        class="btn-primary inline-flex items-center gap-2 text-sm mt-2"
        @click="emit('add-entry')"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Add Feature
      </button>
    </div>
  </div>
</template>
