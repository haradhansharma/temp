<script setup lang="ts">
// Verify email — Vue interactive island
// Handles email verification via OTP (6-digit code sent to user's email)
// POST /auth/verify-email/request → POST /auth/verify-email/confirm

import { ref, onMounted, computed } from "vue";
import { requestEmailVerification, verifyEmail } from "@/lib/auth";
import { getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { useCooldownTimer, useOtpInput } from "@/composables";

const props = defineProps<{
  email?: string;
}>();

// ─── OTP input state ─────────────────────────────────────────────────────────
const { digits: otpDigits, otpValue, isComplete, refs: otpRefs, handleInput: handleOtpInput, handleKeydown: handleOtpKeydown, handlePaste: handleOtpPaste, reset: resetOtp, focusFirst: focusOtpInput } = useOtpInput(6);
const loading = ref(false);
const error = ref("");
const done = ref(false);


// ─── Resend cooldown timer — uses composable ───────────────────────────────
const { cooldown: resendCooldown, startCooldown } = useCooldownTimer(60);

// ─── Email tracking ──────────────────────────────────────────────────────────
const email = ref(props.email || "");
const emailInput = ref("");
const requestingOtp = ref(false);

// Determine if we're in the "enter email" phase or "enter OTP" phase
const showEmailStep = computed(() => !email.value);

// ─── Request OTP ─────────────────────────────────────────────────────────────
async function handleRequestOtp() {
  error.value = "";

  if (!emailInput.value.trim()) {
    error.value = "Email address is required.";
    return;
  }

  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailPattern.test(emailInput.value.trim())) {
    error.value = "Please enter a valid email address.";
    return;
  }

  requestingOtp.value = true;
  try {
    email.value = emailInput.value.trim();
    await requestEmailVerification(email.value);
    showToast("Verification code sent to your email.", "success");
    startCooldown(60);
  } catch (err: unknown) {
    const message = getErrorMessage(err);
    error.value = message;
    showToast(message, "error");
  } finally {
    requestingOtp.value = false;
  }
}

// ─── Verify OTP ──────────────────────────────────────────────────────────────
async function handleVerify() {
  if (otpValue.value.length !== 6) {
    error.value = "Please enter the complete 6-digit code.";
    return;
  }

  error.value = "";
  loading.value = true;

  try {
    await verifyEmail(email.value, otpValue.value);
    done.value = true;
    showToast("Email verified successfully!", "success");
  } catch (err: unknown) {
    const message = getErrorMessage(err);
    error.value = message;
    showToast(message, "error");
    // Clear OTP on error so user can re-enter
    resetOtp();
    focusOtpInput();
  } finally {
    loading.value = false;
  }
}

// ─── Resend OTP ──────────────────────────────────────────────────────────────
async function handleResend() {
  if (resendCooldown.value > 0 || !email.value) return;

  error.value = "";
  try {
    await requestEmailVerification(email.value);
    showToast("A new verification code has been sent.", "success");
    startCooldown(60);
  } catch (err: unknown) {
    const message = getErrorMessage(err);
    error.value = message;
    showToast(message, "error");
  }
}

// ─── Auto-focus on mount ────────────────────────────────────────────────────
onMounted(() => {
  if (!showEmailStep.value) {
    // Auto-focus the first OTP input
    setTimeout(() => focusOtpInput(0), 100);
  }
});
</script>

