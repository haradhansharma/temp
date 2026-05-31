<script setup lang="ts">
/**
 * AdminAuditTimeline — Chronological event timeline for audit logs.
 *
 * Features:
 *   - Chronological list of events with icon, description, timestamp
 *   - Admin user name display
 *   - Expandable rows for request details
 *   - Loading skeleton
 *   - Empty state
 *
 * Usage:
 *   <AdminAuditTimeline
 *     :entries="auditEntries"
 *     :loading="isLoading"
 *   />
 */

import { ref } from "vue";
import { formatRelativeTime, formatDateTime } from "@/lib/admin";
import type { AuditLogEntry, UserAuditEntry } from "@/lib/admin";

// ─── Types ───────────────────────────────────────────────────────────────────

type TimelineEntry = AuditLogEntry | UserAuditEntry;

// ─── Props ───────────────────────────────────────────────────────────────────

withDefaults(
  defineProps<{
    /** Timeline entries (newest first) */
    entries: TimelineEntry[];
    /** Whether data is loading */
    loading?: boolean;
  }>(),
  {
    loading: false,
  },
);

// ─── Expanded rows ───────────────────────────────────────────────────────────

const expandedIds = ref<Set<number>>(new Set());

function toggleExpand(id: number) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id);
  } else {
    expandedIds.value.add(id);
  }
}

function getEntryId(entry: TimelineEntry, index: number): number {
  if (isAuditLogEntry(entry)) return entry.id;
  // UserAuditEntry doesn't have id — use index
  return index;
}

// ─── Entry type guards ───────────────────────────────────────────────────────

function isAuditLogEntry(entry: TimelineEntry): entry is AuditLogEntry {
  return "admin_email" in entry && "method" in entry && "path" in entry;
}

function isUserAuditEntry(entry: TimelineEntry): entry is UserAuditEntry {
  return "event_type" in entry && "description" in entry && "metadata" in entry;
}

function getEntryTimestamp(entry: TimelineEntry): string {
  if (isUserAuditEntry(entry)) return entry.timestamp || "";
  // AuditLogEntry uses created_at
  return (entry as AuditLogEntry).created_at || "";
}

// ─── Action icon ─────────────────────────────────────────────────────────────

function getActionIcon(entry: TimelineEntry): string {
  if (isAuditLogEntry(entry)) {
    const method = entry.method?.toUpperCase();
    if (method === "POST") return "create";
    if (method === "DELETE") return "delete";
    if (method === "PATCH" || method === "PUT") return "update";
    return "view";
  }
  // UserAuditEntry
  const eventType = (entry as UserAuditEntry).event_type?.toLowerCase() || "";
  const description = (entry as UserAuditEntry).description?.toLowerCase() || "";
  if (eventType === "login" || description.includes("login") || description.includes("auth")) return "auth";
  if (eventType === "refund" || description.includes("refund")) return "update";
  if (eventType === "plan_change" || description.includes("change") || description.includes("update")) return "update";
  if (eventType === "subscription_status" || description.includes("cancel") || description.includes("expire")) return "delete";
  return "view";
}

function getIconColors(iconType: string): { bg: string; text: string } {
  switch (iconType) {
    case "create":
      return { bg: "bg-green-100 dark:bg-green-950", text: "text-green-600 dark:text-green-400" };
    case "delete":
      return { bg: "bg-red-100 dark:bg-red-950", text: "text-red-600 dark:text-red-400" };
    case "update":
      return { bg: "bg-amber-100 dark:bg-amber-950", text: "text-amber-600 dark:text-amber-400" };
    case "auth":
      return { bg: "bg-blue-100 dark:bg-blue-950", text: "text-blue-600 dark:text-blue-400" };
    default:
      return { bg: "bg-gray-100 dark:bg-gray-900", text: "text-gray-600 dark:text-gray-400" };
  }
}
</script>

