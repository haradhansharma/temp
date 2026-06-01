<script setup lang="ts">
/**
 * CreditRequestClient — Form for users to request credits via bank transfer.
 *
 * Features:
 *   - Product and plan selection with dynamic price display
 *   - Multiple bank account selection from BankSettings
 *   - Transaction reference and proof of payment upload
 *   - Form validation and submission with loading states
 *
 * Used on: /dashboard/billing/credits/request
 */

import { ref, computed, onMounted, watch } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { creditsApi } from "@/lib/credits";
import type { Product, Plan, CreditRequestInputSchema } from "@/lib/credits";

// ─── Types ───────────────────────────────────────────────────────────────────

interface BankAccount {
  id: number;
  bank_name: string;
  account_holder_name: string;
  account_number: string;
  routing_number: string;
}

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const submitting = ref(false);
const loadError = ref<string | null>(null);

const products = ref<Product[]>([]);
const plans = ref<Plan[]>([]);
const bankAccounts = ref<BankAccount[]>([]);
const selectedBankId = ref<number | null>(null);

// Form state
const form = ref<{
  product_slug: string;
  plan_slug: string;
  amount_cents: number;
  currency: string;
  bank_name: string;
  account_holder_name: string;
  account_number: string;
  routing_number: string;
  transaction_reference: string;
  payment_proof_note: string;
}>({
  product_slug: "",
  plan_slug: "",
  amount_cents: 0,
  currency: "USD",
  bank_name: "",
  account_holder_name: "",
  account_number: "",
  routing_number: "",
  transaction_reference: "",
  payment_proof_note: "",
});

const formErrors = ref<Record<string, string>>({});
const submitted = ref(false);
const requestId = ref<number | null>(null);

// ─── Computed ────────────────────────────────────────────────────────────────

const selectedProduct = computed(() =>
  products.value.find((p) => p.slug === form.value.product_slug)
);

const selectedPlan = computed(() =>
  plans.value.find((p) => p.slug === form.value.plan_slug)
);

const selectedBank = computed(() =>
  bankAccounts.value.find((b) => b.id === selectedBankId.value)
);

const canSubmit = computed(() => {
  return (
    bankAccounts.value.length > 0 &&
    selectedBankId.value !== null &&
    form.value.product_slug &&
    form.value.plan_slug &&
    form.value.amount_cents > 0 &&
    form.value.bank_name.trim() &&
    form.value.account_holder_name.trim() &&
    form.value.account_number.trim() &&
    form.value.transaction_reference.trim() &&
    !submitting.value
  );
});

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchInitialData();
});

async function fetchInitialData() {
  loading.value = true;
  loadError.value = null;
  try {
    const [productsData, bankData] = await Promise.all([
      creditsApi.getProducts(),
      fetchBankSettings(),
    ]);
    products.value = productsData;
    
    if (bankData.length > 0) {
      bankAccounts.value = bankData;
      // Auto-select first bank
      selectedBankId.value = bankData[0].id;
      updateFormFromBank(bankData[0]);
    }
  } catch (err) {
    loadError.value = getErrorMessage(err);
    showToast("Failed to load data", "error");
  } finally {
    loading.value = false;
  }
}

async function fetchBankSettings(): Promise<BankAccount[]> {
  try {
    const data = await creditsApi.getBankSettings();
    if (data && data.active && data.banks) {
      return data.banks;
    }
    return [];
  } catch {
    return [];
  }
}

function updateFormFromBank(bank: BankAccount) {
  form.value.bank_name = bank.bank_name || "";
  form.value.account_holder_name = bank.account_holder_name || "";
  form.value.account_number = bank.account_number || "";
  form.value.routing_number = bank.routing_number || "";
}

function onBankChange() {
  const bank = selectedBank.value;
  if (bank) {
    updateFormFromBank(bank);
  }
}

// ─── Watchers ────────────────────────────────────────────────────────────────

