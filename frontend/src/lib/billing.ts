/**
 * Billing API client — types and functions for the billing backend.
 *
 * Covers all billing endpoints:
 *   - Public:  GET /billing/products, GET /billing/products/{slug}, GET /billing/products/{slug}/plans
 *   - Protected: GET /billing/auth/me, GET /billing/subscriptions, subscription management
 *
 * Usage in Vue components:
 *   import { billingApi } from "@/lib/billing";
 *   const subs = await billingApi.getSubscriptions();
 */

import { apiClient } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AccessEntrySchema {
  key: string;
  value: boolean | number | string;
  description?: string | null;
}

export interface PlanSchema {
  id: number;
  name: string;
  slug: string;
  description: string;
  price_cents: number;
  currency: string;
  billing_cycle: "monthly" | "yearly" | "lifetime";
  trial_days: number;
  features: Record<string, string | number | boolean>;
  sort_order: number;
  is_active: boolean;
  is_featured: boolean;
  display_price: string;
  is_free: boolean;
  // Currency conversion fields — populated when ?currency= is passed
  converted_price_cents?: number | null;
  user_currency?: string | null;
  exchange_rate?: string | null;
}

export interface PlanDetailSchema extends PlanSchema {
  access_entries: AccessEntrySchema[];
}

export interface ServiceDomainSchema {
  id: number;
  domain: string;
  product_id: number;
  is_primary: boolean;
  is_active: boolean;
}

export interface ProductSchema {
  id: number;
  name: string;
  slug: string;
  description: string;
  home_url: string;
  is_active: boolean;
  created_at: string;
}

export interface ProductDetailSchema extends ProductSchema {
  plans: PlanSchema[];
  service_domains: ServiceDomainSchema[];
}

export interface SubscriptionInfoSchema {
  plan_name: string;
  plan_slug: string;
  status: string;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
  trial_end: string | null;
  is_active: boolean;
  is_credit_based: boolean;
}

export interface SubscriptionOutputSchema {
  id: number;
  user_id: number;
  status: string;
  cancel_at_period_end: boolean;
  currency?: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  trial_start: string | null;
  trial_end: string | null;
  canceled_at: string | null;
  expires_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  plan_name: string;
  plan_slug: string;
  product_name: string;
  product_slug: string;
}

export interface SubscriptionDetailSchema extends SubscriptionOutputSchema {
  plan: PlanDetailSchema;
  access: Record<string, boolean | number | string>;
}

export interface AuthMeSchema {
  user: Record<string, unknown>;
  subscription: SubscriptionInfoSchema | null;
  access: Record<string, boolean | number | string>;
}

export interface CheckoutInputSchema {
  plan_slug: string;
  billing_cycle?: string;
  tos_accepted?: boolean;
  return_url?: string;
}

// ─── Proration Preview ───────────────────────────────────────────────────

export interface ProrationPreviewOutputSchema {
  subtotal: number;
  tax: number;
  total: number;
  next_billing: number;
  currency: string;
  preview_token: string | null;
  change_type: "upgrade" | "downgrade" | "lateral";
  is_upgrade: boolean;
}

export interface ConfirmPlanChangeOutputSchema {
  plan_name: string;
  plan_slug: string;
  status: string;
  change_type: "upgrade" | "downgrade" | "lateral";
  effective_when: "immediately" | "next_billing_cycle";
  amount_charged: number;
  currency: string;
}

// ─── Transaction History (F11 — pulled from Stripe) ────────────────────

export interface TransactionItemSchema {
  id: string;
  type: string;
  number: string | null;
  status: string;
  amount_paid: number;
  amount_due: number;
  tax: number;
  currency: string;
  description: string;
  hosted_url: string | null;
  pdf_url: string | null;
  created: string | null;
  period_start: string | null;
  period_end: string | null;
  paid: boolean;
  attempt_count: number;
  charge_id: string;
  payment_method: string;
  card_brand: string;
}

export interface ChangePlanInputSchema {
  plan_slug: string;
  proration_behavior?: string;
}

// ─── API Functions ───────────────────────────────────────────────────────────

