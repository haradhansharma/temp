<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
    <!-- Loading state -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-white"></div>
      <p class="mt-4 text-gray-600 dark:text-gray-400">Loading requests...</p>
    </div>

    <!-- Empty state -->
    <div v-else-if="!requests.length" class="text-center py-12">
      <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <h3 class="mt-2 text-sm font-medium text-gray-900 dark:text-white">No requests</h3>
      <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
        No credit purchase requests to review.
      </p>
    </div>

    <!-- Requests table -->
    <div v-else class="overflow-x-auto">
      <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead class="bg-gray-50 dark:bg-gray-700">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              Request ID
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              User
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              Product / Plan
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              Amount
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              Bank
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              Transaction Ref
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              Status
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              Submitted
            </th>
            <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
          <tr v-for="req in requests" :key="req.id" class="hover:bg-gray-50 dark:hover:bg-gray-700/50">
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
              #{{ req.id }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
              {{ req.user_email }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
              <div>{{ req.product_name }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ req.plan_name }}</div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
              {{ (req.amount_cents / 100).toFixed(2) }} {{ req.currency }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
              {{ req.bank_name }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
              {{ req.transaction_reference }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span
                :class="{
                  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300': req.status === 'pending',
                  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300': req.status === 'approved',
                  'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300': req.status === 'rejected',
                }"
                class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full"
              >
                {{ req.status }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
              {{ formatDate(req.created_at) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
              <button
                v-if="req.status === 'pending'"
                @click="openApproveModal(req)"
                class="text-green-600 hover:text-green-900 dark:text-green-400 dark:hover:text-green-300 mr-3"
              >
                Approve
              </button>
              <button
                v-if="req.status === 'pending'"
                @click="openRejectModal(req)"
                class="text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300"
              >
                Reject
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Approve Modal -->
    <div v-if="showApproveModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4">
        <div class="p-6">
          <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-2">Approve Credit Request</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
            Are you sure you want to approve this credit purchase request?
            The user will receive {{ (selectedRequest?.amount_cents || 0) / 100 }} {{ selectedRequest?.currency }} of credits.
          </p>
          <div class="flex justify-end gap-3">
            <button
              @click="showApproveModal = false"
              class="px-4 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
            >
              Cancel
            </button>
            <button
              @click="approveRequest"
              :disabled="approving"
              class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              <span v-if="approving">Approving...</span>
              <span v-else>Approve</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Reject Modal -->
    <div v-if="showRejectModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4">
        <div class="p-6">
          <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-2">Reject Credit Request</h3>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
            Are you sure you want to reject this request?
          </p>
          <textarea
            v-model="rejectReason"
            rows="3"
            class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent dark:bg-gray-700 dark:text-white mb-4"
            placeholder="Reason for rejection..."
          ></textarea>
          <div class="flex justify-end gap-3">
            <button
              @click="showRejectModal = false"
              class="px-4 py-2 text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
            >
              Cancel
            </button>
            <button
              @click="rejectRequest"
              :disabled="rejecting"
              class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              <span v-if="rejecting">Rejecting...</span>
              <span v-else>Reject</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Success/Error Toast -->
    <div v-if="toast.show" class="fixed bottom-4 right-4 p-4 rounded-lg shadow-lg z-50"
      :class="toast.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'">
      <p class="font-medium">{{ toast.message }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { creditsApi } from "@/lib/credits";
import type { CreditRequest } from "@/lib/credits";

const loading = ref(true);
const requests = ref<CreditRequest[]>([]);
const approving = ref(false);
const rejecting = ref(false);

const showApproveModal = ref(false);
const showRejectModal = ref(false);
const selectedRequest = ref<CreditRequest | null>(null);
const rejectReason = ref("");

const toast = ref({ show: false, message: "", type: "success" as "success" | "error" });

const loadRequests = async () => {
  try {
    const response = await creditsApi.adminListCreditRequests({ status: "pending" });
    requests.value = response.results || [];
  } catch (err) {
    console.error("Failed to load requests:", err);
    showToast("Failed to load requests", "error");
  } finally {
    loading.value = false;
  }
};

const openApproveModal = (req: CreditRequest) => {
  selectedRequest.value = req;
  showApproveModal.value = true;
};

const openRejectModal = (req: CreditRequest) => {
  selectedRequest.value = req;
  showRejectModal.value = true;
};

const approveRequest = async () => {
  if (!selectedRequest.value) return;

  approving.value = true;
  try {
    await creditsApi.adminApproveCreditRequest(selectedRequest.value.id);
    showToast("Credit request approved successfully!", "success");
    showApproveModal.value = false;
    loadRequests();
  } catch (err: any) {
    showToast(err.response?.data?.detail || "Failed to approve request", "error");
  } finally {
    approving.value = false;
  }
};

const rejectRequest = async () => {
  if (!selectedRequest.value) return;

  rejecting.value = true;
  try {
    await creditsApi.adminRejectCreditRequest(selectedRequest.value.id, rejectReason.value);
    showToast("Credit request rejected", "success");
    showRejectModal.value = false;
    rejectReason.value = "";
    loadRequests();
  } catch (err: any) {
    showToast(err.response?.data?.detail || "Failed to reject request", "error");
  } finally {
    rejecting.value = false;
  }
};

const showToast = (message: string, type: "success" | "error") => {
  toast.value = { show: true, message, type };
  setTimeout(() => {
    toast.value.show = false;
  }, 3000);
};

const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

onMounted(() => {
  loadRequests();
});
</script>