<template>
  <div class="w-full">
    <!-- Loading skeleton -->
    <div v-if="loading && entries.length === 0" class="space-y-4">
      <div v-for="i in 4" :key="i" class="flex gap-3 animate-pulse">
        <div class="flex flex-col items-center">
          <div class="h-8 w-8 rounded-full skeleton" />
          <div v-if="i < 4" class="w-px flex-1 bg-border my-1" />
        </div>
        <div class="flex-1 pb-4 space-y-2">
          <div class="h-4 w-48 rounded skeleton" />
          <div class="h-3 w-32 rounded skeleton" />
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="entries.length === 0"
      class="card flex flex-col items-center gap-3 p-10 text-center"
    >
      <svg
        class="h-10 w-10 text-muted-foreground/30"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <p class="font-medium text-foreground">No activity yet</p>
      <p class="text-sm text-muted-foreground">Audit events will appear here as admin actions occur.</p>
    </div>

    <!-- Timeline -->
    <div v-else class="relative">
      <div
        v-for="(entry, index) in entries"
        :key="index"
        class="flex gap-3"
      >
        <!-- Timeline connector -->
        <div class="flex flex-col items-center">
          <!-- Icon circle -->
          <div
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full z-10"
            :class="getIconColors(getActionIcon(entry)).bg"
          >
            <!-- Create icon -->
            <svg
              v-if="getActionIcon(entry) === 'create'"
              class="h-4 w-4"
              :class="getIconColors(getActionIcon(entry)).text"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            <!-- Delete icon -->
            <svg
              v-else-if="getActionIcon(entry) === 'delete'"
              class="h-4 w-4"
              :class="getIconColors(getActionIcon(entry)).text"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            <!-- Update icon -->
            <svg
              v-else-if="getActionIcon(entry) === 'update'"
              class="h-4 w-4"
              :class="getIconColors(getActionIcon(entry)).text"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <!-- Auth icon -->
            <svg
              v-else-if="getActionIcon(entry) === 'auth'"
              class="h-4 w-4"
              :class="getIconColors(getActionIcon(entry)).text"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            <!-- View icon (default) -->
            <svg
              v-else
              class="h-4 w-4"
              :class="getIconColors(getActionIcon(entry)).text"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          </div>

          <!-- Vertical line connector -->
          <div
            v-if="index < entries.length - 1"
            class="w-px flex-1 bg-border my-1"
          />
        </div>

        <!-- Content -->
        <div class="flex-1 pb-5 min-w-0">
          <!-- Primary info -->
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <!-- Action description -->
              <p class="text-sm font-medium text-foreground">
                <template v-if="isAuditLogEntry(entry)">
                  {{ entry.method }} {{ entry.path }}
                </template>
                <template v-else-if="isUserAuditEntry(entry)">
                  {{ entry.description }}
                </template>
              </p>
              <!-- User info -->
              <p class="text-xs text-muted-foreground mt-0.5">
                <template v-if="isAuditLogEntry(entry)">
                  {{ entry.admin_email }}
                  <span v-if="entry.ip_address" class="ml-1">&middot; {{ entry.ip_address }}</span>
                </template>
                <template v-else-if="isUserAuditEntry(entry)">
                  <span class="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase bg-muted text-muted-foreground">{{ entry.event_type }}</span>
                  <span v-if="entry.ip_address" class="ml-1">&middot; {{ entry.ip_address }}</span>
                </template>
              </p>
            </div>

            <!-- Timestamp -->
            <span
              class="shrink-0 text-xs text-muted-foreground"
              :title="formatDateTime(getEntryTimestamp(entry))"
            >
              {{ formatRelativeTime(getEntryTimestamp(entry)) }}
            </span>
          </div>

          <!-- Expandable request details (AuditLogEntry only) -->
          <template v-if="isAuditLogEntry(entry) && entry.details">
            <button
              type="button"
              class="mt-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
              @click="toggleExpand(getEntryId(entry, index))"
            >
              {{ expandedIds.has(getEntryId(entry, index)) ? 'Hide details' : 'Show details' }}
              <svg
                class="inline h-3 w-3 ml-0.5 transition-transform"
                :class="{ 'rotate-180': expandedIds.has(getEntryId(entry, index)) }"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            <div
              v-if="expandedIds.has(getEntryId(entry, index))"
              class="mt-2 rounded-lg bg-muted/50 border border-border p-3 text-xs font-mono text-muted-foreground overflow-x-auto"
            >
              <pre class="whitespace-pre-wrap break-words">{{ JSON.stringify(entry.details, null, 2) }}</pre>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