<template>
  <div>
    <!-- ─── Done State ─── -->
    <div v-if="done" class="text-center">
      <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
        <svg class="h-8 w-8 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h2 class="text-2xl font-bold tracking-tight">Email verified!</h2>
      <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
        Your email address has been verified successfully. You can now sign in.
      </p>
      <a href="/auth/login" class="btn-primary mt-6 inline-flex" aria-label="Go to sign in page">
        Sign in
      </a>
    </div>

    <!-- ─── Email Step (enter email to request OTP) ─── -->
    <div v-else-if="showEmailStep" class="text-center">
      <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
        <svg class="h-8 w-8 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      </div>
      <h2 class="text-2xl font-bold tracking-tight">Verify your email</h2>
      <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
        Enter your email address and we'll send you a verification code.
      </p>

      <div
        v-if="error"
        role="alert"
        class="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
      >
        {{ error }}
      </div>

      <form @submit.prevent="handleRequestOtp" class="mt-6 space-y-4">
        <div class="space-y-2">
          <label for="verify-email" class="label-text">Email address</label>
          <input
            id="verify-email"
            v-model="emailInput"
            type="email"
            required
            autocomplete="email"
            placeholder="you@example.com"
            class="input-field"
            :disabled="requestingOtp"
          />
        </div>
        <button
          type="submit"
          :disabled="requestingOtp"
          class="btn-primary w-full"
        >
          <svg v-if="requestingOtp" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ requestingOtp ? "Sending..." : "Send verification code" }}
        </button>
      </form>

      <p class="mt-6 text-center text-sm text-[var(--color-muted-foreground)]">
        Already verified?
        <a href="/auth/login" class="font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400">Sign in</a>
      </p>
    </div>

    <!-- ─── OTP Step (enter 6-digit code) ─── -->
    <div v-else class="text-center">
      <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
        <svg class="h-8 w-8 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
      </div>
      <h2 class="text-2xl font-bold tracking-tight">Enter verification code</h2>
      <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
        We sent a 6-digit code to <strong class="text-foreground">{{ email }}</strong>
      </p>

      <div
        v-if="error"
        role="alert"
        class="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
      >
        {{ error }}
      </div>

      <form @submit.prevent="handleVerify" class="mt-6 space-y-6">
        <!-- OTP Input -->
        <div class="flex items-center justify-center gap-2 sm:gap-3">
          <div v-for="i in 6" :key="i">
            <input
              :ref="(el: any) => { otpRefs[i - 1] = el as HTMLInputElement; }"
              type="text"
              inputmode="numeric"
              maxlength="1"
              :value="otpDigits[i - 1]"
              class="h-12 w-11 rounded-lg border border-input bg-transparent text-center text-xl font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 transition-colors disabled:opacity-50"
              :class="{
                'border-brand-500 ring-1 ring-brand-500': otpDigits[i - 1],
                'border-red-500': !!error,
              }"
              :disabled="loading"
              :aria-label="`Digit ${i} of 6`"
              @input="handleOtpInput(i - 1, $event)"
              @keydown="handleOtpKeydown(i - 1, $event)"
              @paste="handleOtpPaste"
            />
          </div>
        </div>

        <!-- Submit button -->
        <button
          type="submit"
          :disabled="loading || !isComplete"
          class="btn-primary mx-auto flex w-auto items-center justify-center gap-2"
          aria-label="Verify email"
        >
          <svg v-if="loading" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ loading ? 'Verifying...' : 'Verify email' }}
        </button>
      </form>

      <!-- Resend -->
      <div class="mt-2">
        <p v-if="resendCooldown > 0" class="text-sm text-[var(--color-muted-foreground)]">
          Resend code in <strong>{{ resendCooldown }}s</strong>
        </p>
        <button
          v-else
          type="button"
          @click="handleResend"
          class="text-sm font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400"
        >
          Didn't receive it? Resend code
        </button>
      </div>

      <!-- Tips -->
      <div class="mt-4 mx-auto max-w-xs text-left space-y-1.5">
        <p class="text-xs text-[var(--color-muted-foreground)]">
          &bull; The code expires in 10 minutes
        </p>
        <p class="text-xs text-[var(--color-muted-foreground)]">
          &bull; Check your spam or junk folder
        </p>
      </div>

      <!-- Back link -->
      <div class="mt-6 border-t border-[var(--color-border)] pt-4">
        <p class="text-sm text-[var(--color-muted-foreground)]">
          <a href="/auth/login" class="font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400">
            Back to sign in
          </a>
        </p>
      </div>
    </div>
  </div>
</template>
