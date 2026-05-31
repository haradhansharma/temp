<script setup lang="ts">
/**
 * AdminEmptyState — Empty state placeholder for admin pages.
 *
 * Features:
 *   - Icon, title, description
 *   - Optional CTA button slot
 *
 * Usage:
 *   <AdminEmptyState
 *     title="No products yet"
 *     description="Create your first product to get started."
 *     icon="box"
 *   >
 *     <template #action>
 *       <button class="btn-primary">New Product</button>
 *     </template>
 *   </AdminEmptyState>
 */

// ─── Props ───────────────────────────────────────────────────────────────────

withDefaults(
  defineProps<{
    /** Empty state title */
    title: string;
    /** Description text */
    description?: string;
    /** Icon variant */
    icon?: "box" | "key" | "users" | "document" | "clipboard" | "webhook" | "search" | "generic";
  }>(),
  {
    description: "",
    icon: "generic",
  },
);
</script>

<template>
  <div class="card flex flex-col items-center gap-4 p-10 text-center">
    <!-- Box icon (products) -->
    <svg
      v-if="icon === 'box'"
      class="h-12 w-12 text-muted-foreground/30"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
    </svg>
    <!-- Key icon (API keys) -->
    <svg
      v-else-if="icon === 'key'"
      class="h-12 w-12 text-muted-foreground/30"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
    </svg>
    <!-- Users icon -->
    <svg
      v-else-if="icon === 'users'"
      class="h-12 w-12 text-muted-foreground/30"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
    <!-- Document icon (audit log) -->
    <svg
      v-else-if="icon === 'document'"
      class="h-12 w-12 text-muted-foreground/30"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
    <!-- Clipboard icon (subscriptions) -->
    <svg
      v-else-if="icon === 'clipboard'"
      class="h-12 w-12 text-muted-foreground/30"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
    <!-- Webhook icon -->
    <svg
      v-else-if="icon === 'webhook'"
      class="h-12 w-12 text-muted-foreground/30"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
    </svg>
    <!-- Search icon (no results) -->
    <svg
      v-else-if="icon === 'search'"
      class="h-12 w-12 text-muted-foreground/30"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
    <!-- Generic icon (default) -->
    <svg
      v-else
      class="h-12 w-12 text-muted-foreground/30"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
    </svg>

    <div>
      <p class="font-medium text-foreground">{{ title }}</p>
      <p v-if="description" class="mt-1 text-sm text-muted-foreground">
        {{ description }}
      </p>
    </div>

    <!-- CTA button slot -->
    <slot name="action" />
  </div>
</template>