export const billingApi = {
  // ── Public endpoints ──

  async getProducts(): Promise<ProductSchema[]> {
    return apiClient.get<ProductSchema[]>("/billing/products");
  },

  async getProductBySlug(
    slug: string,
    userCurrency?: string,
  ): Promise<ProductDetailSchema> {
    const params: Record<string, string> = {};
    if (userCurrency) params.currency = userCurrency;
    return apiClient.get<ProductDetailSchema>(`/billing/products/${slug}`, {
      params,
    });
  },

  // ── Protected endpoints ──

  async getAuthMe(domain?: string): Promise<AuthMeSchema> {
    const headers: Record<string, string> = {};
    if (domain) {
      headers["X-Service-Domain"] = domain;
    }
    return apiClient.get<AuthMeSchema>("/billing/auth/me", { headers });
  },

  async getSubscriptions(
    limit?: number,
    offset?: number,
  ): Promise<SubscriptionOutputSchema[]> {
    const params: Record<string, string | number> = {};
    if (limit) params.limit = limit;
    if (offset) params.offset = offset;
    const result = await apiClient.get<{ items: SubscriptionOutputSchema[] }>(
      "/billing/subscriptions",
      { params },
    );
    return result.items || result;
  },

  async syncSubscriptions(): Promise<SubscriptionOutputSchema[]> {
    return apiClient.post<SubscriptionOutputSchema[]>(
      "/billing/subscriptions/sync",
    );
  },

  async getSubscriptionDetail(
    productSlug: string,
  ): Promise<SubscriptionDetailSchema> {
    return apiClient.get<SubscriptionDetailSchema>(
      `/billing/subscriptions/${productSlug}`,
    );
  },

  async cancelSubscription(
    productSlug: string,
    reason?: string,
  ): Promise<{ message: string }> {
    const params: Record<string, string> = {};
    if (reason) params.reason = reason;
    return apiClient.post<{ message: string }>(
      `/billing/subscriptions/${productSlug}/cancel`,
      undefined,
      { params },
    );
  },

  async reactivateSubscription(
    productSlug: string,
  ): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>(
      `/billing/subscriptions/${productSlug}/reactivate`,
    );
  },

  async changePlan(
    productSlug: string,
    planSlug: string,
    prorationBehavior: string = "create_prorations",
  ): Promise<{ message: string }> {
    const body: ChangePlanInputSchema = {
      plan_slug: planSlug,
      proration_behavior: prorationBehavior,
    };
    return apiClient.post<{ message: string }>(
      `/billing/subscriptions/${productSlug}/change-plan`,
      body,
    );
  },

  async createCheckout(
    productSlug: string,
    planSlug: string,
    billingCycle?: string,
    tosAccepted?: boolean,
    returnUrl?: string,
  ): Promise<{ checkout_url: string | null; reactivated: boolean }> {
    const body: CheckoutInputSchema = {
      plan_slug: planSlug,
      billing_cycle: billingCycle,
      tos_accepted: tosAccepted,
      return_url: returnUrl,
    };
    return apiClient.post<{
      checkout_url: string | null;
      reactivated: boolean;
    }>(`/billing/subscriptions/${productSlug}/checkout`, body);
  },

  async confirmCheckout(sessionId: string): Promise<{
    plan_name: string;
    plan_slug: string;
    status: string;
    trial_end: string | null;
    current_period_end: string | null;
  }> {
    return apiClient.post(`/billing/checkout/confirm`, {
      session_id: sessionId,
    });
  },

  async createPortalSession(
    returnUrl?: string,
  ): Promise<{ portal_url: string }> {
    const params = returnUrl
      ? `?return_url=${encodeURIComponent(returnUrl)}`
      : "";
    return apiClient.post<{ portal_url: string }>(`/billing/portal${params}`);
  },

  // ── Proration Preview ──

  async previewPlanChange(
    productSlug: string,
    planSlug: string,
    prorationBehavior: string = "create_prorations",
  ): Promise<ProrationPreviewOutputSchema> {
    return apiClient.post<ProrationPreviewOutputSchema>(
      `/billing/subscriptions/${productSlug}/preview-plan-change`,
      { plan_slug: planSlug, proration_behavior: prorationBehavior },
    );
  },

  async confirmPlanChange(
    productSlug: string,
    planSlug: string,
    previewToken: string,
  ): Promise<ConfirmPlanChangeOutputSchema> {
    return apiClient.post<ConfirmPlanChangeOutputSchema>(
      `/billing/subscriptions/${productSlug}/confirm-plan-change`,
      { plan_slug: planSlug, preview_token: previewToken },
    );
  },

  // ── Transaction History (UX-05: user-facing endpoint) ──────────

  async getTransactionHistory(
    limit: number = 25,
    startingAfter?: string,
  ): Promise<{
    transactions: TransactionItemSchema[];
    has_more: boolean;
    currency: string;
  }> {
    const params: Record<string, string | number> = { limit: String(limit) };
    if (startingAfter) {
      params.starting_after = startingAfter;
    }
    return apiClient.get<{
      transactions: TransactionItemSchema[];
      has_more: boolean;
      currency: string;
    }>("/billing/subscriptions/transactions", { params });
  },

  // ── GDPR Data Export (Art. 20) ──

  async exportBillingData(): Promise<{
    user: { email: string; name: string; user_id: number };
    stripe_customer: Record<string, unknown>;
    subscriptions: Record<string, unknown>[];
    refunds: Record<string, unknown>[];
    invoices: Record<string, unknown>[];
    exported_at: string;
  }> {
    return apiClient.get("/billing/export-data");
  },
};

// ─── User Currency Store (F13) ──────────────────────────────────────────────

/** Default currency used when none is specified. Fetched from auth/me user profile. */
let _userCurrency: string = "USD";

/**
 * Set the user's preferred currency. Called after auth/me fetch.
 * Falls back to "USD" if the profile has no currency field.
 */
export function setUserCurrency(currency: string | null | undefined): void {
  _userCurrency =
    currency && currency.length === 3 ? currency.toUpperCase() : "USD";
}

/**
 * Get the user's preferred currency code (e.g. "USD", "EUR", "BDT").
 */
