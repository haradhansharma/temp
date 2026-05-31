/**
 * Admin API client — types and functions for all admin endpoints.
 *
 * Covers the admin API endpoints grouped by domain:
 *   - API Keys: create, list, revoke, rotate
 *   - Products: CRUD, toggle, list with counts
 *   - Service Domains: add, update, remove
 *   - Plans: CRUD, toggle, feature, duplicate
 *   - Access Entries: add, update, remove, bulk, matrix
 *   - Subscriptions: list, detail, override, cancel, expire, extend
 *   - Users: list, detail, status, role, audit
 *   - Refunds: list, approve, reject
 *   - Metrics: overview, revenue, subscriptions, products
 *   - Webhooks: list, retry
 *   - Audit Log: list
 *
 * All endpoints require admin role (JWT + IsAdmin permission).
 *
 * Usage in Vue components:
 *   import { adminApi } from "@/lib/admin";
 *   const keys = await adminApi.listApiKeys({ page: 1 });
 *   const products = await adminApi.listProducts();
 */

import { apiClient } from "@/lib/api";

// ─── Shared Types ───────────────────────────────────────────────────────────

export interface PaginationMeta {
  total_items: number;
  total_pages: number;
  current_page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface PaginatedResponse<T> {
  meta: PaginationMeta;
  results: T[];
}

// ─── API Key Types ──────────────────────────────────────────────────────────

export interface ApiKeyItem {
  id: number;
  name: string;
  api_key_prefix: string;
  service_domain_id: number;
  service_domain: string;
  permissions: Record<string, unknown>;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string | null;
  created_by: string | null;
}

export interface ApiKeyCreatePayload {
  name: string;
  service_domain_id: number;
}

export interface ApiKeyCreateResponse {
  id: number;
  name: string;
  api_key_prefix: string;
  raw_api_key: string;
  service_domain_id: number;
  service_domain: string;
  is_active: boolean;
  created_at: string | null;
  warning: string;
}

export interface ApiKeyRotateResponse {
  id: number;
  name: string;
  old_prefix: string;
  new_api_key: string;
  new_prefix: string;
  service_domain_id: number;
  service_domain: string;
  is_active: boolean;
  warning: string;
}

export interface ApiKeyListResponse extends PaginatedResponse<ApiKeyItem> {}

export interface ServiceDomainOption {
  id: number;
  domain: string;
  product_name: string;
  is_active: boolean;
}

// ─── Product Types ──────────────────────────────────────────────────────────

export interface ProductItem {
  id: number;
  name: string;
  slug: string;
  description: string;
  home_url: string;
  icon?: string | null;
  is_active: boolean;
  plan_count: number;
  active_plan_count?: number;
  subscriber_count: number;
  domain_count?: number;
  stripe_product_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductDetail extends ProductItem {
  plans: PlanItem[];
  service_domains: ServiceDomainDetail[];
}

export interface ProductCreatePayload {
  name: string;
  slug?: string;
  description?: string;
  home_url?: string;
}

export interface ProductUpdatePayload {
  name?: string;
  slug?: string;
  description?: string;
  home_url?: string;
  is_active?: boolean;
}

export interface ProductListResponse extends PaginatedResponse<ProductItem> {}

// ─── Service Domain Types ───────────────────────────────────────────────────

export interface ServiceDomainDetail {
  id: number;
  domain: string;
  is_primary: boolean;
  is_active: boolean;
  product_id: number;
  product_name: string;
  created_at: string;
}

export interface ServiceDomainCreatePayload {
  domain: string;
  is_primary?: boolean;
}

export interface ServiceDomainUpdatePayload {
  domain?: string;
  is_primary?: boolean;
  is_active?: boolean;
}

// ─── Plan Types ─────────────────────────────────────────────────────────────

export interface PlanItem {
  id: number;
  name: string;
  slug: string;
  price_cents: number;
  currency: string;
  billing_cycle: "monthly" | "yearly";
  trial_days: number;
  is_featured: boolean;
  is_active: boolean;
  sort_order: number;
  subscriber_count: number;
  access_entry_count: number;
  product_id: number;
  product_name: string;
  display_price?: string;
  is_free?: boolean;
}

export interface PlanDetail extends PlanItem {
  access_entries: AccessEntryItem[];
  stripe_price_id: string | null;
  description?: string;
}

export interface PlanCreatePayload {
  name: string;
  slug?: string;
  price_cents: number;
  currency?: string;
  billing_cycle: "monthly" | "yearly";
  trial_days?: number;
  is_featured?: boolean;
  sort_order?: number;
}

export interface PlanUpdatePayload {
  name?: string;
  slug?: string;
  price_cents?: number;
  currency?: string;
  billing_cycle?: "monthly" | "yearly";
  trial_days?: number;
  is_featured?: boolean;
  is_active?: boolean;
  sort_order?: number;
}

export interface PlanListResponse extends PaginatedResponse<PlanItem> {}

// ─── Access Entry Types ─────────────────────────────────────────────────────

export interface AccessEntryItem {
  id: number;
  key: string;
  value: string;
  value_type: "boolean" | "integer" | "string";
  description: string;
  plan_id: number;
  plan_name: string;
}

export interface AccessEntryCreatePayload {
  key: string;
  value: string;
  value_type: "boolean" | "integer" | "string";
  description?: string;
}

export interface AccessEntryUpdatePayload {
  key?: string;
  value?: string;
  value_type?: "boolean" | "integer" | "string";
  description?: string;
}

export interface AccessEntryBulkPayload {
  entries: AccessEntryCreatePayload[];
}

export interface AccessMatrixRow {
  key: string;
  description: string | null;
  values: Record<string, string | null>; // plan_slug → value
  entry_ids: Record<string, number | null>; // plan_slug → entry ID (for edit/delete)
}

export interface AccessMatrixResponse {
  product_id: number;
  product_name: string;
  plans: { slug: string; name: string; is_active: boolean }[];
  rows: AccessMatrixRow[];
}

// ─── Access Matrix Row Save Types (atomic multi-plan save) ─────────────────

export interface AccessMatrixRowEntry {
  plan_id: number;
  value: string;
  value_type: "boolean" | "integer" | "string";
}

export interface AccessMatrixRowSavePayload {
  original_key?: string;
  key: string;
  description?: string;
  entries: AccessMatrixRowEntry[];
}

export interface AccessMatrixRowSaveResponse {
  product_id: number;
  key: string;
  original_key: string | null;
  entries_created: number;
  entries_updated: number;
  entries_deleted: number;
  entries: AccessEntryItem[];
}

// ─── Subscription Types ─────────────────────────────────────────────────────

export interface SubscriptionItem {
  id: number;
  user_id: number;
  user_email: string;
  user_name: string;
  product_id: number;
  product_name: string;
  product_slug: string;
  plan_id: number;
  plan_name: string;
  plan_slug: string;
  status:
    | "active"
    | "trialing"
    | "past_due"
    | "canceled"
    | "expired"
    | "paused";
  currency: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  dunning_step: number;
  stripe_subscription_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SubscriptionDetail extends SubscriptionItem {
  trial_start: string | null;
  trial_end: string | null;
  canceled_at: string | null;
  expires_at: string | null;
  past_due_at: string | null;
  has_used_trial: boolean;
  tos_accepted_at: string | null;
  tos_version: string | null;
  last_dunning_email_at: string | null;
  stripe_customer_id: string | null;
  access: Record<string, unknown>;
}

export interface SubscriptionOverridePayload {
  plan_id?: number;
  status?: string;
  period_start?: string;
  period_end?: string;
  reason?: string;
}

export interface SubscriptionExtendPayload {
  days: number;
  reason?: string;
}

export interface SubscriptionListResponse extends PaginatedResponse<SubscriptionItem> {}

export interface PlanChangeItem {
  id: number;
  from_plan_id: number;
  from_plan_name: string;
  to_plan_id: number;
  to_plan_name: string;
  proration_amount_cents: number;
  currency: string;
  stripe_proration_id: string | null;
  proration_behavior: string;
  initiated_by_id: number | null;
  initiated_by_email: string | null;
  created_at: string | null;
}

export interface InvoiceItem {
  id: number;
  stripe_invoice_id: string;
  subscription_id: number;
  number: string;
  status: string;
  amount_paid_cents: number;
  amount_due_cents: number;
  tax_cents: number;
  discount_cents: number;
  currency: string;
  period_start: string | null;
  period_end: string | null;
  hosted_url: string;
  pdf_url: string;
  stripe_fee_cents: number;
  attempt_count: number;
  created_at: string | null;
}

// ─── User Types ─────────────────────────────────────────────────────────────

export interface UserItem {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  is_active: boolean;
  is_email_verified: boolean;
  is_staff: boolean;
  role: string;
  avatar: string | null;
  subscription_count: number;
  active_subscription_count: number;
  last_login_at: string | null;
  created_at: string | null;
}

export interface UserSubscriptionItem {
  id: number;
  product_name: string;
  product_slug: string;
  plan_name: string;
  plan_slug: string;
  status: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  created_at: string | null;
}

export interface UserDetail extends UserItem {
  phone: string | null;
  timezone: string | null;
  currency: string | null;
  language: string | null;
  subscriptions: UserSubscriptionItem[];
}

export interface UserStatusPayload {
  is_active: boolean;
  reason?: string;
}

export interface UserRolePayload {
  role: string;
  reason?: string;
}

export interface UserAuditEntry {
  event_type: string;
  description: string;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  timestamp: string | null;
}

export interface UserListResponse extends PaginatedResponse<UserItem> {}

// ─── Refund Types ───────────────────────────────────────────────────────────

export interface RefundItem {
  id: number;
  subscription_id: number;
  user_email: string;
  product_name: string | null;
  plan_name: string | null;
  stripe_refund_id: string | null;
  stripe_charge_id: string;
  amount_cents: number;
  currency: string;
  reason: string;
  status: string;
  reason_category: string;
  initiated_by_id: number | null;
  initiated_by_email: string | null;
  initiated_by_ip: string | null;
  approved_by_id: number | null;
  approved_by_email: string | null;
  approved_at: string | null;
  admin_notes: string;
  created_at: string | null;
}

export interface RefundApprovalPayload {
  approved: boolean;
  notes?: string;
}

export interface IssueRefundPayload {
  amount_cents?: number;
  reason?: string;
  reason_category?: string;
  admin_notes?: string;
}

export interface IssueRefundResponse {
  refund_id: number;
  stripe_refund_id: string;
  amount_cents: number;
  currency: string;
  status: string;
  reason_category: string;
  message: string;
}

export interface RefundListResponse extends PaginatedResponse<RefundItem> {}

// ─── Metrics Types ──────────────────────────────────────────────────────────
// Aligned with backend billing/admin_schemas.py (Phase 9)

export interface MetricsOverview {
  mrr_cents: number;
  mrr_display: string;
  active_subscriptions: number;
  trial_subscriptions: number;
  past_due_subscriptions: number;
  canceled_subscriptions: number;
  total_users: number;
  churn_rate: number;
  trial_conversion_rate: number;
  currency: string;
}

export interface MetricsRevenueByProduct {
  product_id: number;
  product_name: string;
  product_slug: string;
  mrr_cents: number;
  active_subscriptions: number;
  trial_subscriptions: number;
}

export interface MetricsRevenueByPlan {
  plan_id: number;
  plan_name: string;
  plan_slug: string;
  product_name: string;
  price_cents: number;
  subscriber_count: number;
  mrr_contribution_cents: number;
}

export interface MetricsRevenueByMonth {
  month: string;
  revenue_cents: number;
  new_subscriptions: number;
  churned_subscriptions: number;
  net_mrr_change_cents: number;
}

export interface MetricsRevenue {
  by_product: MetricsRevenueByProduct[];
  by_plan: MetricsRevenueByPlan[];
  by_month: MetricsRevenueByMonth[];
}

export interface MetricsSubscriptions {
  period_days: number;
  new_registrations: number;
  trial_starts: number;
  trial_conversions: number;
  trial_conversion_rate: number;
  active_to_canceled: number;
  active_to_past_due: number;
  past_due_to_active: number;
  by_product: {
    product_id: number;
    product_name: string;
    product_slug: string;
    trial_starts: number;
    trial_conversions: number;
    active_subscribers: number;
    canceled: number;
    past_due: number;
  }[];
}

export interface MetricsProductItem {
  id: number;
  name: string;
  slug: string;
  total_subscribers: number;
  active_subscribers: number;
  mrr_cents: number;
  plan_distribution: { plan_name: string; plan_slug: string; count: number }[];
}

export interface MetricsProducts {
  products: MetricsProductItem[];
}

// ─── Webhook Types ──────────────────────────────────────────────────────────

export interface WebhookEvent {
  id: number;
  event_id: string;
  event_type: string;
  processed: boolean;
  error_message: string;
  created_at: string | null;
}

export interface WebhookListResponse {
  items: WebhookEvent[];
  total: number;
  failed_count: number;
}

// ─── Audit Log Types ────────────────────────────────────────────────────────

export interface AuditLogEntry {
  id: number;
  admin_user_id: number;
  admin_email: string;
  action: string;
  method: string;
  path: string;
  ip_address: string | null;
  status_code: number | null;
  details: Record<string, unknown>;
  timestamp: string | null;
}

export interface AuditLogListResponse extends PaginatedResponse<AuditLogEntry> {}

// ─── API Functions ──────────────────────────────────────────────────────────

export const adminApi = {
  // ═══════════════════════════════════════════════════════════
  //  API Keys
  // ═══════════════════════════════════════════════════════════

  async listApiKeys(params?: {
    page?: number;
    page_size?: number;
    service_domain_id?: number;
    is_active?: boolean;
  }): Promise<ApiKeyListResponse> {
    const queryParams: Record<string, string | number | boolean> = {};
    if (params?.page) queryParams.page = params.page;
    if (params?.page_size) queryParams.page_size = params.page_size;
    if (params?.service_domain_id !== undefined)
      queryParams.service_domain_id = params.service_domain_id;
    if (params?.is_active !== undefined)
      queryParams.is_active = params.is_active;

    return apiClient.get<ApiKeyListResponse>("/admin/api-keys/", {
      params: queryParams,
    });
  },

  async createApiKey(
    payload: ApiKeyCreatePayload,
  ): Promise<ApiKeyCreateResponse> {
    return apiClient.post<ApiKeyCreateResponse>("/admin/api-keys/", payload);
  },

  async revokeApiKey(keyId: number): Promise<{ message: string }> {
    return apiClient.patch<{ message: string }>(
      `/admin/api-keys/${keyId}/revoke`,
    );
  },

  async rotateApiKey(keyId: number): Promise<ApiKeyRotateResponse> {
    return apiClient.post<ApiKeyRotateResponse>(
      `/admin/api-keys/${keyId}/rotate`,
    );
  },

  async fetchServiceDomains(): Promise<ServiceDomainOption[]> {
    const domains = await apiClient.get<ServiceDomainOption[]>(
      "/admin/api-keys/service-domains",
    );
    return domains || [];
  },

  // ═══════════════════════════════════════════════════════════
  //  Products
  // ═══════════════════════════════════════════════════════════

  async listProducts(params?: {
    page?: number;
    page_size?: number;
    is_active?: boolean;
  }): Promise<ProductListResponse> {
    return apiClient.get<ProductListResponse>("/admin/products", { params });
  },

  async getProduct(productId: number): Promise<ProductDetail> {
    return apiClient.get<ProductDetail>(`/admin/products/${productId}`);
  },

  async createProduct(payload: ProductCreatePayload): Promise<ProductDetail> {
    return apiClient.post<ProductDetail>("/admin/products", payload);
  },

  async updateProduct(
    productId: number,
    payload: ProductUpdatePayload,
  ): Promise<ProductDetail> {
    return apiClient.put<ProductDetail>(
      `/admin/products/${productId}`,
      payload,
    );
  },

  async toggleProduct(productId: number): Promise<{ message: string }> {
    return apiClient.patch<{ message: string }>(
      `/admin/products/${productId}/toggle`,
    );
  },

  async deleteProduct(productId: number): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(
      `/admin/products/${productId}`,
    );
  },

