<script setup lang="ts">
/**
 * AdminStatusBadge — Colored status badge for admin data.
 *
 * Supports predefined status types (subscription, refund, webhook) and
 * custom status definitions. Uses the color helpers from lib/admin.ts.
 *
 * Usage:
 *   <AdminStatusBadge type="subscription" status="active" />
 *   <AdminStatusBadge type="refund" status="pending" />
 *   <AdminStatusBadge type="webhook" status="failed" />
 *   <AdminStatusBadge status="live" color="green" />
 */

import { computed } from "vue";
import {
  getSubscriptionStatusColor,
  getRefundStatusColor,
  getWebhookStatusColor,
} from "@/lib/admin";

// ─── Props ───────────────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    /** Status value to display */
    status: string;
    /** Predefined status type for automatic color mapping */
    type?: "subscription" | "refund" | "webhook" | "generic" | "active-inactive" | "custom";
    /** Custom color (overrides type-based color) — one of: green, red, amber, blue, orange, gray, purple, sky */
    color?: string;
    /** Whether to show a dot indicator before the text */
    dot?: boolean;
  }>(),
  {
    type: "generic",
    color: "",
    dot: true,
  },
);

// ─── Color mapping ───────────────────────────────────────────────────────────

const colorMap: Record<string, { bg: string; text: string; dot: string }> = {
  green: {
    bg: "bg-green-100 dark:bg-green-950",
    text: "text-green-700 dark:text-green-400",
    dot: "bg-green-500",
  },
  red: {
    bg: "bg-red-100 dark:bg-red-950",
    text: "text-red-700 dark:text-red-400",
    dot: "bg-red-500",
  },
  amber: {
    bg: "bg-amber-100 dark:bg-amber-950",
    text: "text-amber-700 dark:text-amber-400",
    dot: "bg-amber-500",
  },
  blue: {
    bg: "bg-blue-100 dark:bg-blue-950",
    text: "text-blue-700 dark:text-blue-400",
    dot: "bg-blue-500",
  },
  orange: {
    bg: "bg-orange-100 dark:bg-orange-950",
    text: "text-orange-700 dark:text-orange-400",
    dot: "bg-orange-500",
  },
  gray: {
    bg: "bg-gray-100 dark:bg-gray-900",
    text: "text-gray-600 dark:text-gray-400",
    dot: "bg-gray-500",
  },
  purple: {
    bg: "bg-purple-100 dark:bg-purple-950",
    text: "text-purple-700 dark:text-purple-400",
    dot: "bg-purple-500",
  },
  sky: {
    bg: "bg-sky-100 dark:bg-sky-950",
    text: "text-sky-700 dark:text-sky-400",
    dot: "bg-sky-500",
  },
};

// ─── Computed colors ─────────────────────────────────────────────────────────

const badgeColors = computed(() => {
  // Custom color takes precedence
  if (props.color && colorMap[props.color]) {
    return colorMap[props.color];
  }

  // Type-based color mapping
  switch (props.type) {
    case "subscription": {
      const c = getSubscriptionStatusColor(props.status);
      // Derive dot color from bg class
      const dotColor = props.status === "active"
        ? "bg-green-500"
        : props.status === "trialing"
          ? "bg-blue-500"
          : props.status === "past_due"
            ? "bg-amber-500"
            : props.status === "canceled"
              ? "bg-gray-500"
              : props.status === "expired"
                ? "bg-red-500"
                : props.status === "paused"
                  ? "bg-orange-500"
                  : "bg-gray-500";
      return { bg: c.bg, text: c.text, dot: dotColor };
    }
    case "refund": {
      const c = getRefundStatusColor(props.status);
      const dotColor = props.status === "pending"
        ? "bg-amber-500"
        : props.status === "completed" || props.status === "processed"
          ? "bg-green-500"
          : props.status === "approved"
            ? "bg-blue-500"
            : props.status === "rejected" || props.status === "failed"
              ? "bg-red-500"
              : "bg-gray-500";
      return { bg: c.bg, text: c.text, dot: dotColor };
    }
    case "webhook": {
      const c = getWebhookStatusColor(props.status);
      const dotColor = props.status === "processed"
        ? "bg-green-500"
        : props.status === "pending"
          ? "bg-amber-500"
          : props.status === "failed"
            ? "bg-red-500"
            : "bg-gray-500";
      return { bg: c.bg, text: c.text, dot: dotColor };
    }
    case "active-inactive": {
      const isActive = props.status === "active" || props.status === "true" || props.status === "1";
      return isActive
        ? colorMap.green
        : colorMap.gray;
    }
    default: {
      // Generic: try to infer from common status values
      const s = props.status.toLowerCase();
      if (s === "active" || s === "live" || s === "success" || s === "ok" || s === "healthy" || s === "verified" || s === "enabled") {
        return colorMap.green;
      }
      if (s === "inactive" || s === "disabled" || s === "unverified" || s === "off") {
        return colorMap.gray;
      }
      if (s === "pending" || s === "warning" || s === "queued" || s === "draft") {
        return colorMap.amber;
      }
      if (s === "failed" || s === "error" || s === "rejected" || s === "revoked" || s === "deleted" || s === "expired" || s === "canceled") {
        return colorMap.red;
      }
      if (s === "trialing" || s === "info" || s === "new") {
        return colorMap.blue;
      }
      if (s === "paused" || s === "suspended") {
        return colorMap.orange;
      }
      return colorMap.gray;
    }
  }
});

// ─── Display text ────────────────────────────────────────────────────────────

const displayStatus = computed(() => {
  return props.status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
});
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
    :class="[badgeColors.bg, badgeColors.text]"
  >
    <!-- Dot indicator -->
    <span
      v-if="dot"
      class="h-1.5 w-1.5 rounded-full"
      :class="badgeColors.dot"
    />
    {{ displayStatus }}
  </span>
</template>