watch(
  () => form.value.product_slug,
  async (productSlug) => {
    if (!productSlug) {
      plans.value = [];
      form.value.plan_slug = "";
      return;
    }
    try {
      plans.value = await creditsApi.getPlans(productSlug);
      // Auto-select first plan
      if (plans.value.length > 0 && !form.value.plan_slug) {
        form.value.plan_slug = plans.value[0].slug;
      }
    } catch (err) {
      showToast("Failed to load plans", "error");
    }
  }
);

watch(
  () => form.value.plan_slug,
  (planSlug) => {
    const plan = plans.value.find((p) => p.slug === planSlug);
    if (plan) {
      // Parse display_price to get cents (e.g., "$9.00" -> 900)
      const match = plan.display_price.match(/\$?([\d,]+\.?\d*)/);
      if (match) {
        const dollars = parseFloat(match[1].replace(/,/g, ""));
        form.value.amount_cents = Math.round(dollars * 100);
      }
    }
  }
);

// ─── Form Handling ───────────────────────────────────────────────────────────

function validateForm(): boolean {
  formErrors.value = {};

  if (!form.value.product_slug) {
    formErrors.value.product_slug = "Please select a product";
  }
  if (!form.value.plan_slug) {
    formErrors.value.plan_slug = "Please select a plan";
  }
  if (form.value.amount_cents <= 0) {
    formErrors.value.amount_cents = "Amount must be greater than zero";
  }
  if (!form.value.bank_name.trim()) {
    formErrors.value.bank_name = "Bank name is required";
  }
  if (!form.value.account_holder_name.trim()) {
    formErrors.value.account_holder_name = "Account holder name is required";
  }
  if (!form.value.account_number.trim()) {
    formErrors.value.account_number = "Account number is required";
  }
  if (!form.value.transaction_reference.trim()) {
    formErrors.value.transaction_reference = "Transaction reference is required";
  }

  return Object.keys(formErrors.value).length === 0;
}

async function handleSubmit() {
  if (!validateForm()) {
    showToast("Please fix the errors below", "error");
    return;
  }

  submitting.value = true;
  try {
    const payload: CreditRequestInputSchema = {
      product_slug: form.value.product_slug,
      plan_slug: form.value.plan_slug,
      amount_cents: form.value.amount_cents,
      currency: form.value.currency,
      bank_name: form.value.bank_name,
      account_holder_name: form.value.account_holder_name,
      account_number: form.value.account_number,
      routing_number: form.value.routing_number,
      transaction_reference: form.value.transaction_reference,
      payment_proof_note: form.value.payment_proof_note,
    };

    const result = await creditsApi.requestCreditPurchase(payload);
    requestId.value = result.id;
    submitted.value = true;
    showToast("Credit request submitted successfully", "success");
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    submitting.value = false;
  }
}

function resetForm() {
  const bank = selectedBank.value;
  form.value = {
    product_slug: "",
    plan_slug: "",
    amount_cents: 0,
    currency: "USD",
    bank_name: bank?.bank_name || "",
    account_holder_name: bank?.account_holder_name || "",
    account_number: bank?.account_number || "",
    routing_number: bank?.routing_number || "",
    transaction_reference: "",
    payment_proof_note: "",
  };
  formErrors.value = {};
  submitted.value = false;
  requestId.value = null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat(navigator.language, {
    style: "currency",
    currency: currency,
  }).format(cents / 100);
}
</script>

