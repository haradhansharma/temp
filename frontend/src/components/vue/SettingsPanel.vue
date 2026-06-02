<script setup lang="ts">
// Settings page — Vue interactive island
// Contains: Change Password, Change Email, Logout, Delete Account

import { ref, reactive, onMounted } from "vue";
import {
  changePassword,
  requestEmailChange,
  confirmEmailChangeOTP,
  deleteAccount,
  logout,
  requireAuth,
  confirmIdentity,
  getErrorMessage,
} from "@/lib/auth";
import { authHelpers } from "@/lib/api";
import { billingApi } from "@/lib/billing";
import { showToast } from "@/lib/toast";
import { useCooldownTimer, useOtpInput } from "@/composables";

// ==================== Auth Guard ====================
onMounted(() => {
  requireAuth();
});

// ==================== Change Password ====================
const pwForm = reactive({
  current_password: "",
  new_password: "",
  confirm_password: "",
});
const pwLoading = ref(false);
const pwError = ref("");
const pwSuccess = ref("");

async function handlePasswordChange() {
  pwError.value = "";
  pwSuccess.value = "";

  if (!pwForm.current_password) {
    pwError.value = "Current password is required.";
    return;
  }
  if (pwForm.new_password.length < 8) {
    pwError.value = "New password must be at least 8 characters.";
    return;
  }
  if (pwForm.new_password !== pwForm.confirm_password) {
    pwError.value = "Passwords do not match.";
    return;
  }

  pwLoading.value = true;
  try {
    await changePassword(pwForm.current_password, pwForm.new_password, pwForm.confirm_password);
    showToast("Password changed successfully.", "success");
    pwForm.current_password = "";
    pwForm.new_password = "";
    pwForm.confirm_password = "";
  } catch (err) {
    const msg = getErrorMessage(err);
    pwError.value = msg;
    showToast(msg, "error");
  } finally {
    pwLoading.value = false;
  }
}

// ==================== Change Email (OTP 2-step) ====================
type EmailStep = "request" | "otp" | "done";
const emailStep = ref<EmailStep>("request");
const emailForm = reactive({
  current_password: "",
  new_email: "",
});
const emailLoading = ref(false);
const emailError = ref("");

// OTP input — uses composable
const { digits: emailOtp, reset: resetEmailOtp } = useOtpInput(6);

// Cooldown timer for email OTP resend — uses composable
const { cooldown: emailCountdown, startCooldown: startEmailCountdown } = useCooldownTimer(60);

function resetEmailFlow() {
  emailStep.value = "request";
  emailForm.current_password = "";
  emailForm.new_email = "";
  resetEmailOtp();
  emailError.value = "";
  startEmailCountdown(0); // stop countdown
}

function handleOtpInput(e: Event, index: number) {
  const input = e.target as HTMLInputElement;
  const val = input.value.replace(/\D/g, "");
  if (val.length > 1) {
    // Paste support
    const digits = val.slice(0, 6).split("");
    for (let i = 0; i < 6; i++) {
      emailOtp.value[i] = digits[i] || "";
    }
    const lastIdx = Math.min(val.length, 5);
    const nextInput = input.parentElement?.querySelectorAll("input")[lastIdx] as HTMLInputElement;
    nextInput?.focus();
    return;
  }
  emailOtp.value[index] = val;
  if (val && index < 5) {
    const nextInput = input.parentElement?.querySelectorAll("input")[index + 1] as HTMLInputElement;
    nextInput?.focus();
  }
}

function handleOtpKeydown(e: KeyboardEvent, index: number) {
  if (e.key === "Backspace" && !emailOtp.value[index] && index > 0) {
    const inputs = (e.target as HTMLInputElement).parentElement?.querySelectorAll("input");
    (inputs?.[index - 1] as HTMLInputElement)?.focus();
  }
}

async function handleEmailRequest() {
  emailError.value = "";
  // Use pre-confirmed password if identity is verified, otherwise require inline
  const pw = identityConfirmed.value ? identityPassword.value : emailForm.current_password;
  if (!pw) {
    emailError.value = "Current password is required.";
    return;
  }
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(emailForm.new_email)) {
    emailError.value = "Please enter a valid email address.";
    return;
  }
  emailLoading.value = true;
  try {
    await requestEmailChange(pw, emailForm.new_email);
    showToast("A verification code has been sent to your current email.", "info");
    emailStep.value = "otp";
    emailOtp.value = ["", "", "", "", "", ""];
    startEmailCountdown();
  } catch (err) {
    const msg = getErrorMessage(err);
    emailError.value = msg;
    showToast(msg, "error");
  } finally {
    emailLoading.value = false;
  }
}

