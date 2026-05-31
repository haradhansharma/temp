<script setup lang="ts">
/**
 * AdminDashboard — Main admin dashboard page.
 *
 * Displays:
 *   - Stats row: Active Subscriptions, MRR, Trials, Past Due, Churn Rate
 *   - Subscription trend chart (SVG line chart — last 12 months)
 *   - Revenue by product (horizontal bar chart)
 *   - Recent activity feed (last 10 audit log entries)
 *   - Quick links to admin sections
 *
 * Uses 10.2 reusable components: AdminStatsCard, AdminPageHeader,
 * AdminAuditTimeline, AdminEmptyState.
 */

import { ref, computed, onMounted } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import {
  adminApi,
  formatRelativeTime,
  formatDateTime,
  formatKeyPrefix,
} from "@/lib/admin";
import type {
  MetricsOverview,
  MetricsRevenue,
  AuditLogEntry,
} from "@/lib/admin";

import AdminPageHeader from "@/components/admin/AdminPageHeader.vue";
import AdminStatsCard from "@/components/admin/AdminStatsCard.vue";
import AdminAuditTimeline from "@/components/admin/AdminAuditTimeline.vue";

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const loadError = ref<string | null>(null);

const overview = ref<MetricsOverview | null>(null);
const revenue = ref<MetricsRevenue | null>(null);
const recentAudit = ref<AuditLogEntry[]>([]);

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchDashboardData() {
  loading.value = true;
  loadError.value = null;
  try {
    const [overviewData, revenueData, auditData] = await Promise.allSettled([
      adminApi.getMetricsOverview(),
      adminApi.getMetricsRevenue(),
      adminApi.listAuditLog({ page: 1, page_size: 10 }),
    ]);

    if (overviewData.status === "fulfilled") {
      overview.value = overviewData.value;
    } else {
      console.warn("Failed to load metrics overview:", overviewData.reason);
    }

    if (revenueData.status === "fulfilled") {
      revenue.value = revenueData.value;
    } else {
      console.warn("Failed to load revenue data:", revenueData.reason);
    }

    if (auditData.status === "fulfilled") {
      recentAudit.value = auditData.value.results;
    } else {
      console.warn("Failed to load audit log:", auditData.reason);
    }

    // If all failed, show error
    if (!overview.value && !revenue.value && recentAudit.value.length === 0) {
      loadError.value = "Failed to load dashboard data. Please try again.";
    }
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchDashboardData();
});

// ─── Stats cards computed values ─────────────────────────────────────────────

const churnRateDisplay = computed(() => {
  if (!overview.value) return "—";
  return `${(overview.value.churn_rate * 100).toFixed(1)}%`;
});

const churnRateChange = computed<number | null>(() => {
  // Churn rate as a percentage change indicator (positive = bad, show red)
  if (!overview.value) return null;
  const rate = overview.value.churn_rate * 100;
  // Show rate itself; no historical comparison available yet
  return null;
});

// ─── Subscription Trend Chart (SVG) ─────────────────────────────────────────