<template>
  <div>
    <!-- Page Header -->
    <div class="mb-8">
      <nav class="mb-2 text-sm text-[var(--color-muted-foreground)]">
        <a href="/dashboard/billing/credits" class="hover:text-foreground transition-colors">Credits</a>
        <span class="mx-2">/</span>
        <span>Request</span>
      </nav>
      <h1 class="text-2xl font-bold tracking-tight md:text-3xl">Request Credits</h1>
      <p class="mt-1 text-[var(--color-muted-foreground)]">
        Pay via bank transfer and receive credits for your subscription.
      </p>
    </div>

    <!-- Loading Skeleton -->
    <template v-if="loading">
      <div class="grid gap-6 lg:grid-cols-2">
        <div class="card p-6 animate-pulse">
          <div class="h-5 w-32 rounded bg-[var(--color-muted)] mb-4"></div>
          <div class="space-y-4">
            <div v-for="i in 4" :key="i" class="h-10 rounded bg-[var(--color-muted)]"></div>
          </div>
        </div>
        <div class="card p-6 animate-pulse">
          <div class="h-5 w-40 rounded bg-[var(--color-muted)] mb-4"></div>
          <div class="space-y-3">
            <div v-for="i in 5" :key="i" class="h-4 rounded bg-[var(--color-muted)]"></div>
          </div>
        </div>
      </div>
    </template>

    <!-- Error State -->
    <template v-else-if="loadError">
      <div class="card flex flex-col items-center justify-center py-16 text-center px-6">
        <div class="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-950">
          <svg class="h-8 w-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h3 class="text-lg font-semibold text-red-800 dark:text-red-300">Failed to Load</h3>
        <p class="mt-2 text-sm text-[var(--color-muted-foreground)] max-w-sm">{{ loadError }}</p>
        <button class="btn-secondary mt-4" @click="fetchInitialData">Try Again</button>
      </div>
    </template>

    <!-- Success State -->
    <template v-else-if="submitted">
      <div class="card p-8 text-center max-w-lg mx-auto">
        <div class="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-950 mx-auto">
          <svg class="h-8 w-8 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 class="text-xl font-bold text-green-800 dark:text-green-300">Request Submitted</h2>
        <p class="mt-3 text-[var(--color-muted-foreground)]">
          Your credit request has been submitted successfully. Our team will review your payment and approve your credits within 1-2 business days.
        </p>
        <div class="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
          <a href="/dashboard/billing/credits" class="btn-primary">
            View My Credits
          </a>
          <button class="btn-secondary" @click="resetForm">
            Submit Another Request
          </button>
        </div>
      </div>
    </template>

    <!-- Form -->
    <template v-else>
      <div class="grid gap-6 lg:grid-cols-2">
        <!-- Left Column: Form -->
        <div class="card p-6">
          <h2 class="text-lg font-semibold mb-4">Payment Details</h2>

          <form @submit.prevent="handleSubmit" class="space-y-5">
            <!-- Product Selection -->
            <div>
              <label class="block text-sm font-medium mb-1.5">
                Product <span class="text-red-500">*</span>
              </label>
              <select
                v-model="form.product_slug"
                class="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                :class="{ 'border-red-500': formErrors.product_slug }"
              >
                <option value="">Select a product...</option>
                <option v-for="product in products" :key="product.slug" :value="product.slug">
                  {{ product.name }}
                </option>
              </select>
              <p v-if="formErrors.product_slug" class="mt-1 text-xs text-red-500">{{ formErrors.product_slug }}</p>
            </div>

            <!-- Plan Selection -->
            <div>
              <label class="block text-sm font-medium mb-1.5">
                Plan <span class="text-red-500">*</span>
              </label>
              <select
                v-model="form.plan_slug"
                class="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                :class="{ 'border-red-500': formErrors.plan_slug }"
                :disabled="!form.product_slug"
              >
                <option value="">Select a plan...</option>
                <option v-for="plan in plans" :key="plan.slug" :value="plan.slug">
                  {{ plan.name }} — {{ plan.display_price }}
                </option>
              </select>
              <p v-if="formErrors.plan_slug" class="mt-1 text-xs text-red-500">{{ formErrors.plan_slug }}</p>
            </div>

            <!-- Amount Display -->
            <div v-if="form.amount_cents > 0" class="rounded-lg bg-[var(--color-muted)] p-4">
              <p class="text-sm text-[var(--color-muted-foreground)]">Amount to Pay</p>
              <p class="text-2xl font-bold mt-1">{{ formatPrice(form.amount_cents, form.currency) }}</p>
            </div>

            <!-- Divider -->
            <div class="border-t border-border pt-5">
              <h3 class="text-sm font-semibold text-[var(--color-muted-foreground)] uppercase tracking-wider mb-4">
                Bank Transfer Information
              </h3>
            </div>

            <!-- Bank Name -->
            <div>
              <label class="block text-sm font-medium mb-1.5">
                Bank Name <span class="text-red-500">*</span>
              </label>
              <input
                v-model="form.bank_name"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                :class="{ 'border-red-500': formErrors.bank_name }"
                placeholder="Enter bank name"
              />
              <p v-if="formErrors.bank_name" class="mt-1 text-xs text-red-500">{{ formErrors.bank_name }}</p>
            </div>

            <!-- Account Holder Name -->
            <div>
              <label class="block text-sm font-medium mb-1.5">
                Account Holder Name <span class="text-red-500">*</span>
              </label>
              <input
                v-model="form.account_holder_name"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                :class="{ 'border-red-500': formErrors.account_holder_name }"
                placeholder="Account holder name"
              />
              <p v-if="formErrors.account_holder_name" class="mt-1 text-xs text-red-500">{{ formErrors.account_holder_name }}</p>
            </div>

            <!-- Account Number -->
            <div>
              <label class="block text-sm font-medium mb-1.5">
                Account Number <span class="text-red-500">*</span>
              </label>
              <input
                v-model="form.account_number"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                :class="{ 'border-red-500': formErrors.account_number }"
                placeholder="Enter account number"
              />
              <p v-if="formErrors.account_number" class="mt-1 text-xs text-red-500">{{ formErrors.account_number }}</p>
            </div>

            <!-- Routing Number -->
            <div>
              <label class="block text-sm font-medium mb-1.5">Routing Number</label>
              <input
                v-model="form.routing_number"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                placeholder="Optional"
              />
            </div>

            <!-- Transaction Reference -->
            <div>
              <label class="block text-sm font-medium mb-1.5">
                Transaction Reference <span class="text-red-500">*</span>
              </label>
              <input
                v-model="form.transaction_reference"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600"
                :class="{ 'border-red-500': formErrors.transaction_reference }"
                placeholder="e.g., TXN-20260601-001"
              />
              <p class="mt-1 text-xs text-[var(--color-muted-foreground)]">
                Enter the reference number from your bank transfer receipt
              </p>
              <p v-if="formErrors.transaction_reference" class="mt-1 text-xs text-red-500">{{ formErrors.transaction_reference }}</p>
            </div>

            <!-- Payment Proof Note -->
            <div>
              <label class="block text-sm font-medium mb-1.5">Additional Notes</label>
              <textarea
                v-model="form.payment_proof_note"
                rows="3"
                class="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-brand-600 focus:outline-none focus:ring-1 focus:ring-brand-600 resize-none"
                placeholder="Any additional information about your payment..."
              />
            </div>

            <!-- Submit Button -->
            <div class="pt-2">
              <button
                type="submit"
                :disabled="!canSubmit"
                class="btn-primary w-full"
              >
                <svg v-if="submitting" class="h-4 w-4 mr-2 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ submitting ? "Submitting..." : "Submit Request" }}
              </button>
              <p v-if="bankAccounts.length === 0" class="mt-2 text-xs text-center text-amber-600 dark:text-amber-400">
                Bank transfer payments are not available at this time.
              </p>
            </div>
          </form>
        </div>

        <!-- Right Column: Instructions -->
        <div class="space-y-6">
          <!-- Bank Details Cards -->
          <div v-if="bankAccounts.length > 0" class="space-y-4">
            <!-- Bank Selector (if multiple) -->
            <div v-if="bankAccounts.length > 1" class="card p-4">
              <label class="block text-sm font-medium mb-2">Select Bank Account</label>
              <select
                v-model="selectedBankId"
                @change="onBankChange"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option v-for="bank in bankAccounts" :key="bank.id" :value="bank.id">
                  {{ bank.bank_name }} ({{ bank.account_number }})
                </option>
              </select>
            </div>

            <!-- Selected Bank Details -->
            <div v-if="selectedBank" class="card p-6">
              <h2 class="text-lg font-semibold mb-4">Bank Account Details</h2>
              <p class="text-sm text-[var(--color-muted-foreground)] mb-4">
                Transfer the amount to this bank account:
              </p>
              <div class="rounded-lg bg-[var(--color-muted)] p-4 space-y-2 font-mono text-sm">
                <div class="flex justify-between">
                  <span class="text-[var(--color-muted-foreground)]">Bank:</span>
                  <span class="font-semibold">{{ selectedBank.bank_name }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-[var(--color-muted-foreground)]">Account:</span>
                  <span class="font-semibold">{{ selectedBank.account_number }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-[var(--color-muted-foreground)]">Holder:</span>
                  <span class="font-semibold">{{ selectedBank.account_holder_name }}</span>
                </div>
                <div v-if="selectedBank.routing_number" class="flex justify-between">
                  <span class="text-[var(--color-muted-foreground)]">Routing:</span>
                  <span class="font-semibold">{{ selectedBank.routing_number }}</span>
                </div>
              </div>
              <p class="mt-4 text-xs text-[var(--color-muted-foreground)]">
                Please include your email in the transfer reference for faster processing.
              </p>
            </div>
          </div>

          <!-- No Bank Settings Warning -->
          <div v-else class="card p-6 bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800">
            <div class="flex items-start gap-3">
              <svg class="h-5 w-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <p class="font-medium text-amber-800 dark:text-amber-300">Bank Transfer Not Available</p>
                <p class="text-sm text-amber-700 dark:text-amber-400 mt-1">
                  Bank account details have not been configured yet. Please contact support or check back later.
                </p>
              </div>
            </div>
          </div>

          <!-- Instructions Card -->
          <div class="card p-6">
            <h2 class="text-lg font-semibold mb-4">How It Works</h2>
            <ol class="space-y-4">
              <li class="flex gap-3">
                <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950 text-brand-600 dark:text-brand-400 text-sm font-semibold">
                  1
                </span>
                <div>
                  <p class="font-medium">Select Product & Plan</p>
                  <p class="text-sm text-[var(--color-muted-foreground)]">
                    Choose the subscription you want to pay for.
                  </p>
                </div>
              </li>
              <li class="flex gap-3">
                <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950 text-brand-600 dark:text-brand-400 text-sm font-semibold">
                  2
                </span>
                <div>
                  <p class="font-medium">Transfer Funds</p>
                  <p class="text-sm text-[var(--color-muted-foreground)]">
                    Send the exact amount to the bank account shown.
                  </p>
                </div>
              </li>
              <li class="flex gap-3">
                <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950 text-brand-600 dark:text-brand-400 text-sm font-semibold">
                  3
                </span>
                <div>
                  <p class="font-medium">Submit Request</p>
                  <p class="text-sm text-[var(--color-muted-foreground)]">
                    Fill in the transaction reference from your receipt.
                  </p>
                </div>
              </li>
              <li class="flex gap-3">
                <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950 text-brand-600 dark:text-brand-400 text-sm font-semibold">
                  4
                </span>
                <div>
                  <p class="font-medium">Get Credits</p>
                  <p class="text-sm text-[var(--color-muted-foreground)]">
                    After approval, credits are issued for the same value.
                  </p>
                </div>
              </li>
            </ol>
          </div>

          <!-- Help Card -->
          <div class="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 p-4">
            <div class="flex gap-3">
              <svg class="h-5 w-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p class="font-medium text-amber-800 dark:text-amber-300">Need Help?</p>
                <p class="text-sm text-amber-700 dark:text-amber-400 mt-1">
                  If you have any questions about bank transfers, contact our support team for assistance.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