  // ═══════════════════════════════════════════════════════════
  //  Service Domains
  // ═══════════════════════════════════════════════════════════

  async addServiceDomain(
    productId: number,
    payload: ServiceDomainCreatePayload,
  ): Promise<ServiceDomainDetail> {
    return apiClient.post<ServiceDomainDetail>(
      `/admin/products/${productId}/domains`,
      payload,
    );
  },

  async updateServiceDomain(
    domainId: number,
    payload: ServiceDomainUpdatePayload,
  ): Promise<ServiceDomainDetail> {
    return apiClient.put<ServiceDomainDetail>(
      `/admin/domains/${domainId}`,
      payload,
    );
  },

  async deleteServiceDomain(domainId: number): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(`/admin/domains/${domainId}`);
  },

  // ═══════════════════════════════════════════════════════════
  //  Plans
  // ═══════════════════════════════════════════════════════════

  async listPlans(
    productId: number,
    params?: {
      page?: number;
      page_size?: number;
      is_active?: boolean;
    },
  ): Promise<PlanListResponse> {
    return apiClient.get<PlanListResponse>(
      `/admin/products/${productId}/plans`,
      { params },
    );
  },

  async getPlan(planId: number): Promise<PlanDetail> {
    return apiClient.get<PlanDetail>(`/admin/plans/${planId}`);
  },

