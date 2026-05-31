<script setup lang="ts">
/**
 * AdminPageHeader — Consistent page header for admin pages.
 *
 * Features:
 *   - Page title
 *   - Breadcrumb trail (auto-generated from route or manual)
 *   - Primary and secondary action buttons via slots
 *
 * Usage:
 *   <AdminPageHeader
 *     title="Products"
 *     description="Manage products, plans, and access entries."
 *     :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Products' }]"
 *   >
 *     <template #primary-action>
 *       <button class="btn-primary">New Product</button>
 *     </template>
 *     <template #secondary-action>
 *       <button class="btn-secondary">Export</button>
 *     </template>
 *   </AdminPageHeader>
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export interface BreadcrumbItem {
  /** Display text */
  label: string;
  /** Optional link (if absent, rendered as plain text) */
  href?: string;
}

// ─── Props ───────────────────────────────────────────────────────────────────

withDefaults(
  defineProps<{
    /** Page title */
    title: string;
    /** Optional description below the title */
    description?: string;
    /** Breadcrumb items — last item is the current page */
    breadcrumbs?: BreadcrumbItem[];
  }>(),
  {
    description: "",
    breadcrumbs: () => [],
  },
);
</script>

<template>
  <div class="mb-6">
    <!-- Breadcrumbs -->
    <nav
      v-if="breadcrumbs.length > 0"
      class="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground"
      aria-label="Breadcrumb"
    >
      <template v-for="(crumb, index) in breadcrumbs" :key="index">
        <!-- Separator -->
        <svg
          v-if="index > 0"
          class="h-3 w-3 text-muted-foreground/50"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
        <!-- Link or text -->
        <a
          v-if="crumb.href && index < breadcrumbs.length - 1"
          :href="crumb.href"
          class="transition-colors hover:text-foreground"
        >
          {{ crumb.label }}
        </a>
        <span
          v-else
          :class="index === breadcrumbs.length - 1 ? 'text-foreground font-medium' : ''"
        >
          {{ crumb.label }}
        </span>
      </template>
    </nav>

    <!-- Title row -->
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <h1 class="text-2xl font-bold text-foreground">{{ title }}</h1>
        <p v-if="description" class="mt-1 text-sm text-muted-foreground">
          {{ description }}
        </p>
      </div>

      <!-- Action buttons -->
      <div v-if="$slots['primary-action'] || $slots['secondary-action']" class="flex items-center gap-2 shrink-0">
        <slot name="secondary-action" />
        <slot name="primary-action" />
      </div>
    </div>
  </div>
</template>
