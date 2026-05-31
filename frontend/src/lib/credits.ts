/**
 * Credit API client — types and functions for the credit system.
 *
 * Covers:
 *   - User-facing: GET /billing/credits, GET /billing/credits/invoices
 *   - Admin: GET/POST /admin/credits, POST /admin/credits/{id}/refund, etc.
 *
 * Usage in Vue components:
 *   import { creditsApi } from "@/lib/credits";
 *   const myCredits = await creditsApi.getMyCredits();
 */

import { apiClient } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CreditPool {
  id: number;
  plan_name: string;
  plan_slug: string;
  product_name: string;
  amount_cents: number;
  display_amount: string;
  currency: string;
  credit_periods: number;
  periods_consumed: number;
  periods_remaining: number;
  source: string;
  payment_reference: string;
  status: string;
  is_effectively_active: boolean;
  current_period_start: string | null;
  current_period_end: string | null;
  expires_at: string | null;
  created_at: string | null;
}

export interface CreditInvoice {
  id: number;
  invoice_number: string;
  status: string;
  amount_cents: number;
  tax_cents: number;
  total_cents: number;
  currency: string;
  plan_name: string;
  plan_slug: string;
  product_name: string;
  period_start: string | null;
  period_end: string | null;
  payment_reference: string;
  issued_at: string | null;
  created_at: string | null;
}

export interface CreditTransaction {
  id: number;
  action: string;
  periods_delta: number;
  amount_cents_delta: number;
  periods_balance: number;
  reason: string;
  created_at: string;
}

export interface CreditPurchaseResponse {
  pool: CreditPool;
  invoice: CreditInvoice;
  message: string;
}

export interface PaginationMeta {
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface AdminCreditPurchasePayload {
  user_email: string;
  product_slug: string;
  plan_slug: string;
  amount_cents: number;
  currency?: string;
  source?: string;
  payment_reference?: string;
  tax_cents?: number;
  notes?: string;
}

export interface AdminCreditRefundPayload {
  reason: string;
}

export interface AdminCreditAdjustPayload {
  periods_delta: number;
  reason: string;
  amount_cents_delta?: number;
}

export interface CreditRequestInputSchema {
  product_slug: string;
  plan_slug: string;
  amount_cents: number;
  currency?: string;
  bank_name: string;
  account_holder_name: string;
  account_number: string;
  routing_number?: string;
  transaction_reference: string;
  payment_proof_note?: string;
}

export interface CreditRequest {
  id: number;
  user_email: string;
  product_name: string;
  plan_name: string;
  plan_slug: string;
  amount_cents: number;
  currency: string;
  bank_name: string;
  account_holder_name: string;
  account_number: string;
  routing_number: string;
  transaction_reference: string;
  payment_proof_note: string;
  status: string;
  created_at: string;
  reviewed_at: string | null;
  review_note: string;
  created_credit_pool_id: number | null;
}

export interface Product {
  slug: string;
  name: string;
}

export interface Plan {
  slug: string;
  name: string;
  display_price: string;
}

// ─── User-Facing API Functions ───────────────────────────────────────────────

export const creditsApi = {
  async getMyCredits(): Promise<CreditPool[]> {
    return apiClient.get<CreditPool[]>("/billing/credits");
  },

  async getMyCreditInvoices(): Promise<CreditInvoice[]> {
    return apiClient.get<CreditInvoice[]>("/billing/credits/invoices");
  },

  // ── Admin API Functions ────────────────────────────────────────────────────

  async adminListCredits(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    source?: string;
    product_id?: number;
    search?: string;
  }): Promise<PaginatedResponse<CreditPool>> {
    return apiClient.get<PaginatedResponse<CreditPool>>("/admin/credits", { params });
  },

  async adminGetCreditPool(creditId: number): Promise<CreditPool & { transactions: CreditTransaction[] }> {
    return apiClient.get<CreditPool & { transactions: CreditTransaction[] }>(
      `/admin/credits/${creditId}`
    );
  },

  async adminPurchaseCredit(
    payload: AdminCreditPurchasePayload
  ): Promise<CreditPurchaseResponse> {
    return apiClient.post<CreditPurchaseResponse>("/admin/credits", payload);
  },

  async adminRefundCredit(
    creditId: number,
    payload: AdminCreditRefundPayload
  ): Promise<{ id: number; status: string; periods_remaining: number; message: string }> {
    return apiClient.post(`/admin/credits/${creditId}/refund`, payload);
  },

  async adminAdjustCredit(
    creditId: number,
    payload: AdminCreditAdjustPayload
  ): Promise<{ id: number; credit_periods: number; periods_remaining: number; status: string; message: string }> {
    return apiClient.post(`/admin/credits/${creditId}/adjust`, payload);
  },

  async adminListCreditInvoices(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    search?: string;
  }): Promise<PaginatedResponse<CreditInvoice>> {
    return apiClient.get<PaginatedResponse<CreditInvoice>>("/admin/credit-invoices", {
      params,
    });
  },

  async adminGetCreditInvoice(
    invoiceNumber: string
  ): Promise<CreditInvoice> {
    return apiClient.get<CreditInvoice>(
      `/admin/credit-invoices/${invoiceNumber}`
    );
  },

  // ── Credit Request API Functions ────────────────────────────────────────────

  async getProducts(): Promise<Product[]> {
    return apiClient.get<Product[]>("/billing/products");
  },

  async getPlans(productSlug: string): Promise<Plan[]> {
    return apiClient.get<Plan[]>(`/billing/plans/${productSlug}`);
  },

  async requestCreditPurchase(
    payload: CreditRequestInputSchema
  ): Promise<{ id: number; status: string; message: string }> {
    return apiClient.post<{ id: number; status: string; message: string }>(
      "/billing/credits/request",
      payload
    );
  },

  async adminListCreditRequests(params?: {
    page?: number;
    page_size?: number;
    status?: string;
    search?: string;
  }): Promise<{ meta: PaginationMeta; results: CreditRequest[] }> {
    return apiClient.get<{ meta: PaginationMeta; results: CreditRequest[] }>(
      "/admin/credit-requests",
      { params }
    );
  },

  async adminGetCreditRequest(requestId: number): Promise<CreditRequest> {
    return apiClient.get<CreditRequest>(`/admin/credit-requests/${requestId}`);
  },

  async adminApproveCreditRequest(
    requestId: number
  ): Promise<{ id: number; status: string; credit_pool_id: number; invoice_number: string; message: string }> {
    return apiClient.post(
      `/admin/credit-requests/${requestId}/approve`,
      {}
    );
  },

  async adminRejectCreditRequest(
    requestId: number,
    reason: string
  ): Promise<{ id: number; status: string; message: string }> {
    return apiClient.post(
      `/admin/credit-requests/${requestId}/reject`,
      { reason }
    );
  },
};