  async createPlan(
    productId: number,
    payload: PlanCreatePayload,
  ): Promise<PlanDetail> {
    return apiClient.post<PlanDetail>(
      `/admin/products/${productId}/plans`,
      payload,
    );
  },

  async updatePlan(
    planId: number,
    payload: PlanUpdatePayload,
  ): Promise<PlanDetail> {
    return apiClient.put<PlanDetail>(`/admin/plans/${planId}`, payload);
  },

  async togglePlan(planId: number): Promise<{ message: string }> {
    return apiClient.patch<{ message: string }>(
      `/admin/plans/${planId}/toggle`,
    );
  },

  async togglePlanFeature(planId: number): Promise<{ message: string }> {
    return apiClient.patch<{ message: string }>(
      `/admin/plans/${planId}/feature`,
    );
  },

  async duplicatePlan(planId: number): Promise<PlanDetail> {
    return apiClient.post<PlanDetail>(`/admin/plans/${planId}/duplicate`);
  },

  async deletePlan(planId: number): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(`/admin/plans/${planId}`);
  },

  // ═══════════════════════════════════════════════════════════
  //  Access Entries
  // ═══════════════════════════════════════════════════════════

  async addAccessEntry(
    planId: number,
    payload: AccessEntryCreatePayload,
  ): Promise<AccessEntryItem> {
    return apiClient.post<AccessEntryItem>(
      `/admin/plans/${planId}/access-entries`,
      payload,
    );
  },