async function handleEmailOtpConfirm() {
  emailError.value = "";
  const otpStr = emailOtp.value.join("");
  if (otpStr.length !== 6) {
    emailError.value = "Please enter the complete 6-digit code.";
    return;
  }
  emailLoading.value = true;
  try {
    await confirmEmailChangeOTP(otpStr);
    emailStep.value = "done";
    showToast("Email changed successfully. Logging out...", "success");
    // Auto-logout after 2 seconds
    setTimeout(async () => {
      try {
        await logout();
      } catch {
        // Fallback: clear auth state and redirect
        authHelpers.clearAuth();
        // VUE 3 CONVENTION: Use navigateTo() instead of window.location.href
        setTimeout(() => { authHelpers.navigateTo("/auth/login"); }, 0);
      }
    }, 2000);
  } catch (err) {
    const msg = getErrorMessage(err);
    emailError.value = msg;
    showToast(msg, "error");
  } finally {
    emailLoading.value = false;
  }
}

async function handleResendEmailOtp() {
  if (emailCountdown.value > 0 || emailLoading.value) return;
  emailError.value = "";
  emailLoading.value = true;
  try {
    const pw = identityConfirmed.value ? identityPassword.value : emailForm.current_password;
    await requestEmailChange(pw, emailForm.new_email);
    showToast("A new verification code has been sent.", "info");
    emailOtp.value = ["", "", "", "", "", ""];
    startEmailCountdown();
  } catch (err) {
    const msg = getErrorMessage(err);
    emailError.value = msg;
    showToast(msg, "error");
  } finally {
    emailLoading.value = false;
  }
}

// ==================== Logout ====================
const showLogoutDialog = ref(false);
const logoutLoading = ref(false);

async function handleLogout() {
  showLogoutDialog.value = false;
  logoutLoading.value = true;
  try {
    await logout();
  } catch {
    showToast("Could not reach the server. Signing you out locally.", "warning");
  } finally {
    logoutLoading.value = false;
  }
}

// ==================== Identity Confirmation (Danger Zone Gate) ====================
const identityConfirmed = ref(false);
const identityPassword = ref(""); // temporarily held for subsequent sensitive ops
const identityLoading = ref(false);
const identityError = ref("");
const identityCountdown = ref(0); // seconds remaining
let identityTimer: ReturnType<typeof setInterval> | null = null;
const IDENTITY_DURATION = 300; // 5 minutes

function startIdentityTimer() {
  identityCountdown.value = IDENTITY_DURATION;
  identityTimer = setInterval(() => {
    identityCountdown.value--;
    if (identityCountdown.value <= 0) {
      clearIdentity();
    }
  }, 1000);
}

function clearIdentity() {
  identityConfirmed.value = false;
  identityPassword.value = "";
  identityCountdown.value = 0;
  if (identityTimer) {
    clearInterval(identityTimer);
    identityTimer = null;
  }
}

function formatIdentityTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

async function handleConfirmIdentity() {
  identityError.value = "";
  if (!identityPassword.value) {
    identityError.value = "Password is required.";
    return;
  }
  identityLoading.value = true;
  try {
    await confirmIdentity(identityPassword.value);
    identityConfirmed.value = true;
    showToast("Identity verified. You can now perform sensitive actions.", "success");
    startIdentityTimer();
  } catch (err) {
    const msg = getErrorMessage(err);
    identityError.value = msg;
    showToast(msg, "error");
  } finally {
    identityLoading.value = false;
  }
}

// ==================== GDPR Data Export ====================
const exportLoading = ref(false);

async function handleExportData() {
  exportLoading.value = true;
  try {
    const data = await billingApi.exportBillingData();

    // Build filename with user email and timestamp
    const emailPart = (data.user.email || "user").replace(/[^a-zA-Z0-9._-]/g, "_");
    const datePart = new Date().toISOString().slice(0, 10);
    const filename = `sattabase_billing_export_${emailPart}_${datePart}.json`;

    // Trigger browser download
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast("Billing data exported successfully.", "success");
  } catch (err) {
    const msg = getErrorMessage(err);
    showToast(msg, "error");
  } finally {
    exportLoading.value = false;
  }
}

