<script setup lang="ts">
// SearchableSelect — Reusable Vue dropdown with search/filter
// Used for timezone, currency, and language selection in profile settings

import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from "vue";

export interface SelectOption {
  value: string;
  label: string;
  group?: string;
  secondary?: string; // e.g. "USD" for "US Dollar (USD)"
}

const props = withDefaults(defineProps<{
  modelValue: string;
  options: SelectOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  noResultsText?: string;
  disabled?: boolean;
  id?: string;
  label?: string;
}>(), {
  placeholder: "Select an option...",
  searchPlaceholder: "Search...",
  noResultsText: "No results found",
  disabled: false,
});

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const isOpen = ref(false);
const searchQuery = ref("");
const containerRef = ref<HTMLElement | null>(null);
const searchInputRef = ref<HTMLInputElement | null>(null);

// Current display value
const selectedOption = computed(() =>
  props.options.find((o) => o.value === props.modelValue)
);

const displayValue = computed(() =>
  selectedOption.value
    ? props.label
      ? `${props.label}: ${selectedOption.value.label}`
      : selectedOption.value.label
    : props.placeholder
);

// Filtered options based on search
const filteredOptions = computed(() => {
  if (!searchQuery.value.trim()) return props.options;
  const q = searchQuery.value.toLowerCase().trim();
  return props.options.filter(
    (o) =>
      o.label.toLowerCase().includes(q) ||
      o.value.toLowerCase().includes(q) ||
      (o.secondary && o.secondary.toLowerCase().includes(q)) ||
      (o.group && o.group.toLowerCase().includes(q))
  );
});

// Group options
const groupedOptions = computed(() => {
  const groups = new Map<string, SelectOption[]>();
  for (const option of filteredOptions.value) {
    const group = option.group || "";
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group)!.push(option);
  }
  return groups;
});

function toggleDropdown() {
  if (props.disabled) return;
  isOpen.value = !isOpen.value;
  if (isOpen.value) {
    searchQuery.value = "";
    nextTick(() => {
      searchInputRef.value?.focus();
    });
  }
}

function closeDropdown() {
  isOpen.value = false;
  searchQuery.value = "";
}

function selectOption(option: SelectOption) {
  emit("update:modelValue", option.value);
  closeDropdown();
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    closeDropdown();
  }
}

// Click outside to close
function handleClickOutside(event: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
    closeDropdown();
  }
}

onMounted(() => {
  document.addEventListener("click", handleClickOutside);
  document.addEventListener("keydown", handleKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("click", handleClickOutside);
  document.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
  <div ref="containerRef" class="relative" :class="{ 'opacity-50 pointer-events-none': disabled }">
    <!-- Trigger Button -->
    <button
      type="button"
      :id="id"
      class="input-field flex items-center justify-between gap-2 text-left cursor-pointer"
      :class="{ 'ring-2 ring-ring ring-offset-1': isOpen }"
      @click="toggleDropdown"
      :aria-expanded="isOpen"
      :aria-haspopup="true"
      :disabled="disabled"
    >
      <span
        :class="selectedOption ? 'text-foreground' : 'text-muted-foreground'"
        class="truncate"
      >
        {{ displayValue }}
      </span>
      <svg
        class="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200"
        :class="{ 'rotate-180': isOpen }"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <!-- Dropdown Panel -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1 scale-[0.98]"
      enter-to-class="opacity-100 translate-y-0 scale-100"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 translate-y-0 scale-100"
      leave-to-class="opacity-0 -translate-y-1 scale-[0.98]"
    >
      <div
        v-if="isOpen"
        class="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg"
        style="min-width: 16rem;"
      >
        <!-- Search Input -->
        <div class="border-b border-border p-2">
          <div class="relative">
            <svg class="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              ref="searchInputRef"
              v-model="searchQuery"
              type="text"
              :placeholder="searchPlaceholder"
              class="h-8 w-full rounded-md border border-input bg-transparent pl-8 pr-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>
        </div>

        <!-- Options List -->
        <div class="max-h-56 overflow-y-auto p-1" role="listbox">
          <!-- No results -->
          <div v-if="filteredOptions.length === 0" class="px-3 py-6 text-center text-sm text-muted-foreground">
            {{ noResultsText }}
          </div>

          <!-- Grouped options -->
          <template v-for="([group, options], groupIndex) in groupedOptions" :key="group">
            <!-- Group header -->
            <div
              v-if="group"
              class="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
              :class="{ 'mt-1 pt-1 border-t border-border': groupIndex > 0 }"
            >
              {{ group }}
            </div>

            <!-- Options -->
            <button
              v-for="option in options"
              :key="option.value"
              type="button"
              role="option"
              class="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-left transition-colors"
              :class="option.value === modelValue
                ? 'bg-brand-50 text-brand-700 font-medium dark:bg-brand-950 dark:text-brand-300'
                : 'text-foreground hover:bg-accent'"
              @click="selectOption(option)"
            >
              <!-- Check icon for selected -->
              <svg
                v-if="option.value === modelValue"
                class="h-3.5 w-3.5 shrink-0 text-brand-600 dark:text-brand-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
              <span v-else class="w-3.5 shrink-0" />
              <span class="flex-1 truncate">{{ option.label }}</span>
              <span v-if="option.secondary && option.value !== modelValue" class="shrink-0 text-xs text-muted-foreground">
                {{ option.secondary }}
              </span>
            </button>
          </template>
        </div>
      </div>
    </Transition>
  </div>
</template>