  async updateAccessEntry(
    entryId: number,
    payload: AccessEntryUpdatePayload,
  ): Promise<AccessEntryItem> {
    return apiClient.put<AccessEntryItem>(
      `/admin/access-entries/${entryId}`,
      payload,
    );
  },

  async deleteAccessEntry(entryId: number): Promise<{ message: string }> {
    return apiClient.delete<{ message: string }>(
      `/admin/access-entries/${entryId}`,
    );
  },

  async bulkSetAccessEntries(
    planId: number,
    payload: AccessEntryBulkPayload,
  ): Promise<AccessEntryItem[]> {
    return apiClient.post<AccessEntryItem[]>(
      `/admin/plans/${planId}/access-entries/bulk`,
      payload,
    );
  },

  async getAccessMatrix(productId: number): Promise<AccessMatrixResponse> {
    return apiClient.get<AccessMatrixResponse>(
      `/admin/products/${productId}/access-matrix`,
    );
  },

  async saveAccessMatrixRow(
    productId: number,
    payload: AccessMatrixRowSavePayload,
  ): Promise<AccessMatrixRowSaveResponse> {
    return apiClient.put<AccessMatrixRowSaveResponse>(
      `/admin/products/${productId}/access-matrix/row`,
      payload,
    );
  },

  // ═══════════════════════════════════════════════════════════
  //  Subscriptions
  // ═══════════════════════════════════════════════════════════

