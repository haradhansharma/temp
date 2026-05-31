<script setup lang="ts">
/**
 * AdminFilterBar — Search + filter bar for admin data tables.
 *
 * Features:
 *   - Search input with debounced emit
 *   - Dropdown filter selects
 *   - Date range picker (start/end)
 *   - Active filter count badge
 *   - Clear all button
 *
 * Usage:
 *   <AdminFilterBar
 *     :search="searchQuery"
 *     :filters="filterDefs"
 *     :active-count="3"
 *     @update:search="searchQuery = $event"
 *     @update:filter="onFilterChange"
 *     @clear="clearAllFilters"
 *   />
 */

import { ref, watch, computed } from "vue";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterDef {
  /** Unique key for this filter */
  key: string;
  /** Display label */
  label: string;
  /** Options for the dropdown */
  options: FilterOption[];
  /** Currently selected value (empty string = all) */
  value?: string;
  /** Placeholder text */
  placeholder?: string;
}

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    /** Current search query */
    search?: string;
    /** Filter definitions with their current values */
    filters?: FilterDef[];
    /** Number of active filters (search + dropdowns) */
    activeCount?: number;
    /** Search input placeholder */
    searchPlaceholder?: string;
    /** Whether to show the date range picker */
    showDateRange?: boolean;
    /** Start date value */
    dateFrom?: string;
    /** End date value */
    dateTo?: string;
  }>(),
  {
    search: "",
    filters: () => [],
    activeCount: 0,
    searchPlaceholder: "Search...",
    showDateRange: false,
    dateFrom: "",
    dateTo: "",
  },
);

const emit = defineEmits<{
  "update:search": [value: string];
  "update:filter": [{ key: string; value: string }];
  "update:dateFrom": [value: string];
  "update:dateTo": [value: string];
  clear: [];
}>();

// ─── Local state ─────────────────────────────────────────────────────────────

const localSearch = ref(props.search);

// Sync external search to local
watch(
  () => props.search,
  (val) => {
    localSearch.value = val;
  },
);

// Debounced search emit
let searchTimeout: ReturnType<typeof setTimeout>;
watch(localSearch, (val) => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    emit("update:search", val);
  }, 300);
});

// ─── Filter change ───────────────────────────────────────────────────────────

function onFilterChange(key: string, value: string) {
  emit("update:filter", { key, value });
}

function onClearAll() {
  localSearch.value = "";
  emit("clear");
}

const hasActiveFilters = computed(() => props.activeCount > 0);
</script>

<template>
  <div class="space-y-3">
    <!-- Top row: Search + primary filters -->
    <div class="flex flex-wrap items-center gap-2">
      <!-- Search input -->
      <div class="relative flex-1 min-w-[200px] max-w-sm">
        <svg
          class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          v-model="localSearch"
          type="text"
          :placeholder="searchPlaceholder"
          class="input-field pl-9 pr-3"
        />
      </div>

      <!-- Dropdown filters -->
      <template v-for="filter in filters" :key="filter.key">
        <select
          :value="filter.value || ''"
          class="input-field w-auto min-w-[140px] cursor-pointer appearance-none bg-[url('data:image/svg+xml;charset=UTF-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22%23737373%22%20stroke-width%3D%222%22%3E%3Cpath%20d%3D%22M6%209l6%206%206-6%22%2F%3E%3C%2Fsvg%3E')] bg-[position:right_10px_center] bg-no-repeat pr-8"
          @change="onFilterChange(filter.key, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">{{ filter.placeholder || `All ${filter.label}` }}</option>
          <option
            v-for="opt in filter.options"
            :key="opt.value"
            :value="opt.value"
          >
            {{ opt.label }}
          </option>
        </select>
      </template>

      <!-- Active filter badge + Clear all -->
      <div v-if="hasActiveFilters" class="flex items-center gap-2">
        <span class="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700 dark:bg-amber-950 dark:text-amber-400">
          {{ activeCount }} active
        </span>
        <button
          type="button"
          class="btn-ghost px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground"
          @click="onClearAll"
        >
          <svg class="h-3.5 w-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
          Clear
        </button>
      </div>
    </div>

    <!-- Date range row (if enabled) -->
    <div v-if="showDateRange" class="flex flex-wrap items-center gap-2">
      <span class="text-xs font-medium text-muted-foreground">Date range:</span>
      <input
        type="date"
        :value="dateFrom"
        class="input-field w-auto text-xs"
        @change="emit('update:dateFrom', ($event.target as HTMLInputElement).value)"
      />
      <span class="text-xs text-muted-foreground">to</span>
      <input
        type="date"
        :value="dateTo"
        class="input-field w-auto text-xs"
        @change="emit('update:dateTo', ($event.target as HTMLInputElement).value)"
      />
    </div>
  </div>
</template>
