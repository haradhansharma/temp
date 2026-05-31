<script setup lang="ts">
/**
 * AdminStatsCard — Metric card with label, value, change indicator, and optional sparkline.
 *
 * Usage:
 *   <AdminStatsCard
 *     label="Active Subscriptions"
 *     :value="1234"
 *     :change="5.2"
 *     prefix="$"
 *     icon="currency"
 *   />
 */

import { computed } from "vue";

// ─── Props ───────────────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    /** Card label (e.g. "MRR", "Active Subscriptions") */
    label: string;
    /** Numeric or string value to display */
    value: number | string;
    /** Percentage change (positive = green/up, negative = red/down) */
    change?: number | null;
    /** Currency or unit prefix (e.g. "$", "€") */
    prefix?: string;
    /** Unit suffix (e.g. "%", "users") */
    suffix?: string;
    /** Icon variant for the colored background */
    icon?: "currency" | "users" | "chart" | "activity" | "warning" | "info";
    /** Whether the card is in loading state */
    loading?: boolean;
    /** Sparkline data points (array of numbers) */
    sparkline?: number[];
  }>(),
  {
    change: null,
    prefix: "",
    suffix: "",
    icon: "info",
    loading: false,
    sparkline: () => [],
  },
);

// ─── Computed ────────────────────────────────────────────────────────────────

const formattedValue = computed(() => {
  if (typeof props.value === "string") return props.value;
  if (Number.isInteger(props.value)) {
    return props.value.toLocaleString();
  }
  return props.value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
});

const changeIsPositive = computed(() => props.change !== null && props.change >= 0);

const changeDisplay = computed(() => {
  if (props.change === null) return "";
  const sign = props.change >= 0 ? "+" : "";
  return `${sign}${props.change.toFixed(1)}%`;
});

// Icon color mapping
const iconColorMap: Record<string, { bg: string; text: string }> = {
  currency: {
    bg: "bg-green-100 dark:bg-green-950",
    text: "text-green-600 dark:text-green-400",
  },
  users: {
    bg: "bg-purple-100 dark:bg-purple-950",
    text: "text-purple-600 dark:text-purple-400",
  },
  chart: {
    bg: "bg-blue-100 dark:bg-blue-950",
    text: "text-blue-600 dark:text-blue-400",
  },
  activity: {
    bg: "bg-amber-100 dark:bg-amber-950",
    text: "text-amber-600 dark:text-amber-400",
  },
  warning: {
    bg: "bg-red-100 dark:bg-red-950",
    text: "text-red-600 dark:text-red-400",
  },
  info: {
    bg: "bg-sky-100 dark:bg-sky-950",
    text: "text-sky-600 dark:text-sky-400",
  },
};

const iconColors = computed(() => iconColorMap[props.icon] || iconColorMap.info);

// Sparkline path generation (simple SVG polyline)
const sparklinePath = computed(() => {
  if (props.sparkline.length < 2) return "";
  const data = props.sparkline;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const width = 80;
  const height = 28;
  const step = width / (data.length - 1);

  const points = data.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  });

  return `M${points.join(" L")}`;
});

const sparklineColor = computed(() =>
  changeIsPositive.value
    ? "stroke-green-500 dark:stroke-green-400"
    : "stroke-red-500 dark:stroke-red-400",
);
</script>

<template>
  <div class="card p-5">
    <!-- Loading skeleton -->
    <div v-if="loading" class="animate-pulse space-y-3">
      <div class="flex items-center gap-3">
        <div class="h-10 w-10 rounded-lg skeleton" />
        <div class="flex-1 space-y-2">
          <div class="h-3 w-24 rounded skeleton" />
          <div class="h-5 w-16 rounded skeleton" />
        </div>
      </div>
    </div>

    <!-- Content -->
    <div v-else class="flex items-start justify-between gap-3">
      <div class="flex items-start gap-3 min-w-0">
        <!-- Icon -->
        <div
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
          :class="iconColors.bg"
        >
          <!-- Currency icon -->
          <svg
            v-if="icon === 'currency'"
            class="h-5 w-5"
            :class="iconColors.text"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <!-- Users icon -->
          <svg
            v-else-if="icon === 'users'"
            class="h-5 w-5"
            :class="iconColors.text"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
          <!-- Chart icon -->
          <svg
            v-else-if="icon === 'chart'"
            class="h-5 w-5"
            :class="iconColors.text"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <!-- Activity icon -->
          <svg
            v-else-if="icon === 'activity'"
            class="h-5 w-5"
            :class="iconColors.text"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <!-- Warning icon -->
          <svg
            v-else-if="icon === 'warning'"
            class="h-5 w-5"
            :class="iconColors.text"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <!-- Info icon (default) -->
          <svg
            v-else
            class="h-5 w-5"
            :class="iconColors.text"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>

        <!-- Label + Value -->
        <div class="min-w-0">
          <p class="text-xs font-medium text-muted-foreground">{{ label }}</p>
          <p class="mt-1 text-2xl font-bold text-foreground tracking-tight">
            {{ prefix }}{{ formattedValue }}{{ suffix }}
          </p>
          <!-- Change indicator -->
          <div v-if="change !== null" class="mt-1 flex items-center gap-1">
            <!-- Up arrow -->
            <svg
              v-if="changeIsPositive"
              class="h-3.5 w-3.5 text-green-600 dark:text-green-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
            </svg>
            <!-- Down arrow -->
            <svg
              v-else
              class="h-3.5 w-3.5 text-red-600 dark:text-red-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
            <span
              class="text-xs font-medium"
              :class="changeIsPositive
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'"
            >
              {{ changeDisplay }}
            </span>
          </div>
        </div>
      </div>

      <!-- Sparkline -->
      <svg
        v-if="sparkline.length >= 2"
        class="shrink-0"
        width="80"
        height="28"
        viewBox="0 0 80 28"
        fill="none"
      >
        <path
          :d="sparklinePath"
          :class="sparklineColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          fill="none"
        />
      </svg>
    </div>
  </div>
</template>