  async listSubscriptions(params?: {
    page?: number;
    page_size?: number;
    product_id?: number;
    plan_id?: number;
    status?: string;
    search?: string;
  }): Promise<SubscriptionListResponse> {
    return apiClient.get<SubscriptionListResponse>("/admin/subscriptions", {
      params,
    });
  },

  async getSubscription(subscriptionId: number): Promise<SubscriptionDetail> {
    return apiClient.get<SubscriptionDetail>(
      `/admin/subscriptions/${subscriptionId}`,
    );
  },

  async overrideSubscription(
    subscriptionId: number,
    payload: SubscriptionOverridePayload,
  ): Promise<SubscriptionDetail> {
    return apiClient.patch<SubscriptionDetail>(
      `/admin/subscriptions/${subscriptionId}/override`,
      payload,
    );
  },

  async cancelSubscription(
    subscriptionId: number,
  ): Promise<SubscriptionDetail> {
    return apiClient.patch<SubscriptionDetail>(
      `/admin/subscriptions/${subscriptionId}/cancel`,
    );
  },

  async expireSubscription(
    subscriptionId: number,
  ): Promise<SubscriptionDetail> {
    return apiClient.patch<SubscriptionDetail>(
      `/admin/subscriptions/${subscriptionId}/expire`,
    );
  },

