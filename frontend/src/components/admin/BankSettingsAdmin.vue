<script setup lang="ts">
/**
 * BankSettingsAdmin — Admin bank account settings management.
 *
 * Features:
 *   - List all bank accounts (active and inactive)
 *   - Create new bank account
 *   - Update existing bank account
 *   - Toggle active/deactive status
 *   - Delete bank account
 *
 * Used on: /admin/bank-settings
 */

import { ref, onMounted, computed } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { creditsApi } from "@/lib/credits";

import AdminPageHeader from "@/components/admin/AdminPageHeader.vue";
import AdminStatusBadge from "@/components/admin/AdminStatusBadge.vue";

// ─── Types ───────────────────────────────────────────────────────────────────

interface BankAccount {
  id: number;
  bank_name: string;
  account_holder_name: string;
  account_number: string;
  routing_number: string;
  is_active: boolean;
}

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(true);
const saving = ref(false);
const loadError = ref<string | null>(null);

const bankAccounts = ref<BankAccount[]>([]);
const editingId = ref<number | null>(null);
const showForm = ref(false);

const form = ref({
  bank_name: "",
  account_holder_name: "",
  account_number: "",
  routing_number: "",
  is_active: true,
});

// ─── Computed ────────────────────────────────────────────────────────────────

const activeCount = computed(() => bankAccounts.value.filter(b => b.is_active).length);
const editingBank = computed(() => bankAccounts.value.find(b => b.id === editingId.value));

// ─── Data fetching ───────────────────────────────────────────────────────────

async function fetchBankAccounts() {
  loading.value = true;
  loadError.value = null;
  try {
    const data = await creditsApi.adminListBankSettings();
    bankAccounts.value = data.banks || [];
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  if (!requireAuth()) return;
  await fetchBankAccounts();
});

// ─── Form Actions ────────────────────────────────────────────────────────────

function openCreateForm() {
  editingId.value = null;
  form.value = {
    bank_name: "",
    account_holder_name: "",
    account_number: "",
    routing_number: "",
    is_active: true,
  };
  showForm.value = true;
}

function openEditForm(bank: BankAccount) {
  editingId.value = bank.id;
  form.value = {
    bank_name: bank.bank_name,
    account_holder_name: bank.account_holder_name,
    account_number: bank.account_number,
    routing_number: bank.routing_number || "",
    is_active: bank.is_active,
  };
  showForm.value = true;
}

function closeForm() {
  showForm.value = false;
  editingId.value = null;
}

async function handleSave() {
  // Validation
  if (!form.value.bank_name.trim()) {
    showToast("Bank name is required", "error");
    return;
  }
  if (!form.value.account_holder_name.trim()) {
    showToast("Account holder name is required", "error");
    return;
  }
  if (!form.value.account_number.trim()) {
    showToast("Account number is required", "error");
    return;
  }

  saving.value = true;
  try {
    const payload = {
      bank_name: form.value.bank_name.trim(),
      account_holder_name: form.value.account_holder_name.trim(),
      account_number: form.value.account_number.trim(),
      routing_number: form.value.routing_number.trim(),
      is_active: form.value.is_active,
    };

    let result;
    if (editingId.value) {
      result = await creditsApi.updateBankSettings(editingId.value, payload);
    } else {
      result = await creditsApi.createBankSettings(payload);
    }

    showToast(result.message || "Bank settings saved successfully", "success");
    closeForm();
    await fetchBankAccounts();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    saving.value = false;
  }
}

async function handleToggle(bank: BankAccount) {
  try {
    const result = await creditsApi.toggleBankSettings(bank.id);
    showToast(result.message || `Bank ${bank.bank_name} ${result.is_active ? 'activated' : 'deactivated'}`, "success");
    await fetchBankAccounts();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  }
}