// ==================== Delete Account ====================
const deleteForm = reactive({
  current_password: "",
  confirmText: "",
});
const showDeleteDialog = ref(false);
const deleteLoading = ref(false);
const deleteError = ref("");

const DELETE_CONFIRM_PHRASE = "DELETE MY ACCOUNT";

async function handleDeleteAccount() {
  deleteError.value = "";

  // Use pre-confirmed password if identity is verified, otherwise require inline
  const pw = identityConfirmed.value ? identityPassword.value : deleteForm.current_password;
  if (!pw) {
    deleteError.value = "Current password is required.";
    return;
  }

  if (deleteForm.confirmText !== DELETE_CONFIRM_PHRASE) {
    deleteError.value = `Type "${DELETE_CONFIRM_PHRASE}" exactly to confirm.`;
    return;
  }

  deleteLoading.value = true;
  try {
    await deleteAccount(pw);
    showToast("Account deleted. Redirecting...", "success");
    setTimeout(() => {
      // VUE 3 CONVENTION: Use navigateTo() instead of window.location.href
      authHelpers.navigateTo("/auth/login");
    }, 1000);
  } catch (err) {
    const msg = getErrorMessage(err);
    deleteError.value = msg;
    showToast(msg, "error");
  } finally {
    deleteLoading.value = false;
  }
}

function openDeleteDialog() {
  // If identity already confirmed, skip the password field
  deleteForm.current_password = identityConfirmed.value ? "*" : "";
  deleteForm.confirmText = "";
  deleteError.value = "";
  showDeleteDialog.value = true;
}