const trendChartData = computed(() => {
  if (!revenue.value?.by_month?.length) return null;

  const months = revenue.value.by_month;
  const maxRevenue = Math.max(...months.map((m) => m.revenue_cents), 1);

  const chartWidth = 600;
  const chartHeight = 180;
  const paddingX = 50;
  const paddingY = 20;
  const plotWidth = chartWidth - paddingX * 2;
  const plotHeight = chartHeight - paddingY * 2;

  const points = months.map((m, i) => {
    const x = paddingX + (i / Math.max(months.length - 1, 1)) * plotWidth;
    const y = paddingY + plotHeight - (m.revenue_cents / maxRevenue) * plotHeight;
    return { x, y, ...m };
  });

  // Build SVG path
  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`)
    .join(" ");

  // Build area path (filled under line)
  const areaPath =
    linePath +
    ` L${points[points.length - 1].x},${paddingY + plotHeight} L${points[0].x},${paddingY + plotHeight} Z`;

  // Y-axis labels
  const yLabels = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const value = Math.round((maxRevenue * ratio) / 100);
    const y = paddingY + plotHeight - ratio * plotHeight;
    return { y, label: value >= 1000 ? `$${(value / 1000).toFixed(1)}k` : `$${value}` };
  });

  // X-axis labels
  const xLabels = points.map((p) => ({
    x: p.x,
    label: p.month.slice(5), // "MM" from "YYYY-MM"
  }));

  return {
    chartWidth,
    chartHeight,
    paddingX,
    paddingY,
    points,
    linePath,
    areaPath,
    yLabels,
    xLabels,
    maxRevenue,
  };
});

// ─── Revenue by Product Chart (horizontal bars) ──────────────────────────────

const revenueByProduct = computed(() => {
  if (!revenue.value?.by_product?.length) return null;

  const products = revenue.value.by_product;
  const maxMrr = Math.max(...products.map((p) => p.mrr_cents), 1);

  return products
    .sort((a, b) => b.mrr_cents - a.mrr_cents)
    .map((p) => ({
      ...p,
      mrr_display: formatCents(p.mrr_cents),
      barWidth: (p.mrr_cents / maxMrr) * 100,
    }));
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatCents(cents: number): string {
  if (cents >= 100) {
    return `$${(cents / 100).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
  return `$${cents}`;
}

function formatMonthLabel(month: string): string {
  const [year, mon] = month.split("-");
  const monthNames = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${monthNames[parseInt(mon)]} ${year.slice(2)}`;
}

// Bar chart colors for products
const productBarColors = [
  "bg-green-500 dark:bg-green-400",
  "bg-blue-500 dark:bg-blue-400",
  "bg-purple-500 dark:bg-purple-400",
  "bg-amber-500 dark:bg-amber-400",
  "bg-cyan-500 dark:bg-cyan-400",
  "bg-rose-500 dark:bg-rose-400",
];
</script>

<template>
  <div class="space-y-6">
    <!-- Page Header -->
    <AdminPageHeader
      title="Admin Dashboard"
      description="Monitor and manage your Sattabase platform."
      :breadcrumbs="[{ label: 'Admin' }]"
    />

    <!-- Error state -->
    <div
      v-if="loadError"
      class="card flex flex-col items-center gap-4 p-10 text-center"
    >
      <svg class="h-12 w-12 text-destructive/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <div>
        <p class="font-medium text-foreground">Failed to load dashboard</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchDashboardData">Try again</button>
    </div>

    <template v-else>
      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Stats Row (10.3.2)                                                    -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <AdminStatsCard
          label="Active Subscriptions"
          :value="overview?.active_subscriptions ?? 0"
          icon="chart"
          :loading="loading"
        />
        <AdminStatsCard
          label="MRR"
          :value="overview?.mrr_display ?? '$0.00'"
          icon="currency"
          :loading="loading"
        />
        <AdminStatsCard
          label="Trials"
          :value="overview?.trial_subscriptions ?? 0"
          icon="users"
          :loading="loading"
        />
        <AdminStatsCard
          label="Past Due"
          :value="overview?.past_due_subscriptions ?? 0"
          icon="warning"
          :loading="loading"
        />
        <AdminStatsCard
          label="Churn Rate"
          :value="churnRateDisplay"
          suffix=""
          icon="activity"
          :loading="loading"
        />
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Charts Row (10.3.3 + 10.3.4)                                          -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Subscription Trend Chart (takes 2 columns) -->
        <div class="card p-5 lg:col-span-2">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <h3 class="text-sm font-semibold text-foreground">Revenue Trend</h3>
              <p class="text-xs text-muted-foreground">Monthly recognized revenue (last 12 months)</p>
            </div>
            <span
              v-if="overview"
              class="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-700 dark:bg-green-950 dark:text-green-400"
            >
              {{ overview.mrr_display }}/mo
            </span>
          </div>

          <!-- Loading skeleton -->
          <div v-if="loading" class="animate-pulse">
            <div class="h-44 rounded skeleton" />
          </div>

          <!-- Empty state -->
          <div
            v-else-if="!trendChartData"
            class="flex flex-col items-center gap-2 py-10 text-center"
          >
            <svg class="h-8 w-8 text-muted-foreground/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p class="text-sm text-muted-foreground">No revenue data yet</p>
          </div>

          <!-- SVG Chart -->
          <div v-else class="overflow-x-auto">
            <svg
              :width="trendChartData.chartWidth"
              :height="trendChartData.chartHeight"
              :viewBox="`0 0 ${trendChartData.chartWidth} ${trendChartData.chartHeight}`"
              class="w-full"
              style="min-width: 400px;"
            >
              <!-- Y-axis grid lines -->
              <line
                v-for="label in trendChartData.yLabels"
                :key="label.y"
                :x1="trendChartData.paddingX"
                :x2="trendChartData.chartWidth - trendChartData.paddingX"
                :y1="label.y"
                :y2="label.y"
                stroke="currentColor"
                class="text-border"
                stroke-width="1"
                stroke-dasharray="4,4"
              />

              <!-- Y-axis labels -->
              <text
                v-for="label in trendChartData.yLabels"
                :key="`y-${label.y}`"
                :x="trendChartData.paddingX - 8"
                :y="label.y + 4"
                text-anchor="end"
                class="fill-muted-foreground"
                font-size="10"
              >
                {{ label.label }}
              </text>

              <!-- Area fill -->
              <path
                :d="trendChartData.areaPath"
                class="fill-green-500/10 dark:fill-green-400/10"
              />

              <!-- Line -->
              <path
                :d="trendChartData.linePath"
                class="stroke-green-500 dark:stroke-green-400"
                fill="none"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />

              <!-- Data points -->
              <circle
                v-for="(point, i) in trendChartData.points"
                :key="`pt-${i}`"
                :cx="point.x"
                :cy="point.y"
                r="3"
                class="fill-green-500 dark:fill-green-400"
              />

              <!-- X-axis labels -->
              <text
                v-for="label in trendChartData.xLabels"
                :key="`x-${label.x}`"
                :x="label.x"
                :y="trendChartData.chartHeight - 4"
                text-anchor="middle"
                class="fill-muted-foreground"
                font-size="10"
              >
                {{ label.label }}
              </text>
            </svg>
          </div>
        </div>

        <!-- Revenue by Product (1 column) -->
        <div class="card p-5">
          <div class="mb-4">
            <h3 class="text-sm font-semibold text-foreground">Revenue by Product</h3>
            <p class="text-xs text-muted-foreground">Monthly recurring revenue breakdown</p>
          </div>

          <!-- Loading skeleton -->
          <div v-if="loading" class="space-y-4 animate-pulse">
            <div v-for="i in 3" :key="i" class="space-y-2">
              <div class="h-3 w-20 rounded skeleton" />
              <div class="h-5 rounded skeleton" :style="{ width: `${70 - i * 15}%` }" />
            </div>
          </div>

          <!-- Empty state -->
          <div
            v-else-if="!revenueByProduct || revenueByProduct.length === 0"
            class="flex flex-col items-center gap-2 py-8 text-center"
          >
            <svg class="h-8 w-8 text-muted-foreground/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
            </svg>
            <p class="text-sm text-muted-foreground">No revenue data</p>
          </div>

          <!-- Bar chart -->
          <div v-else class="space-y-4">
            <div
              v-for="(product, i) in revenueByProduct"
              :key="product.product_id"
            >
              <div class="flex items-center justify-between mb-1">
                <span class="text-xs font-medium text-foreground truncate max-w-[60%]">
                  {{ product.product_name }}
                </span>
                <span class="text-xs font-semibold text-foreground shrink-0">
                  {{ product.mrr_display }}
                </span>
              </div>
              <div class="h-2.5 w-full rounded-full bg-muted">
                <div
                  class="h-full rounded-full transition-all duration-500"
                  :class="productBarColors[i % productBarColors.length]"
                  :style="{ width: `${product.barWidth}%` }"
                />
              </div>
              <p class="mt-0.5 text-[10px] text-muted-foreground">
                {{ product.active_subscriptions }} active
                <span v-if="product.trial_subscriptions > 0">
                  &middot; {{ product.trial_subscriptions }} trial
                </span>
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══════════════════════════════════════════════════════════════════════ -->
      <!--  Bottom Row: Activity Feed + Quick Links (10.3.5 + 10.3.6)             -->
      <!-- ═══════════════════════════════════════════════════════════════════════ -->

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Recent Activity Feed -->
        <div class="card p-5 lg:col-span-2">
          <div class="mb-4 flex items-center justify-between">
            <div>
              <h3 class="text-sm font-semibold text-foreground">Recent Activity</h3>
              <p class="text-xs text-muted-foreground">Last 10 admin actions</p>
            </div>
            <a
              href="/admin/audit-log"
              class="text-xs font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300 transition-colors"
            >
              View all
              <svg class="inline h-3 w-3 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </a>
          </div>

          <!-- Loading skeleton -->
          <div v-if="loading" class="space-y-4 animate-pulse">
            <div v-for="i in 4" :key="i" class="flex gap-3">
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

          <!-- Empty -->
          <div
            v-else-if="recentAudit.length === 0"
            class="flex flex-col items-center gap-2 py-8 text-center"
          >
            <svg class="h-8 w-8 text-muted-foreground/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p class="text-sm text-muted-foreground">No recent activity</p>
          </div>

          <!-- Timeline -->
          <AdminAuditTimeline
            v-else
            :entries="recentAudit"
            :loading="false"
          />
        </div>

        <!-- Quick Links -->
        <div class="card p-5">
          <h3 class="mb-4 text-sm font-semibold text-foreground">Quick Links</h3>
          <div class="space-y-2">
            <a
              href="/admin/subscriptions"
              class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <svg class="h-4 w-4 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
              </svg>
              View All Subscriptions
            </a>
            <a
              href="/admin/products"
              class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <svg class="h-4 w-4 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
              </svg>
              Manage Products
            </a>
            <a
              href="/admin/api-keys"
              class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <svg class="h-4 w-4 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
              </svg>
              API Keys
            </a>
            <a
              href="/admin/users"
              class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <svg class="h-4 w-4 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
              User Management
            </a>
            <a
              href="/admin/refunds"
              class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <svg class="h-4 w-4 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
              </svg>
              Refund Requests
            </a>
            <a
              href="/admin/webhooks"
              class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <svg class="h-4 w-4 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              Webhook Events
            </a>

            <!-- Separator -->
            <div class="border-t border-border my-2" />

            <a
              href="/admin/django/"
              class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              target="_blank"
              rel="noopener noreferrer"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Django Admin
            </a>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
