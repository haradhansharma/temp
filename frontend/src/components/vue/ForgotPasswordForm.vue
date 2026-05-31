<script setup lang="ts">
// Forgot password — Vue interactive island
// OTP-based flow: Step 1 → enter email & request OTP, Step 2 → enter OTP + new password

import { ref, reactive, toRef, computed, nextTick, onMounted } from "vue";
import { requestPasswordReset, confirmPasswordReset, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { usePasswordStrength, useFormErrors, useCooldownTimer, useOtpInput } from "@/composables";

// ─── State ──────────────────────────────────────────────────────────────────

const step = ref<1 | 2>(1); // 1 = email form, 2 = OTP + new password form
const loading = ref(false);
const done = ref(false);

const form = reactive({
  email: "",
  new_password: "",
  confirm_password: "",
});

// Field errors + general error from composable
const { fieldErrors, generalError: error, clearErrors, setApiFieldErrors } = useFormErrors([
  "email", "new_password", "confirm_password",
]);

// ─── OTP input — uses composable ─────────────────────────────────────────────
const {
  digits: otpDigits,
  otpValue,
  isComplete: otpComplete,
  refs: otpRefs,
  handleInput: handleOtpInput,
  handleKeydown: handleOtpKeydown,
  handlePaste: handleOtpPaste,
  reset: resetOtp,
  focusFirst: focusOtpInput,
} = useOtpInput(6);

// ─── Password strength ─────────────────────────────────────────────────────
const { passwordChecks, passwordStrength, strengthSegments, isValid: passwordValid } = usePasswordStrength(toRef(form, "new_password"));

// ─── Cooldown timer — uses composable ───────────────────────────────────────
const { cooldown: resendCooldown, startCooldown: startResendCooldown } = useCooldownTimer(60);

// ─── Step 1: Request OTP ────────────────────────────────────────────────────

function validateEmailForm(): boolean {
  clearErrors();
  if (!form.email.trim()) {
    fieldErrors.email = "Email address is required.";
    return false;
  }
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailPattern.test(form.email)) {
    fieldErrors.email = "Please enter a valid email address.";
    return false;
  }
  return true;
}

async function handleRequestOtp() {
  if (!validateEmailForm()) return;

  loading.value = true;
  clearErrors();

  try {
    await requestPasswordReset(form.email.trim());
    step.value = 2;
    showToast("A verification code has been sent to your email.", "success");
    startResendCooldown();
    // Auto-focus first OTP digit after step transition
    await nextTick();
    setTimeout(() => focusOtpInput(), 150);
  } catch {
    // For security, still proceed to OTP step even on error
    // so we don't leak whether an email exists
    step.value = 2;
    showToast("If an account with that email exists, a reset code has been sent.", "info");
    startResendCooldown();
    await nextTick();
    setTimeout(() => focusOtpInput(), 150);
  } finally {
    loading.value = false;
  }
}

// ─── Resend OTP ─────────────────────────────────────────────────────────────

async function handleResendOtp() {
  if (resendCooldown.value > 0 || loading.value) return;
  loading.value = true;
  clearErrors();

  try {
    await requestPasswordReset(form.email.trim());
    showToast("A new verification code has been sent.", "success");
    startResendCooldown();
    resetOtp();
    setTimeout(() => focusOtpInput(), 100);
  } catch {
    showToast("Could not resend code. Please try again.", "error");
  } finally {
    loading.value = false;
  }
}

// ─── Step 2: Confirm OTP + Set New Password ────────────────────────────────

function validateResetForm(): boolean {
  clearErrors();
  let valid = true;

  if (!otpComplete.value) {
    error.value = "Please enter the complete 6-digit code.";
    valid = false;
  }

  if (!form.new_password) {
    fieldErrors.new_password = "New password is required.";
    valid = false;
  } else if (!passwordValid.value) {
    fieldErrors.new_password = "Password does not meet all requirements.";
    valid = false;
  }

  if (!form.confirm_password) {
    fieldErrors.confirm_password = "Please confirm your new password.";
    valid = false;
  } else if (form.new_password !== form.confirm_password) {
    fieldErrors.confirm_password = "Passwords do not match.";
    valid = false;
  }

  return valid;
}

