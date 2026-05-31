<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
    <!-- Loading state -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-white"></div>
      <p class="mt-4 text-gray-600 dark:text-gray-400">Loading products...</p>
    </div>

    <!-- Form -->
    <form v-else @submit.prevent="handleSubmit" class="space-y-6">
      <!-- Product Selection -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Product <span class="text-red-500">*</span>
        </label>
        <select
          v-model="form.product_slug"
          required
          class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
        >
          <option value="">Select a product</option>
          <option
            v-for="product in products"
            :key="product.slug"
            :value="product.slug"
          >
            {{ product.name }}
          </option>
        </select>
      </div>

      <!-- Plan Selection -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Plan <span class="text-red-500">*</span>
        </label>
        <select
          v-model="form.plan_slug"
          required
          :disabled="!form.product_slug"
          class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white disabled:opacity-50"
        >
          <option value="">Select a plan</option>
          <option
            v-for="plan in filteredPlans"
            :key="plan.slug"
            :value="plan.slug"
          >
            {{ plan.name }} ({{ plan.display_price }})
          </option>
        </select>
      </div>

      <!-- Amount -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Amount (USD) <span class="text-red-500">*</span>
        </label>
        <input
          v-model.number="form.amount_cents"
          type="number"
          min="100"
          step="1"
          required
          class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
          placeholder="2700"
        />
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Minimum: $1.00 (100 cents)
        </p>
      </div>

      <!-- Bank Details -->
      <div class="border-t border-gray-200 dark:border-gray-700 pt-6">
        <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-4">Bank Details</h3>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="md:col-span-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Bank Name <span class="text-red-500">*</span>
            </label>
            <input
              v-model="form.bank_name"
              type="text"
              required
              maxlength="100"
              class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="State Bank of India"
            />
          </div>

          <div class="md:col-span-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Account Holder Name <span class="text-red-500">*</span>
            </label>
            <input
              v-model="form.account_holder_name"
              type="text"
              required
              maxlength="200"
              class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="John Doe"
            />
          </div>

          <div class="md:col-span-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Account Number <span class="text-red-500">*</span>
            </label>
            <input
              v-model="form.account_number"
              type="text"
              required
              maxlength="50"
              class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="1234567890"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Routing Number
            </label>
            <input
              v-model="form.routing_number"
              type="text"
              maxlength="50"
              class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="SBIN0001234"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Transaction Reference <span class="text-red-500">*</span>
            </label>
            <input
              v-model="form.transaction_reference"
              type="text"
              required
              maxlength="255"
              class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
              placeholder="UPI-20260531-TEST"
            />
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Bank transaction ID or UPI reference
            </p>
          </div>
        </div>
      </div>

      <!-- Payment Proof Note -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Payment Proof Note (Optional)
        </label>
        <textarea
          v-model="form.payment_proof_note"
          rows="3"
          maxlength="500"
          class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
          placeholder="Optional note about the payment..."
        ></textarea>
      </div>

      <!-- Submit Button -->
      <div class="flex items-center justify-end gap-3 pt-4">
        <button
          type="button"
          @click="resetForm"
          class="px-4 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
        >
          Reset
        </button>
        <button
          type="submit"
          :disabled="submitting"
          class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <span v-if="submitting">Submitting...</span>
          <span v-else>Submit Request</span>
        </button>
      </div>
    </form>

    <!-- Success Message -->
    <div v-if="success" class="mt-6 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
      <div class="flex items-center gap-2">
        <svg class="w-5 h-5 text-green-600 dark:text-green-400" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
        </svg>
        <p class="text-green-800 dark:text-green-200 font-medium">
          Credit purchase request submitted successfully!
        </p>
      </div>
      <p class="mt-2 text-sm text-green-700 dark:text-green-300">
        An admin will review your transaction and approve it within 24-48 hours.
      </p>
      <button
        @click="resetForm"
        class="mt-4 text-sm text-green-700 dark:text-green-300 hover:text-green-900 dark:hover:text-white underline"
      >
        Submit another request
      </button>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="mt-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
      <div class="flex items-center gap-2">
        <svg class="w-5 h-5 text-red-600 dark:text-red-400" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
        </svg>
        <p class="text-red-800 dark:text-red-200 font-medium">
          Failed to submit request
        </p>
      </div>
      <p class="mt-2 text-sm text-red-700 dark:text-red-300">
        {{ error }}
      </p>
      <button
        @click="resetForm"
        class="mt-4 text-sm text-red-700 dark:text-red-300 hover:text-red-900 dark:hover:text-white underline"
      >
        Try again
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { creditsApi } from "@/lib/credits";

interface Form {
  product_slug: string;
  plan_slug: string;
  amount_cents: number;
  bank_name: string;
  account_holder_name: string;
  account_number: string;
  routing_number: string;
  transaction_reference: string;
  payment_proof_note: string;
}

interface Product {
  slug: string;
  name: string;
}

interface Plan {
  slug: string;
  name: string;
  display_price: string;
}

const loading = ref(true);
const submitting = ref(false);
const success = ref(false);
const error = ref("");

const products = ref<Product[]>([]);
const plans = ref<Plan[]>([]);

const form = ref<Form>({
  product_slug: "",
  plan_slug: "",
  amount_cents: 2700,
  bank_name: "",
  account_holder_name: "",
  account_number: "",
  routing_number: "",
  transaction_reference: "",
  payment_proof_note: "",
});

const filteredPlans = computed(() => {
  if (!form.value.product_slug) return [];
  return plans.value.filter((p) => p.slug === form.value.product_slug);
});

const loadProducts = async () => {
  try {
    const response = await creditsApi.getProducts();
    products.value = response.data || [];
  } catch (err) {
    console.error("Failed to load products:", err);
  } finally {
    loading.value = false;
  }
};

const loadPlans = async (productSlug: string) => {
  try {
    const response = await creditsApi.getPlans(productSlug);
    plans.value = response.data || [];
  } catch (err) {
    console.error("Failed to load plans:", err);
  }
};

const handleSubmit = async () => {
  submitting.value = true;
  error.value = "";

  try {
    const response = await creditsApi.requestCreditPurchase(form.value);
    if (response.data?.id) {
      success.value = true;
      // Reset form after 3 seconds
      setTimeout(() => {
        resetForm();
      }, 3000);
    } else {
      error.value = "Invalid response from server";
    }
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || "Failed to submit request";
  } finally {
    submitting.value = false;
  }
};

const resetForm = () => {
  form.value = {
    product_slug: "",
    plan_slug: "",
    amount_cents: 2700,
    bank_name: "",
    account_holder_name: "",
    account_number: "",
    routing_number: "",
    transaction_reference: "",
    payment_proof_note: "",
  };
  success.value = false;
  error.value = "";
};

onMounted(() => {
  loadProducts();
});
</script>