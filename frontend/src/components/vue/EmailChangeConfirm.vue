<script setup lang="ts">
// Email change confirmation — Vue interactive island
// Handles POST /auth/email-change/confirm via auth.ts

import { ref, reactive, onMounted } from "vue";
import { confirmEmailChangeOTP, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";

const props = defineProps<{
  token?: string;
}>();

const form = reactive({
  token: props.token || "",
});

const loading = ref(false);
const error = ref("");
const done = ref(false);
const showManualEntry = ref(false);

function clearErrors() {
  error.value = "";
}

async function handleSubmit() {
  if (!form.token.trim()) {
    error.value = "Confirmation token is required.";
    return;
  }

  error.value = "";
  loading.value = true;

  try {
    await confirmEmailChangeOTP(form.token.trim());
    done.value = true;
    showToast("Email address updated successfully!", "success");
  } catch (err: unknown) {
    const message = getErrorMessage(err);
    error.value = message;
    showToast(message, "error");

    // If auto-submit failed and there's a token prop, show manual entry option
    if (props.token && !showManualEntry.value) {
      showManualEntry.value = true;
    }
  } finally {
    loading.value = false;
  }
}

// Auto-submit with a small delay if token is provided via props
onMounted(() => {
  if (props.token) {
    setTimeout(() => {
      handleSubmit();
    }, 500);
  }
});
</script>

<template>
  <div>
    <!-- Loading state during auto-submit -->
    <div v-if="loading && !showManualEntry" class="text-center">
      <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
        <svg class="h-8 w-8 animate-spin text-brand-600 dark:text-brand-400" fill="none" viewBox="0 0 24 24" aria-hidden="true">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
      <h2 class="text-2xl font-bold tracking-tight">Confirming email change...</h2>
      <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
        Please wait while we verify your token.
      </p>
    </div>

    <!-- Done state -->
    <div v-else-if="done" class="text-center">
      <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
        <svg class="h-8 w-8 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h2 class="text-2xl font-bold tracking-tight">Email updated!</h2>
      <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
        Your email address has been changed successfully. Please sign in with your new email.
      </p>
      <a href="/auth/login" class="btn-primary mt-6 inline-flex" aria-label="Go to sign in page">
        Sign in with new email
      </a>
    </div>

    <!-- Form state (manual token entry or auto-submit failed) -->
    <div v-else>
      <div class="mb-6 text-center">
        <h2 class="text-2xl font-bold tracking-tight">Confirm email change</h2>
        <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
          Enter the confirmation token sent to your email
        </p>
      </div>

      <div
        v-if="error"
        role="alert"
        class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
      >
        {{ error }}
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div class="space-y-2">
          <label for="email-token" class="label-text">Confirmation token</label>
          <input
            id="email-token"
            v-model="form.token"
            type="text"
            required
            placeholder="Paste your confirmation token here"
            class="input-field font-mono"
            :aria-invalid="!!error"
            :aria-describedby="error ? 'email-token-error' : undefined"
            :disabled="loading"
          />
          <p
            v-if="error && !done"
            id="email-token-error"
            class="text-xs text-red-500"
            role="alert"
          >
            Please check the token and try again, or request a new email change from your account settings.
          </p>
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="btn-primary w-full"
          aria-label="Confirm email change"
        >
          <svg v-if="loading" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ loading ? "Confirming..." : "Confirm email change" }}
        </button>
      </form>

      <p class="mt-6 text-center text-sm text-[var(--color-muted-foreground)]">
        <a href="/auth/login" class="font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400">Back to sign in</a>
      </p>
    </div>
  </div>
</template>