  async extendSubscription(
    subscriptionId: number,
    payload: SubscriptionExtendPayload,
  ): Promise<SubscriptionDetail> {
    return apiClient.patch<SubscriptionDetail>(
      `/admin/subscriptions/${subscriptionId}/extend`,
      payload,
    );
  },

  async getSubscriptionPlanChanges(
    subscriptionId: number,
  ): Promise<PlanChangeItem[]> {
    const data = await apiClient.get<PaginatedResponse<PlanChangeItem>>(
      `/admin/subscriptions/${subscriptionId}/plan-changes`,
      { params: { page: 1, page_size: 100 } },
    );
    return data.results ?? [];
  },

  async getSubscriptionInvoices(
    subscriptionId: number,
  ): Promise<InvoiceItem[]> {
    const data = await apiClient.get<PaginatedResponse<InvoiceItem>>(
      `/admin/subscriptions/${subscriptionId}/invoices`,
      { params: { page: 1, page_size: 100 } },
    );
    return data.results ?? [];
  },

  async getSubscriptionRefunds(subscriptionId: number): Promise<RefundItem[]> {
    const data = await apiClient.get<PaginatedResponse<RefundItem>>(
      `/admin/subscriptions/${subscriptionId}/refunds`,
      { params: { page: 1, page_size: 100 } },
    );
    return data.results ?? [];
  },

  async issueRefund(
    subscriptionId: number,
    payload: IssueRefundPayload,
  ): Promise<IssueRefundResponse> {
    return apiClient.post<IssueRefundResponse>(
      `/admin/subscriptions/${subscriptionId}/refund`,
      payload,
    );
  },

  // ═══════════════════════════════════════════════════════════
  //  Users
  // ═══════════════════════════════════════════════════════════

