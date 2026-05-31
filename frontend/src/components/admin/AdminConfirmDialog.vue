<script setup lang="ts">
/**
 * AdminConfirmDialog — Confirmation modal for admin actions.
 *
 * Features:
 *   - Title, message, and optional detail text
 *   - Confirm/Cancel buttons with loading state
 *   - Destructive variant (red confirm button)
 *   - Escape key and backdrop click to close
 *   - Accessible: role="dialog", aria-modal, aria-label
 *
 * Usage:
 *   <AdminConfirmDialog
 *     v-model:open="showDeleteDialog"
 *     title="Delete Product"
 *     message="Are you sure you want to delete this product?"
 *     detail="This action cannot be undone. All plans and access entries will be removed."
 *     confirm-label="Delete"
 *     :destructive="true"
 *     :loading="isDeleting"
 *     @confirm="handleDelete"
 *     @cancel="showDeleteDialog = false"
 *   />
 */

import { watch, onMounted, onUnmounted } from "vue";

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    /** Whether the dialog is visible */
    open: boolean;
    /** Dialog title */
    title: string;
    /** Main message */
    message: string;
    /** Additional detail text (shown in a muted box) */
    detail?: string;
    /** Confirm button label */
    confirmLabel?: string;
    /** Cancel button label */
    cancelLabel?: string;
    /** Use destructive (red) variant for confirm button */
    destructive?: boolean;
    /** Show loading spinner on confirm button */
    loading?: boolean;
  }>(),
  {
    detail: "",
    confirmLabel: "Confirm",
    cancelLabel: "Cancel",
    destructive: false,
    loading: false,
  },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  confirm: [];
  cancel: [];
}>();

// ─── Close handlers ──────────────────────────────────────────────────────────

function close() {
  if (props.loading) return;
  emit("update:open", false);
  emit("cancel");
}

function handleConfirm() {
  emit("confirm");
}

function handleBackdropClick() {
  close();
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && props.open) {
    close();
  }
}

// Register/unregister Escape key handler when dialog opens
watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeydown);
      // Prevent body scroll when dialog is open
      document.body.style.overflow = "hidden";
    } else {
      document.removeEventListener("keydown", handleKeydown);
      document.body.style.overflow = "";
    }
  },
);

onMounted(() => {
  if (props.open) {
    document.addEventListener("keydown", handleKeydown);
    document.body.style.overflow = "hidden";
  }
});

onUnmounted(() => {
  document.removeEventListener("keydown", handleKeydown);
  document.body.style.overflow = "";
});
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
    >
      <!-- Backdrop -->
      <div
        class="fixed inset-0 bg-black/60 backdrop-blur-sm"
        @click="handleBackdropClick"
      />

      <!-- Panel -->
      <div class="relative z-10 w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl animate-scale-in">
        <!-- Icon + Title -->
        <div class="flex items-start gap-4 mb-4">
          <!-- Warning icon -->
          <div
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
            :class="destructive
              ? 'bg-red-100 dark:bg-red-950'
              : 'bg-amber-100 dark:bg-amber-950'"
          >
            <svg
              v-if="destructive"
              class="h-5 w-5 text-red-600 dark:text-red-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <svg
              v-else
              class="h-5 w-5 text-amber-600 dark:text-amber-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>

          <div class="min-w-0 flex-1">
            <h3 class="text-base font-semibold text-foreground">{{ title }}</h3>
            <p class="mt-1 text-sm text-muted-foreground">{{ message }}</p>
          </div>
        </div>

        <!-- Detail box -->
        <div
          v-if="detail"
          class="mb-4 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground border border-border"
        >
          {{ detail }}
        </div>

        <!-- Actions -->
        <div class="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            class="btn-ghost px-4 py-2.5 text-sm"
            :disabled="loading"
            @click="close"
          >
            {{ cancelLabel }}
          </button>
          <button
            type="button"
            :class="destructive ? 'btn-destructive' : 'btn-primary'"
            class="px-4 py-2.5 text-sm"
            :disabled="loading"
            @click="handleConfirm"
          >
            <!-- Loading spinner -->
            <svg
              v-if="loading"
              class="h-4 w-4 animate-spin"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