async function handleResetPassword() {
  if (!validateResetForm()) return;

  loading.value = true;
  clearErrors();

  try {
    await confirmPasswordReset(
      form.email.trim(),
      otpValue.value,
      form.new_password,
      form.confirm_password,
    );
    done.value = true;
    showToast("Password reset successfully! Redirecting to sign in...", "success");
    setTimeout(() => {
      window.location.href = "/auth/login";
    }, 3000);
  } catch (err: unknown) {
    const message = getErrorMessage(err);
    error.value = message;
    showToast(message, "error");
    // Clear OTP on error so user can re-enter
    resetOtp();
    setTimeout(() => focusOtpInput(), 100);
  } finally {
    loading.value = false;
  }
}

// ─── Back to step 1 ────────────────────────────────────────────────────────
function backToEmail() {
  step.value = 1;
  resetOtp();
  form.new_password = "";
  form.confirm_password = "";
  clearErrors();
}
</script>

<template>
  <div>
    <!-- ─── Done state ─── -->
    <div v-if="done" class="text-center">
      <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100 dark:bg-green-950 animate-[scaleIn_0.3s_ease-out]">
        <svg class="h-8 w-8 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h2 class="text-2xl font-bold tracking-tight">Password reset!</h2>
      <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
        Your password has been reset successfully. You can now sign in with your new password.
      </p>
      <a href="/auth/login" class="btn-primary mt-6 inline-flex items-center gap-2" aria-label="Go to sign in page">
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
        </svg>
        Sign in
      </a>
    </div>

    <!-- ─── Step 1: Enter email ─── -->
    <div v-else-if="step === 1">
      <!-- Header with icon -->
      <div class="mb-6 text-center">
        <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-950">
          <svg class="h-8 w-8 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
          </svg>
        </div>
        <h2 class="text-2xl font-bold tracking-tight">Forgot password?</h2>
        <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
          No worries. Enter your email and we'll send you a verification code to reset your password.
        </p>
      </div>

      <!-- Step indicator -->
      <div class="mb-6 flex items-center justify-center gap-2">
        <div class="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">1</div>
        <div class="h-0.5 w-8 rounded-full bg-[var(--color-border)]"></div>
        <div class="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--color-muted)] text-xs font-bold text-[var(--color-muted-foreground)]">2</div>
      </div>
      <div class="mb-6 flex items-center justify-center gap-6 text-xs text-[var(--color-muted-foreground)]">
        <span class="font-medium text-brand-600 dark:text-brand-400">Verify email</span>
        <span>Reset password</span>
      </div>

      <!-- Error alert -->
      <div
        v-if="error"
        role="alert"
        class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
      >
        {{ error }}
      </div>

      <form @submit.prevent="handleRequestOtp" class="space-y-4">
        <div class="space-y-2">
          <label for="forgot-email" class="label-text">Email address</label>
          <div class="relative">
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
              <svg class="h-4 w-4 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <input
              id="forgot-email"
              v-model="form.email"
              type="email"
              required
              autocomplete="email"
              placeholder="you@example.com"
              class="input-field pl-10"
              :class="{ 'border-red-500 ring-red-500': fieldErrors.email }"
              :aria-invalid="!!fieldErrors.email"
              :aria-describedby="fieldErrors.email ? 'forgot-email-error' : undefined"
              :disabled="loading"
            />
          </div>
          <p
            v-if="fieldErrors.email"
            id="forgot-email-error"
            class="text-xs text-red-500"
            role="alert"
          >
            {{ fieldErrors.email }}
          </p>
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="btn-primary w-full"
          aria-label="Send verification code"
        >
          <svg v-if="loading" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {{ loading ? "Sending..." : "Send verification code" }}
        </button>
      </form>

      <p class="mt-6 text-center text-sm text-[var(--color-muted-foreground)]">
        Remember your password?
        <a href="/auth/login" class="font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400">Sign in</a>
      </p>
    </div>

    <!-- ─── Step 2: OTP + New Password ─── -->
    <div v-else>
      <!-- Header with icon -->
      <div class="mb-6 text-center">
        <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
          <svg class="h-8 w-8 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
          </svg>
        </div>
        <h2 class="text-2xl font-bold tracking-tight">Verify & reset</h2>
        <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
          Enter the 6-digit code sent to <strong class="text-foreground">{{ form.email }}</strong>
        </p>
      </div>

      <!-- Step indicator -->
      <div class="mb-6 flex items-center justify-center gap-2">
        <div class="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
          <svg class="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
          </svg>
        </div>
        <div class="h-0.5 w-8 rounded-full bg-brand-600"></div>
        <div class="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">2</div>
      </div>
      <div class="mb-6 flex items-center justify-center gap-6 text-xs text-[var(--color-muted-foreground)]">
        <span class="font-medium text-brand-600 dark:text-brand-400">
          <svg class="inline h-3 w-3 mr-0.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
          Verify email
        </span>
        <span class="font-medium text-foreground">Reset password</span>
      </div>

      <!-- General Error -->
      <div
        v-if="error"
        role="alert"
        class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
      >
        {{ error }}
      </div>

      <form @submit.prevent="handleResetPassword" class="space-y-5">

        <!-- OTP Input — 6 individual digit boxes -->
        <div class="space-y-2">
          <label class="label-text text-center block">Verification code</label>
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
          <p class="text-center text-xs text-[var(--color-muted-foreground)]">
            Didn't receive it?
            <button
              type="button"
              class="font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="resendCooldown > 0 || loading"
              @click="handleResendOtp"
            >
              {{ resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend code" }}
            </button>
          </p>
          <!-- Tips -->
          <div class="mx-auto max-w-xs text-left space-y-1 pt-1">
            <p class="text-xs text-[var(--color-muted-foreground)]">
              &bull; The code expires in 10 minutes
            </p>
            <p class="text-xs text-[var(--color-muted-foreground)]">
              &bull; Check your spam or junk folder
            </p>
          </div>
        </div>

        <!-- Divider -->
        <div class="relative">
          <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-[var(--color-border)]"></div></div>
          <div class="relative flex justify-center text-xs"><span class="bg-card px-2 text-[var(--color-muted-foreground)]">Now set your new password</span></div>
        </div>

        <!-- New Password -->
        <div class="space-y-2">
          <label for="forgot-new-password" class="label-text">New password</label>
          <input
            id="forgot-new-password"
            v-model="form.new_password"
            type="password"
            required
            autocomplete="new-password"
            placeholder="Create a strong password"
            class="input-field"
            :class="{ 'border-red-500 ring-red-500': fieldErrors.new_password }"
            :aria-invalid="!!fieldErrors.new_password"
            :aria-describedby="fieldErrors.new_password ? 'forgot-pw-error' : (form.new_password ? 'forgot-pw-strength' : undefined)"
            :disabled="loading"
          />
          <p
            v-if="fieldErrors.new_password"
            id="forgot-pw-error"
            class="text-xs text-red-500"
            role="alert"
          >
            {{ fieldErrors.new_password }}
          </p>

          <!-- Password Strength Bar -->
          <div v-if="form.new_password.length > 0" id="forgot-pw-strength" class="space-y-2">
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
                :class="passwordStrength.textClass"
              >
                {{ passwordStrength.label }}
              </span>
            </div>

            <ul class="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
              <li
                :class="passwordChecks.length ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.length ? '\u2713' : '\u25cb' }} 8+ characters
              </li>
              <li
                :class="passwordChecks.uppercase ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.uppercase ? '\u2713' : '\u25cb' }} Uppercase letter
              </li>
              <li
                :class="passwordChecks.lowercase ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.lowercase ? '\u2713' : '\u25cb' }} Lowercase letter
              </li>
              <li
                :class="passwordChecks.number ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.number ? '\u2713' : '\u25cb' }} Number
              </li>
              <li
                :class="passwordChecks.special ? 'text-brand-600 dark:text-brand-400' : 'text-[var(--color-muted-foreground)]'"
                class="transition-colors duration-200"
              >
                {{ passwordChecks.special ? '\u2713' : '\u25cb' }} Special character
              </li>
            </ul>
          </div>
        </div>

        <!-- Confirm Password -->
        <div class="space-y-2">
          <label for="forgot-confirm" class="label-text">Confirm new password</label>
          <input
            id="forgot-confirm"
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
            :disabled="loading"
          />
          <p
            v-if="fieldErrors.confirm_password"
            class="text-xs text-red-500"
            role="alert"
          >
            {{ fieldErrors.confirm_password }}
          </p>
          <p
            v-else-if="form.confirm_password && form.new_password !== form.confirm_password"
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

      <!-- Back link -->
      <div class="mt-4 flex items-center justify-between">
        <button
          type="button"
          class="text-sm text-[var(--color-muted-foreground)] hover:text-foreground transition-colors inline-flex items-center gap-1"
          @click="backToEmail"
        >
          <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
          Use a different email
        </button>
        <a href="/auth/login" class="text-sm font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400">
          Sign in
        </a>
      </div>
    </div>
  </div>
</template>