  async listUsers(params?: {
    page?: number;
    page_size?: number;
    role?: string;
    is_active?: boolean;
    email_verified?: boolean;
    search?: string;
  }): Promise<UserListResponse> {
    return apiClient.get<UserListResponse>("/admin/users", { params });
  },

  async getUser(userId: number): Promise<UserDetail> {
    return apiClient.get<UserDetail>(`/admin/users/${userId}`);
  },

  async updateUserStatus(
    userId: number,
    payload: UserStatusPayload,
  ): Promise<UserDetail> {
    return apiClient.patch<UserDetail>(
      `/admin/users/${userId}/status`,
      payload,
    );
  },

  async updateUserRole(
    userId: number,
    payload: UserRolePayload,
  ): Promise<UserDetail> {
    return apiClient.patch<UserDetail>(`/admin/users/${userId}/role`, payload);
  },

  async getUserAudit(
    userId: number,
    params?: {
      page?: number;
      page_size?: number;
    },
  ): Promise<PaginatedResponse<UserAuditEntry>> {
    return apiClient.get<PaginatedResponse<UserAuditEntry>>(
      `/admin/users/${userId}/audit`,
      { params },
    );
  },

  // ═══════════════════════════════════════════════════════════
  //  Refunds
  // ═══════════════════════════════════════════════════════════