function closeDeleteDialog() {
  showDeleteDialog.value = false;
  deleteError.value = "";
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="mb-8">
      <h1 class="text-2xl font-bold tracking-tight">Settings</h1>
      <p class="mt-1 text-sm text-[var(--color-muted-foreground)]">
        Manage your account security and preferences
      </p>
    </div>

    <div class="space-y-6 max-w-2xl">
      <!-- ==================== Change Password ==================== -->
      <div class="card p-6">
        <div class="mb-4">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <svg class="h-5 w-5 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            Change Password
          </h2>
          <p class="mt-1 text-sm text-[var(--color-muted-foreground)]">
            Update your password. Requires current password.
          </p>
        </div>

        <div v-if="pwError" class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          {{ pwError }}
        </div>
        <div v-if="pwSuccess" class="mb-3 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-700 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300">
          {{ pwSuccess }}
        </div>

        <form @submit.prevent="handlePasswordChange" class="space-y-3">
          <div class="space-y-1">
            <label for="pw-current" class="label-text">Current password</label>
            <input id="pw-current" v-model="pwForm.current_password" type="password" required autocomplete="current-password" class="input-field" />
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="space-y-1">
              <label for="pw-new" class="label-text">New password</label>
              <input id="pw-new" v-model="pwForm.new_password" type="password" required minlength="8" autocomplete="new-password" class="input-field" />
            </div>
            <div class="space-y-1">
              <label for="pw-confirm" class="label-text">Confirm new password</label>
              <input id="pw-confirm" v-model="pwForm.confirm_password" type="password" required minlength="8" autocomplete="new-password" class="input-field" />
            </div>
          </div>
          <button type="submit" :disabled="pwLoading" class="btn-primary">
            {{ pwLoading ? "Changing..." : "Change password" }}
          </button>
        </form>
      </div>

      <!-- ==================== Change Email ==================== -->
      <div class="card p-6">
        <div class="mb-4 flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold flex items-center gap-2">
              <svg class="h-5 w-5 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              Change Email
            </h2>
            <p class="mt-1 text-sm text-[var(--color-muted-foreground)]">
              {{ identityConfirmed ? 'A 6-digit code will be sent to your current email.' : 'Requires current password. A 6-digit code will be sent to your current email.' }}
            </p>
          </div>
          <span v-if="identityConfirmed" class="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-950 dark:text-green-300">
            <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
            Verified {{ formatIdentityTime(identityCountdown) }}
          </span>
        </div>

        <div v-if="emailError" class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          {{ emailError }}
        </div>

        <!-- Step 1: Request -->
        <form v-if="emailStep === 'request'" @submit.prevent="handleEmailRequest" class="space-y-3">
          <div v-if="!identityConfirmed" class="space-y-1">
            <label for="email-current" class="label-text">Current password</label>
            <input id="email-current" v-model="emailForm.current_password" type="password" required autocomplete="current-password" class="input-field" />
          </div>
          <div v-else class="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-300">
            <svg class="inline h-4 w-4 mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
            Identity verified — password pre-filled. <button type="button" @click="clearIdentity()" class="underline hover:no-underline">Clear</button>
          </div>
          <div class="space-y-1">
            <label for="email-new" class="label-text">New email address</label>
            <input id="email-new" v-model="emailForm.new_email" type="email" required autocomplete="email" placeholder="new@example.com" class="input-field" />
          </div>
          <button type="submit" :disabled="emailLoading" class="btn-primary">
            {{ emailLoading ? "Sending code..." : "Send verification code" }}
          </button>
        </form>

        <!-- Step 2: Enter OTP -->
        <div v-else-if="emailStep === 'otp'" class="space-y-4">
          <div class="rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 dark:border-brand-800 dark:bg-brand-950">
            <p class="text-sm text-brand-700 dark:text-brand-300">
              <svg class="inline h-4 w-4 mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
              A code was sent to <strong>your current email</strong>. Changing to <strong>{{ emailForm.new_email }}</strong>.
            </p>
          </div>

          <div class="space-y-2">
            <label class="label-text">Enter 6-digit code</label>
            <div class="flex gap-2 justify-center">
              <input
                v-for="(_, i) in 6"
                :key="i"
                :ref="(el) => { if (el) (el as HTMLInputElement).value = emailOtp[i] }"
                type="text"
                inputmode="numeric"
                maxlength="1"
                class="input-field w-11 h-12 text-center text-lg font-mono"
                :disabled="emailLoading"
                @input="handleOtpInput($event, i)"
                @keydown="handleOtpKeydown($event, i)"
              />
            </div>
          </div>

          <div class="flex gap-2">
            <button @click="handleEmailOtpConfirm" :disabled="emailLoading || emailOtp.join('').length !== 6" class="btn-primary flex-1">
              {{ emailLoading ? "Verifying..." : "Confirm email change" }}
            </button>
            <button type="button" @click="resetEmailFlow" class="btn-ghost" :disabled="emailLoading">Cancel</button>
          </div>

          <button
            type="button"
            @click="handleResendEmailOtp"
            :disabled="emailCountdown > 0 || emailLoading"
            class="w-full text-center text-sm text-brand-600 hover:text-brand-500 dark:text-brand-400 disabled:text-muted-foreground disabled:cursor-not-allowed transition-colors"
          >
            {{ emailCountdown > 0 ? `Resend code in ${emailCountdown}s` : "Resend code" }}
          </button>
        </div>

        <!-- Step 3: Done -->
        <div v-else-if="emailStep === 'done'" class="text-center py-4">
          <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
            <svg class="h-6 w-6 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <p class="text-sm font-medium">Email changed! Logging you out...</p>
        </div>
      </div>

      <!-- ==================== Logout ==================== -->
      <div class="card p-6">
        <div class="mb-4">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <svg class="h-5 w-5 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Sign Out
          </h2>
          <p class="mt-1 text-sm text-[var(--color-muted-foreground)]">
            Sign out of your account on this device.
          </p>
        </div>

        <!-- Logout Confirmation Dialog -->
        <div v-if="showLogoutDialog" class="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-accent)] p-4">
          <p class="text-sm font-medium mb-3">Are you sure you want to sign out?</p>
          <div class="flex gap-2">
            <button
              @click="handleLogout"
              :disabled="logoutLoading"
              class="btn-secondary"
            >
              {{ logoutLoading ? "Signing out..." : "Yes, sign out" }}
            </button>
            <button
              @click="showLogoutDialog = false"
              class="btn-ghost"
              :disabled="logoutLoading"
            >
              Cancel
            </button>
          </div>
        </div>

        <button
          v-else
          @click="showLogoutDialog = true"
          class="btn-secondary"
        >
          Sign out
        </button>
      </div>

      <!-- ==================== GDPR Data Export ==================== -->
      <div class="card p-6">
        <div class="mb-4">
          <h2 class="text-lg font-semibold flex items-center gap-2">
            <svg class="h-5 w-5 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Export Your Data
          </h2>
          <p class="mt-1 text-sm text-[var(--color-muted-foreground)]">
            Download all your billing data (subscriptions, invoices, refunds) as a JSON file. Your right under GDPR Article 20.
          </p>
        </div>

        <button
          @click="handleExportData"
          :disabled="exportLoading"
          class="btn-secondary"
        >
          <svg v-if="!exportLoading" class="h-4 w-4 mr-1.5 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          <svg v-else class="h-4 w-4 mr-1.5 -mt-0.5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          {{ exportLoading ? "Exporting..." : "Export billing data" }}
        </button>
      </div>

      <!-- ==================== Danger Zone ==================== -->
      <div class="card p-6 border-red-200 dark:border-red-900">
        <div class="mb-4 flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-red-600 dark:text-red-400 flex items-center gap-2">
              <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              Danger Zone
            </h2>
            <p class="mt-1 text-sm text-[var(--color-muted-foreground)]">
              Permanently delete your account and all associated data. This action cannot be undone.
            </p>
          </div>
          <span v-if="identityConfirmed" class="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-950 dark:text-green-300">
            <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
            Verified {{ formatIdentityTime(identityCountdown) }}
          </span>
        </div>

        <!-- Identity Confirmation Gate -->
        <div v-if="!identityConfirmed" class="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950">
          <div class="flex items-start gap-3">
            <svg class="h-5 w-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <div class="flex-1">
              <p class="text-sm font-medium text-amber-700 dark:text-amber-300">
                Verify your identity to proceed
              </p>
              <p class="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                Enter your password to unlock sensitive actions. Your verification lasts 5 minutes.
              </p>
              <form @submit.prevent="handleConfirmIdentity" class="mt-3 flex gap-2">
                <input
                  v-model="identityPassword"
                  type="password"
                  required
                  autocomplete="current-password"
                  placeholder="Current password"
                  class="input-field flex-1"
                />
                <button type="submit" :disabled="identityLoading" class="btn-secondary shrink-0">
                  {{ identityLoading ? "Verifying..." : "Verify" }}
                </button>
              </form>
              <div v-if="identityError" class="mt-2 text-xs text-red-600 dark:text-red-400">
                {{ identityError }}
              </div>
            </div>
          </div>
        </div>

        <!-- Identity Confirmed Banner -->
        <div v-else class="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-800 dark:bg-green-950">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-green-700 dark:text-green-300">
              <svg class="inline h-4 w-4 mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
              Identity verified — expires in {{ formatIdentityTime(identityCountdown) }}
            </p>
            <button type="button" @click="clearIdentity()" class="text-xs text-green-600 hover:text-green-500 dark:text-green-400 underline">
              Clear
            </button>
          </div>
        </div>

        <!-- Delete Confirmation Modal -->
        <div v-if="showDeleteDialog">
          <div class="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950">
            <div v-if="deleteError" class="mb-3 rounded border border-red-300 bg-red-100 px-3 py-2 text-sm text-red-800 dark:border-red-700 dark:bg-red-900 dark:text-red-200">
              {{ deleteError }}
            </div>

            <p class="mb-3 text-sm font-medium text-red-700 dark:text-red-300">
              This will permanently delete your account and all your data.
            </p>
            <form @submit.prevent="handleDeleteAccount" class="space-y-3">
              <div v-if="!identityConfirmed" class="space-y-1">
                <label for="delete-pw" class="label-text">Current password</label>
                <input id="delete-pw" v-model="deleteForm.current_password" type="password" required autocomplete="current-password" class="input-field" />
              </div>
              <div v-else class="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-300">
                <svg class="inline h-4 w-4 mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
                Identity verified — password pre-filled.
              </div>
              <div class="space-y-1">
                <label for="delete-confirm" class="label-text">
                  Type <strong>{{ DELETE_CONFIRM_PHRASE }}</strong> to confirm
                </label>
                <input
                  id="delete-confirm"
                  v-model="deleteForm.confirmText"
                  type="text"
                  required
                  class="input-field"
                  :placeholder="DELETE_CONFIRM_PHRASE"
                />
              </div>
              <div class="flex gap-2">
                <button type="submit" :disabled="deleteLoading" class="btn-destructive">
                  {{ deleteLoading ? "Deleting..." : "Permanently delete my account" }}
                </button>
                <button type="button" @click="closeDeleteDialog" class="btn-secondary">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>

        <button
          v-else
          @click="openDeleteDialog"
          class="btn-destructive"
        >
          Delete account
        </button>
      </div>
    </div>
  </div>
</template>
