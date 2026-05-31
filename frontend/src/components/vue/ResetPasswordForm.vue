<script setup lang="ts">
// Reset password — Vue interactive island
// Handles POST /auth/password-reset/confirm via auth.ts

import { ref, reactive, computed } from "vue";
import { confirmPasswordReset } from "@/lib/auth";
import { getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import type { ApiError } from "@/lib/api";

const props = defineProps<{
  token?: string;
}>();

const form = reactive({
  token: props.token || "",
  new_password: "",
  confirm_password: "",
});

const loading = ref(false);
const error = ref("");
const fieldErrors = reactive<Record<string, string>>({
  token: "",
  new_password: "",
  confirm_password: "",
});
const done = ref(false);

// Password strength computation
const passwordChecks = computed(() => {
  const pw = form.new_password;
  return {
    length: pw.length >= 8,
    uppercase: /[A-Z]/.test(pw),
    lowercase: /[a-z]/.test(pw),
    number: /[0-9]/.test(pw),
    special: /[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`;\']/.test(pw),
  };
});

const passwordStrength = computed(() => {
  const checks = Object.values(passwordChecks.value);
  const passed = checks.filter(Boolean).length;
  if (form.new_password.length === 0) return { level: 0, label: "", color: "" };
  if (passed <= 2) return { level: 1, label: "Weak", color: "bg-red-500" };
  if (passed <= 3) return { level: 2, label: "Fair", color: "bg-yellow-500" };
  if (passed <= 4) return { level: 3, label: "Good", color: "bg-brand-400" };
  return { level: 4, label: "Strong", color: "bg-brand-600" };
});

const strengthSegments = [0, 1, 2, 3];

function clearErrors() {
  error.value = "";
  Object.keys(fieldErrors).forEach((key) => {
    fieldErrors[key] = "";
  });
}

function validateForm(): boolean {
  clearErrors();
  let valid = true;

  if (!props.token && !form.token.trim()) {
    fieldErrors.token = "Reset token is required.";
    valid = false;
  }

  const checks = Object.values(passwordChecks.value);
  if (checks.some((c) => !c)) {
    fieldErrors.new_password = "Password does not meet all requirements.";
    valid = false;
  }

  if (form.new_password !== form.confirm_password) {
    fieldErrors.confirm_password = "Passwords do not match.";
    valid = false;
  }

  return valid;
}

async function handleSubmit() {
  if (!validateForm()) return;

  loading.value = true;
  clearErrors();

  try {
    const token = props.token || form.token.trim();
    await confirmPasswordReset(token, form.new_password);
    done.value = true;
    showToast("Password reset successfully! Redirecting to sign in...", "success");
    setTimeout(() => {
      window.location.href = "/auth/login";
    }, 3000);
  } catch (err: unknown) {
    const apiErr = err as ApiError;

    if (apiErr.errors) {
      for (const [field, messages] of Object.entries(apiErr.errors)) {
        if (field === "token") {
          fieldErrors.token = messages.join(" ");
        } else if (field === "new_password") {
          fieldErrors.new_password = messages.join(" ");
        }
      }
    }

    const message = getErrorMessage(err);
    error.value = message;
    showToast(message, "error");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div>
    <!-- Done state -->
    <div v-if="done" class="text-center">
      <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
        <svg class="h-8 w-8 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h2 class="text-2xl font-bold tracking-tight">Password reset!</h2>
      <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
        Your password has been reset successfully. You can now sign in.
      </p>
      <a href="/auth/login" class="btn-primary mt-6 inline-flex" aria-label="Go to sign in page">
        Sign in
      </a>
    </div>

    <!-- Form state -->
    <div v-else>
      <div class="mb-6 text-center">
        <h2 class="text-2xl font-bold tracking-tight">Reset password</h2>
        <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
          Enter your new password below
        </p>
      </div>

      <!-- General Error -->
      <div
        v-if="error"
        role="alert"
        class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
      >
        {{ error }}
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <!-- Token (if not in URL) -->
        <div v-if="!token" class="space-y-2">
          <label for="reset-token" class="label-text">Reset token</label>
          <input
            id="reset-token"
            v-model="form.token"
            type="text"
            required
            placeholder="UUID token from email"
            class="input-field font-mono"
            :class="{ 'border-red-500 ring-red-500': fieldErrors.token }"
            :aria-invalid="!!fieldErrors.token"
            :aria-describedby="fieldErrors.token ? 'reset-token-error' : undefined"
            :disabled="loading"
          />
          <p
            v-if="fieldErrors.token"
            id="reset-token-error"
            class="text-xs text-red-500"
            role="alert"
          >
            {{ fieldErrors.token }}
          </p>
        </div>

        <div class="space-y-2">
          <label for="reset-password" class="label-text">New password</label>
          <input
            id="reset-password"
            v-model="form.new_password"
            type="password"
            required
            autocomplete="new-password"
            placeholder="Create a strong password"
            class="input-field"
            :class="{ 'border-red-500 ring-red-500': fieldErrors.new_password }"
            :aria-invalid="!!fieldErrors.new_password"
            :aria-describedby="fieldErrors.new_password ? 'reset-password-error' : 'reset-password-strength'"
            :disabled="loading"
          />
          <p
            v-if="fieldErrors.new_password"
            id="reset-password-error"
            class="text-xs text-red-500"
            role="alert"
          >
            {{ fieldErrors.new_password }}
          </p>

          <!-- Password Strength Bar -->
          <div v-if="form.new_password.length > 0" id="reset-password-strength" class="space-y-2">
            <div class="flex items-center gap-2">
              <div class="flex flex-1 gap-1">
                <div
                  v-for="i in strengthSegments"
                  :key="i"
                  class="h-1.5 flex-1 rounded-full transition-colors duration-300"
                  :class="passwordStrength.level > i ? passwordStrength.color : 'bg-[var(--color-border)]'"
                ></div>
              </div>
              <span
                class="text-xs font-medium transition-colors duration-300"
                :class="{
                  'text-red-500': passwordStrength.level === 1,
                  'text-yellow-500': passwordStrength.level === 2,
                  'text-brand-400': passwordStrength.level === 3,
                  'text-brand-600': passwordStrength.level === 4,
                }"
              >
                {{ passwordStrength.label }}
              </span>
            </div>

            <!-- Password strength hints -->
            <ul class="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs transition-all duration-300">
              <li
                :class="passwordChecks.length ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.length ? '✓' : '○' }} 8+ characters
              </li>
              <li
                :class="passwordChecks.uppercase ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.uppercase ? '✓' : '○' }} Uppercase letter
              </li>
              <li
                :class="passwordChecks.lowercase ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.lowercase ? '✓' : '○' }} Lowercase letter
              </li>
              <li
                :class="passwordChecks.number ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.number ? '✓' : '○' }} Number
              </li>
              <li
                :class="passwordChecks.special ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.special ? '✓' : '○' }} Special character
              </li>
            </ul>
          </div>
        </div>

        <div class="space-y-2">
          <label for="reset-confirm" class="label-text">Confirm new password</label>
          <input
            id="reset-confirm"
            v-model="form.confirm_password"
            type="password"
            required
            autocomplete="new-password"
            placeholder="Re-enter your new password"
            class="input-field"
            :class="{
              'border-red-500 ring-red-500': fieldErrors.confirm_password || (form.confirm_password && form.new_password !== form.confirm_password)
            }"
            :aria-invalid="!!(fieldErrors.confirm_password || (form.confirm_password && form.new_password !== form.confirm_password))"
            :aria-describedby="
              fieldErrors.confirm_password ? 'reset-confirm-error' :
              (form.confirm_password && form.new_password !== form.confirm_password) ? 'reset-confirm-mismatch' : undefined
            "
            :disabled="loading"
          />
          <p
            v-if="fieldErrors.confirm_password"
            id="reset-confirm-error"
            class="text-xs text-red-500"
            role="alert"
          >
            {{ fieldErrors.confirm_password }}
          </p>
          <p
            v-else-if="form.confirm_password && form.new_password !== form.confirm_password"
            id="reset-confirm-mismatch"
            class="text-xs text-red-500"
          >
            Passwords do not match
          </p>
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="btn-primary w-full"
          aria-label="Reset your password"
        >
          <svg v-if="loading" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ loading ? "Resetting..." : "Reset password" }}
        </button>
      </form>

      <p class="mt-6 text-center text-sm text-[var(--color-muted-foreground)]">
        <a href="/auth/login" class="font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400">Back to sign in</a>
      </p>
    </div>
  </div>
</template>