  async listRefunds(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    reason_category?: string;
    subscription_id?: number;
    date_from?: string;
    date_to?: string;
  }): Promise<RefundListResponse> {
    return apiClient.get<RefundListResponse>("/admin/refunds", { params });
  },

  async approveRefund(
    refundId: number,
    payload: RefundApprovalPayload,
  ): Promise<{ message: string }> {
    return apiClient.patch<{ message: string }>(
      `/admin/refunds/${refundId}/approve`,
      payload,
    );
  },

  async rejectRefund(
    refundId: number,
    payload: RefundApprovalPayload,
  ): Promise<{ message: string }> {
    return apiClient.patch<{ message: string }>(
      `/admin/refunds/${refundId}/reject`,
      payload,
    );
  },

  // ═══════════════════════════════════════════════════════════
  //  Metrics
  // ═══════════════════════════════════════════════════════════

  async getMetricsOverview(): Promise<MetricsOverview> {
    return apiClient.get<MetricsOverview>("/admin/metrics/overview");
  },

  async getMetricsRevenue(params?: {
    period?: string;
    product_id?: number;
  }): Promise<MetricsRevenue> {
    return apiClient.get<MetricsRevenue>("/admin/metrics/revenue", { params });
  },

  async getMetricsSubscriptions(params?: {
    period?: string;
  }): Promise<MetricsSubscriptions> {
    return apiClient.get<MetricsSubscriptions>("/admin/metrics/subscriptions", {
      params,
    });
  },

  async getMetricsProducts(): Promise<MetricsProducts> {
    return apiClient.get<MetricsProducts>("/admin/metrics/products");
  },

  // ═══════════════════════════════════════════════════════════
  //  Webhooks
  // ═══════════════════════════════════════════════════════════

  async listWebhooks(params?: {
    page?: number;
    page_size?: number;
    event_type?: string;
    processed?: boolean;
  }): Promise<WebhookListResponse> {
    return apiClient.get<WebhookListResponse>("/admin/webhooks", { params });
  },

  async retryWebhook(webhookId: number): Promise<{
    id: number;
    event_id: string;
    event_type: string;
    processed: boolean;
    error_message: string;
    message: string;
  }> {
    return apiClient.post<{
      id: number;
      event_id: string;
      event_type: string;
      processed: boolean;
      error_message: string;
      message: string;
    }>(`/admin/webhooks/${webhookId}/retry`);
  },

  // ═══════════════════════════════════════════════════════════
  //  Audit Log
  // ═══════════════════════════════════════════════════════════

  async listAuditLog(params?: {
    page?: number;
    page_size?: number;
    admin_user_id?: number;
    action?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<AuditLogListResponse> {
    return apiClient.get<AuditLogListResponse>("/admin/audit-log", { params });
  },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Format an API key prefix for display (truncate + ellipsis).
 */
export function formatKeyPrefix(prefix: string): string {
  if (!prefix) return "—";
  if (prefix.length <= 14) return prefix;
  return prefix.slice(0, 14) + "...";
}

/**
 * Format a datetime string for display.
 */
export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Never";
  const locale =
    typeof navigator !== "undefined" ? navigator.language : "en-US";
  return new Date(dateStr).toLocaleDateString(locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Format a relative time string (e.g., "2 hours ago", "3 days ago").
 */
export function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Never";
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return "just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 30) return `${diffDays}d ago`;
  return formatDateTime(dateStr);
}

/**
 * Get a status badge color class for subscription status.
 */
export function getSubscriptionStatusColor(status: string): {
  bg: string;
  text: string;
} {
  switch (status) {
    case "active":
      return {
        bg: "bg-green-100 dark:bg-green-950",
        text: "text-green-700 dark:text-green-400",
      };
    case "trialing":
      return {
        bg: "bg-blue-100 dark:bg-blue-950",
        text: "text-blue-700 dark:text-blue-400",
      };
    case "past_due":
      return {
        bg: "bg-amber-100 dark:bg-amber-950",
        text: "text-amber-700 dark:text-amber-400",
      };
    case "canceled":
      return {
        bg: "bg-gray-100 dark:bg-gray-900",
        text: "text-gray-600 dark:text-gray-400",
      };
    case "expired":
      return {
        bg: "bg-red-100 dark:bg-red-950",
        text: "text-red-700 dark:text-red-400",
      };
    case "paused":
      return {
        bg: "bg-orange-100 dark:bg-orange-950",
        text: "text-orange-700 dark:text-orange-400",
      };
    default:
      return {
        bg: "bg-gray-100 dark:bg-gray-900",
        text: "text-gray-600 dark:text-gray-400",
      };
  }
}

/**
 * Get a status badge color class for refund status.
 */
export function getRefundStatusColor(status: string): {
  bg: string;
  text: string;
} {
  switch (status) {
    case "pending":
      return {
        bg: "bg-amber-100 dark:bg-amber-950",
        text: "text-amber-700 dark:text-amber-400",
      };
    case "completed":
      return {
        bg: "bg-green-100 dark:bg-green-950",
        text: "text-green-700 dark:text-green-400",
      };
    case "approved":
      return {
        bg: "bg-blue-100 dark:bg-blue-950",
        text: "text-blue-700 dark:text-blue-400",
      };
    case "processed":
      return {
        bg: "bg-green-100 dark:bg-green-950",
        text: "text-green-700 dark:text-green-400",
      };
    case "rejected":
      return {
        bg: "bg-red-100 dark:bg-red-950",
        text: "text-red-700 dark:text-red-400",
      };
    case "failed":
      return {
        bg: "bg-red-100 dark:bg-red-950",
        text: "text-red-700 dark:text-red-400",
      };
    default:
      return {
        bg: "bg-gray-100 dark:bg-gray-900",
        text: "text-gray-600 dark:text-gray-400",
      };
  }
}

/**
 * Get a status badge color class for webhook status.
 */
export function getWebhookStatusColor(status: string): {
  bg: string;
  text: string;
} {
  switch (status) {
    case "processed":
      return {
        bg: "bg-green-100 dark:bg-green-950",
        text: "text-green-700 dark:text-green-400",
      };
    case "pending":
      return {
        bg: "bg-amber-100 dark:bg-amber-950",
        text: "text-amber-700 dark:text-amber-400",
      };
    case "failed":
      return {
        bg: "bg-red-100 dark:bg-red-950",
        text: "text-red-700 dark:text-red-400",
      };
    default:
      return {
        bg: "bg-gray-100 dark:bg-gray-900",
        text: "text-gray-600 dark:text-gray-400",
      };
  }
}