export function getUserCurrency(): string {
  return _userCurrency;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Format price from cents to human-readable string.
 * Defaults to the user's profile currency (F13), falling back to "USD".
 * Explicit currency param overrides the user's profile currency.
 *
 * UX-13 Fix: Uses ``navigator.language`` (user's browser locale)
 * instead of hardcoded ``"en-US"``.  Non-English users now see
 * number formatting appropriate for their locale (e.g. 9,00€ for
 * German users, ৳৯০০ for Bengali users).
 *
 * Example: 900 → "$9.00"
 */
export function formatPrice(cents: number, currency?: string | null): string {
  if (cents === 0) return "Free";
  const effectiveCurrency =
    currency && currency.length === 3 ? currency : _userCurrency;
  const amount = cents / 100;
  const locale =
    typeof navigator !== "undefined" ? navigator.language : "en-US";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: effectiveCurrency.toUpperCase(),
    minimumFractionDigits: 2,
  }).format(amount);
}

/**
 * Format billing cycle for display.
 */
export function formatCycle(cycle: string): string {
  const map: Record<string, string> = {
    monthly: "/mo",
    yearly: "/yr",
    lifetime: "one-time",
  };
  return map[cycle] || cycle;
}

/**
 * Get status color classes for subscription status badge.
 */
export function getStatusStyle(status: string): {
  bg: string;
  text: string;
  dot: string;
} {
  const styles: Record<string, { bg: string; text: string; dot: string }> = {
    active: {
      bg: "bg-brand-50 dark:bg-brand-950/50",
      text: "text-brand-700 dark:text-brand-300",
      dot: "bg-brand-500",
    },
    trialing: {
      bg: "bg-blue-50 dark:bg-blue-950/50",
      text: "text-blue-700 dark:text-blue-300",
      dot: "bg-blue-500",
    },
    past_due: {
      bg: "bg-yellow-50 dark:bg-yellow-950/50",
      text: "text-yellow-700 dark:text-yellow-300",
      dot: "bg-yellow-500",
    },
    canceled: {
      bg: "bg-orange-50 dark:bg-orange-950/50",
      text: "text-orange-700 dark:text-orange-300",
      dot: "bg-orange-500",
    },
    paused: {
      bg: "bg-gray-50 dark:bg-gray-950/50",
      text: "text-gray-700 dark:text-gray-300",
      dot: "bg-gray-500",
    },
    expired: {
      bg: "bg-red-50 dark:bg-red-950/50",
      text: "text-red-700 dark:text-red-300",
      dot: "bg-red-500",
    },
  };
  return styles[status] || styles.expired;
}

/**
 * Format a date string for display.
 *
 * UX-13 Fix: Uses ``navigator.language`` (user's browser locale)
 * instead of hardcoded ``"en-US"``.  Dates are now formatted
 * according to the user's locale preferences (e.g. "2. Mai 2026" for
 * German, "2026年5月2日" for Japanese).
 */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const locale =
    typeof navigator !== "undefined" ? navigator.language : "en-US";
  return new Date(dateStr).toLocaleDateString(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ─── Feature Value Formatting ────────────────────────────────────────────────

/**
 * Feature value type classification for display rendering.
 *
 * Features values in PlanSchema.features can be boolean, integer, or string:
 *   - boolean true  → shown as "True" with green checkmark
 *   - boolean false → shown as "False" with red cross
 *   - integer 0     → shown as "Unlimited" with purple infinity icon
 *   - integer N>0   → shown as the number with blue numeric badge
 *   - string        → shown as-is with green checkmark
 */
export type FeatureValueType =
  | "boolean-true"
  | "boolean-false"
  | "unlimited"
  | "numeric"
  | "string";

/**
 * Classify a feature value's type for display rendering.
 * Handles both proper JS types (boolean, number) and legacy string patterns
 * ("true", "false", "Unlimited", "0") for backward compatibility.
 */
export function getFeatureValueType(
  value: string | number | boolean,
): FeatureValueType {
  if (typeof value === "boolean") {
    return value ? "boolean-true" : "boolean-false";
  }
  if (typeof value === "number") {
    return value === 0 ? "unlimited" : "numeric";
  }
  // String: check for special patterns for backward compatibility
  const str = String(value).toLowerCase();
  if (str === "true") return "boolean-true";
  if (str === "false") return "boolean-false";
  if (str === "unlimited" || str === "infinity") return "unlimited";
  if (str.match(/^\d+$/)) {
    const num = parseInt(str, 10);
    return num === 0 ? "unlimited" : "numeric";
  }
  return "string";
}

/**
 * Format a feature value for display according to its type:
 *   - boolean true  → "True"
 *   - boolean false → "False"
 *   - integer 0     → "Unlimited"
 *   - integer N>0   → the number as string (e.g. "50")
 *   - string        → as-is
 */
export function formatFeatureValue(value: string | number | boolean): string {
  const type = getFeatureValueType(value);
  switch (type) {
    case "boolean-true":
      return "True";
    case "boolean-false":
      return "False";
    case "unlimited":
      return "Unlimited";
    case "numeric":
      return String(value);
    case "string":
      return String(value);
  }
}