async function handleDelete(bank: BankAccount) {
  if (!confirm(`Are you sure you want to delete "${bank.bank_name}"? This cannot be undone.`)) {
    return;
  }

  try {
    const result = await creditsApi.deleteBankSettings(bank.id);
    showToast(result.message || "Bank settings deleted", "success");
    await fetchBankAccounts();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Page Header -->
    <AdminPageHeader
      title="Bank Settings"
      description="Manage bank account details for manual credit purchases via bank transfer."
      :breadcrumbs="[{ label: 'Admin', href: '/admin' }, { label: 'Bank Settings' }]"
    >
      <template #actions>
        <button
          class="btn-primary text-sm"
          @click="openCreateForm"
          :disabled="showForm"
        >
          <svg class="h-4 w-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Add Bank Account
        </button>
      </template>
    </AdminPageHeader>

    <!-- Error state -->
    <div
      v-if="loadError"
      class="card flex flex-col items-center gap-4 p-10 text-center"
    >
      <svg class="h-12 w-12 text-destructive/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <div>
        <p class="font-medium text-foreground">Failed to load bank settings</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchBankAccounts">Try again</button>
    </div>

    <template v-else>
      <!-- Status Summary -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="card p-4">
          <div class="text-sm text-muted-foreground">Total Accounts</div>
          <div class="text-2xl font-bold">{{ bankAccounts.length }}</div>
        </div>
        <div class="card p-4 bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800">
          <div class="text-sm text-green-700 dark:text-green-400">Active</div>
          <div class="text-2xl font-bold text-green-800 dark:text-green-300">{{ activeCount }}</div>
        </div>
        <div class="card p-4 bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800">
          <div class="text-sm text-amber-700 dark:text-amber-400">Inactive</div>
          <div class="text-2xl font-bold text-amber-800 dark:text-amber-300">{{ bankAccounts.length - activeCount }}</div>
        </div>
      </div>

      <!-- Create/Edit Form -->
      <div v-if="showForm" class="card">
        <div class="p-6 border-b border-border flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold">{{ editingId ? 'Edit Bank Account' : 'Add New Bank Account' }}</h2>
            <p class="text-sm text-muted-foreground mt-1">
              These details will be shown to users when requesting credit purchases via bank transfer.
            </p>
          </div>
          <button
            type="button"
            class="text-muted-foreground hover:text-foreground"
            @click="closeForm"
          >
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form @submit.prevent="handleSave" class="p-6 space-y-4">
          <div>
            <label class="block text-sm font-medium mb-1">Bank Name *</label>
            <input
              v-model="form.bank_name"
              type="text"
              class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder="e.g., City Bank"
              :disabled="saving"
            />
          </div>

          <div>
            <label class="block text-sm font-medium mb-1">Account Holder Name *</label>
            <input
              v-model="form.account_holder_name"
              type="text"
              class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              placeholder="e.g., SattaBase Inc."
              :disabled="saving"
            />
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium mb-1">Account Number *</label>
              <input
                v-model="form.account_number"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                placeholder="e.g., 1234567890"
                :disabled="saving"
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">Routing/SWIFT Number</label>
              <input
                v-model="form.routing_number"
                type="text"
                class="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                placeholder="e.g., 021000021"
                :disabled="saving"
              />
            </div>
          </div>

          <div class="flex items-center gap-2">
            <input
              type="checkbox"
              id="is_active"
              v-model="form.is_active"
              class="rounded border-border"
              :disabled="saving"
            />
            <label for="is_active" class="text-sm">Active (show to users)</label>
          </div>

          <div class="flex items-center justify-end gap-3 pt-4 border-t border-border">
            <button type="button" class="btn-secondary text-sm" @click="closeForm" :disabled="saving">
              Cancel
            </button>
            <button type="submit" :disabled="saving" class="btn-primary text-sm">
              <svg v-if="saving" class="h-4 w-4 mr-1.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {{ saving ? "Saving..." : (editingId ? "Update" : "Create") }}
            </button>
          </div>
        </form>
      </div>

      <!-- Bank Accounts List -->
      <div class="card">
        <div class="p-6 border-b border-border">
          <h2 class="text-lg font-semibold">Bank Accounts</h2>
          <p class="text-sm text-muted-foreground mt-1">
            Active accounts are shown to users on the credit request page.
          </p>
        </div>

        <div v-if="bankAccounts.length === 0" class="p-10 text-center">
          <svg class="h-12 w-12 mx-auto text-muted-foreground/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
          </svg>
          <p class="mt-4 text-muted-foreground">No bank accounts configured yet.</p>
          <button class="btn-primary text-sm mt-4" @click="openCreateForm">
            Add First Bank Account
          </button>
        </div>

        <div v-else class="divide-y divide-border">
          <div
            v-for="bank in bankAccounts"
            :key="bank.id"
            class="p-4 flex items-center justify-between gap-4"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium truncate">{{ bank.bank_name }}</span>
                <AdminStatusBadge :status="bank.is_active ? 'active' : 'inactive'" />
              </div>
              <div class="text-sm text-muted-foreground mt-1">
                {{ bank.account_holder_name }} &bull; {{ bank.account_number }}
                <span v-if="bank.routing_number"> &bull; {{ bank.routing_number }}</span>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="btn-secondary text-xs"
                @click="openEditForm(bank)"
                title="Edit"
              >
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button
                class="btn-secondary text-xs"
                @click="handleToggle(bank)"
                :title="bank.is_active ? 'Deactivate' : 'Activate'"
              >
                <svg v-if="bank.is_active" class="h-4 w-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                </svg>
                <svg v-else class="h-4 w-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>
              <button
                class="btn-secondary text-xs !text-red-600 hover:!bg-red-50 dark:hover:!bg-red-950"
                @click="handleDelete(bank)"
                title="Delete"
              >
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Usage Info -->
      <div class="card bg-muted/30">
        <div class="p-6">
          <h3 class="text-sm font-semibold mb-3">How Bank Settings Work</h3>
          <ul class="space-y-2 text-sm text-muted-foreground">
            <li class="flex items-start gap-2">
              <span class="text-brand-500 mt-0.5">1.</span>
              <span>All <strong>active</strong> bank accounts are shown to users on the credit request page.</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="text-brand-500 mt-0.5">2.</span>
              <span>Users select a bank, transfer money, and submit their transaction reference.</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="text-brand-500 mt-0.5">3.</span>
              <span>Admins review requests in <a href="/admin/credit-requests" class="text-brand-600 hover:underline">Credit Requests</a> and approve/reject them.</span>
            </li>
            <li class="flex items-start gap-2">
              <span class="text-brand-500 mt-0.5">4.</span>
              <span>Approved requests create a CreditPool and CreditInvoice for the user.</span>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </div>
</template>
