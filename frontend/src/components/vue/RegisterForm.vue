<script setup lang="ts">
// Register form — Vue interactive island
// Handles POST /auth/register via auth.ts

import { ref, reactive, toRef, onMounted } from "vue";
import {
  register,
  getErrorMessage,
  fetchChoices,
  detectUserTimezone,
  detectUserLanguage,
} from "@/lib/auth";
import type { Choices } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import type { ApiError } from "@/lib/api";
import { usePasswordStrength, useFormErrors } from "@/composables";

const form = reactive({
  first_name: "",
  last_name: "",
  email: "",
  password: "",
  confirm_password: "",
  timezone: "UTC",
  currency: "USD",
  language: "en",
  agree_terms: false,
});

const loading = ref(false);
const choicesLoading = ref(true);
const choices = ref<Choices>({ timezones: [], currencies: [], languages: [] });

const { fieldErrors, generalError, clearErrors, setApiFieldErrors, setGeneralError } = useFormErrors([
  "first_name", "last_name", "email", "password", "confirm_password", "agree_terms",
]);

// Auto-detect preferences on mount
onMounted(async () => {
  try {
    choices.value = await fetchChoices();
    form.timezone = detectUserTimezone(choices.value.timezones);
    form.language = detectUserLanguage(choices.value.languages);
  } catch (err) {
    console.error("Failed to load choices:", err);
  } finally {
    choicesLoading.value = false;
  }
});

// Collapsible preferences section
const showPreferences = ref(false);

// Password strength — uses composable
const { passwordChecks, passwordStrength, strengthSegments, isValid: passwordValid } = usePasswordStrength(toRef(form, "password"));

function validateForm(): boolean {
  clearErrors();
  let valid = true;

  if (!form.first_name.trim()) {
    fieldErrors.first_name = "First name is required.";
    valid = false;
  }

  if (!form.email.trim()) {
    fieldErrors.email = "Email address is required.";
    valid = false;
  } else {
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(form.email)) {
      fieldErrors.email = "Please enter a valid email address.";
      valid = false;
    }
  }

  if (!form.password) {
    fieldErrors.password = "Password is required.";
    valid = false;
  } else if (!passwordValid.value) {
    fieldErrors.password = "Password does not meet all requirements.";
    valid = false;
  }

  if (form.password !== form.confirm_password) {
    fieldErrors.confirm_password = "Passwords do not match.";
    valid = false;
  }

  if (!form.agree_terms) {
    fieldErrors.agree_terms = "You must agree to the terms and conditions.";
    valid = false;
  }

  return valid;
}

async function handleSubmit() {
  if (!validateForm()) return;

  loading.value = true;
  clearErrors();

  try {
    await register({
      email: form.email.trim(),
      password: form.password,
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      timezone: form.timezone,
      currency: form.currency,
      language: form.language,
    });

    showToast("Account created successfully! Please verify your email.", "success");
    // Redirect to email verification page with the registered email
    // VUE 3 CONVENTION: Use Astro's navigate() for SPA-like redirect
    setTimeout(async () => {
      try {
        const { navigate } = await import("astro:transitions/client");
        navigate(`/auth/verify-email?email=${encodeURIComponent(form.email.trim())}`);
      } catch {
        // Fallback: full page reload if navigate() unavailable
        window.location.href = `/auth/verify-email?email=${encodeURIComponent(form.email.trim())}`;
      }
    }, 1500);
  } catch (err: unknown) {
    const apiErr = err as ApiError;

    // Map API-level field errors to local fieldErrors via composable
    setApiFieldErrors(apiErr.errors as Record<string, string[]>);

    const message = getErrorMessage(err);
    setGeneralError(message);
    showToast(message, "error");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div>
    <!-- Header with icon -->
    <div class="mb-6 text-center">
      <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 dark:bg-brand-950">
        <svg class="h-8 w-8 text-brand-600 dark:text-brand-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zM4 19.235v-.11a6.375 6.375 0 0112.75 0v.109A12.318 12.318 0 0110.374 21c-2.331 0-4.512-.645-6.374-1.766z" />
        </svg>
      </div>
      <h2 class="text-2xl font-bold tracking-tight">Create an account</h2>
      <p class="mt-2 text-sm text-[var(--color-muted-foreground)]">
        Start managing your finances with Satta Ledger
      </p>
    </div>

    <!-- General Error -->
    <div
      v-if="generalError"
      role="alert"
      class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
    >
      {{ generalError }}
    </div>

    <!-- Form -->
    <form @submit.prevent="handleSubmit" class="space-y-4">
      <!-- Name Row -->
      <div class="grid grid-cols-2 gap-3">
        <div class="space-y-2">
          <label for="reg-first" class="label-text">First name</label>
          <div class="relative">
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
              <svg class="h-4 w-4 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
              </svg>
            </div>
            <input
              id="reg-first"
              v-model="form.first_name"
              type="text"
              required
              autocomplete="given-name"
              placeholder="John"
              class="input-field pl-10"
              :class="{ 'border-red-500 ring-red-500': fieldErrors.first_name }"
              :aria-invalid="!!fieldErrors.first_name"
              :aria-describedby="fieldErrors.first_name ? 'reg-first-error' : undefined"
              :disabled="loading"
            />
          </div>
          <p
            v-if="fieldErrors.first_name"
            id="reg-first-error"
            class="text-xs text-red-500"
            role="alert"
          >
            {{ fieldErrors.first_name }}
          </p>
        </div>
        <div class="space-y-2">
          <label for="reg-last" class="label-text">Last name</label>
          <div class="relative">
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
              <svg class="h-4 w-4 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
              </svg>
            </div>
            <input
              id="reg-last"
              v-model="form.last_name"
              type="text"
              autocomplete="family-name"
              placeholder="Doe"
              class="input-field pl-10"
              :disabled="loading"
            />
          </div>
        </div>
      </div>

      <!-- Email -->
      <div class="space-y-2">
        <label for="reg-email" class="label-text">Email address</label>
        <div class="relative">
          <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <svg class="h-4 w-4 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <input
            id="reg-email"
            v-model="form.email"
            type="email"
            required
            autocomplete="email"
            placeholder="you@example.com"
            class="input-field pl-10"
            :class="{ 'border-red-500 ring-red-500': fieldErrors.email }"
            :aria-invalid="!!fieldErrors.email"
            :aria-describedby="fieldErrors.email ? 'reg-email-error' : undefined"
            :disabled="loading"
          />
        </div>
        <p
          v-if="fieldErrors.email"
          id="reg-email-error"
          class="text-xs text-red-500"
          role="alert"
        >
          {{ fieldErrors.email }}
        </p>
      </div>

      <!-- Password -->
      <div class="space-y-2">
        <label for="reg-password" class="label-text">Password</label>
        <div class="relative">
          <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <svg class="h-4 w-4 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <input
            id="reg-password"
            v-model="form.password"
            type="password"
            required
            autocomplete="new-password"
            placeholder="Create a strong password"
            class="input-field pl-10"
            :class="{ 'border-red-500 ring-red-500': fieldErrors.password }"
            :aria-invalid="!!fieldErrors.password"
            :aria-describedby="fieldErrors.password ? 'reg-password-error' : 'reg-password-strength'"
            :disabled="loading"
          />
        </div>
        <p
          v-if="fieldErrors.password"
          id="reg-password-error"
          class="text-xs text-red-500"
          role="alert"
        >
          {{ fieldErrors.password }}
        </p>

        <!-- Password Strength Bar -->
        <div v-if="form.password.length > 0" id="reg-password-strength" class="space-y-2">
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

          <!-- Password strength hints -->
          <ul class="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs transition-all duration-300">
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
        <label for="reg-confirm" class="label-text">Confirm password</label>
        <div class="relative">
          <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <svg class="h-4 w-4 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <input
            id="reg-confirm"
            v-model="form.confirm_password"
            type="password"
            required
            autocomplete="new-password"
            placeholder="Re-enter your password"
            class="input-field pl-10"
            :class="{
              'border-red-500 ring-red-500': fieldErrors.confirm_password || (form.confirm_password && form.password !== form.confirm_password)
            }"
            :aria-invalid="!!(fieldErrors.confirm_password || (form.confirm_password && form.password !== form.confirm_password))"
            :aria-describedby="
              fieldErrors.confirm_password ? 'reg-confirm-error' :
              (form.confirm_password && form.password !== form.confirm_password) ? 'reg-confirm-mismatch' : undefined
            "
            :disabled="loading"
          />
        </div>
        <p
          v-if="fieldErrors.confirm_password"
          id="reg-confirm-error"
          class="text-xs text-red-500"
          role="alert"
        >
          {{ fieldErrors.confirm_password }}
        </p>
        <p
          v-else-if="form.confirm_password && form.password !== form.confirm_password"
          id="reg-confirm-mismatch"
          class="text-xs text-red-500"
        >
          Passwords do not match
        </p>
      </div>

      <!-- Preferences (Collapsible) -->
      <div class="rounded-lg border border-[var(--color-border)]">
        <button
          type="button"
          @click="showPreferences = !showPreferences"
          class="flex w-full items-center justify-between px-4 py-3 text-sm font-medium transition-colors hover:bg-[var(--color-accent)]"
          :disabled="loading"
        >
          <span class="flex items-center gap-2">
            <svg class="h-4 w-4 text-[var(--color-muted-foreground)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Preferences
          </span>
          <svg
            class="h-4 w-4 text-[var(--color-muted-foreground)] transition-transform duration-200"
            :class="{ 'rotate-180': showPreferences }"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        <div v-show="showPreferences" class="border-t border-[var(--color-border)] px-4 py-3 space-y-3">
          <!-- Timezone -->
          <div class="space-y-1">
            <label for="reg-timezone" class="label-text text-xs">Timezone</label>
            <select
              id="reg-timezone"
              v-model="form.timezone"
              class="input-field"
              :disabled="loading || choicesLoading"
            >
              <option v-for="tz in choices.timezones" :key="tz.value" :value="tz.value">
                {{ tz.label }}
              </option>
            </select>
          </div>
          <!-- Currency & Language Row -->
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1">
              <label for="reg-currency" class="label-text text-xs">Currency</label>
              <select
                id="reg-currency"
                v-model="form.currency"
                class="input-field"
                :disabled="loading || choicesLoading"
              >
                <option v-for="c in choices.currencies" :key="c.value" :value="c.value">
                  {{ c.label }}
                </option>
              </select>
            </div>
            <div class="space-y-1">
              <label for="reg-language" class="label-text text-xs">Language</label>
              <select
                id="reg-language"
                v-model="form.language"
                class="input-field"
                :disabled="loading || choicesLoading"
              >
                <option v-for="l in choices.languages" :key="l.value" :value="l.value">
                  {{ l.label }}
                </option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- Terms -->
      <div class="flex items-start gap-2">
        <input
          id="reg-terms"
          v-model="form.agree_terms"
          type="checkbox"
          required
          class="mt-1 h-4 w-4 rounded border-[var(--color-input)]"
          :aria-invalid="!!fieldErrors.agree_terms"
          :aria-describedby="fieldErrors.agree_terms ? 'reg-terms-error' : undefined"
          :disabled="loading"
        />
        <label for="reg-terms" class="text-sm text-[var(--color-muted-foreground)]">
          I agree to the
          <a href="#" class="text-brand-600 hover:text-brand-500 dark:text-brand-400">Terms of Service</a>
          and
          <a href="#" class="text-brand-600 hover:text-brand-500 dark:text-brand-400">Privacy Policy</a>
        </label>
      </div>
      <p
        v-if="fieldErrors.agree_terms"
        id="reg-terms-error"
        class="text-xs text-red-500"
        role="alert"
      >
        {{ fieldErrors.agree_terms }}
      </p>

      <!-- Submit -->
      <button
        type="submit"
        :disabled="loading"
        class="btn-primary w-full"
        aria-label="Create your account"
      >
        <svg v-if="loading" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        {{ loading ? "Creating account..." : "Create account" }}
      </button>
    </form>

    <!-- Footer -->
    <p class="mt-6 text-center text-sm text-[var(--color-muted-foreground)]">
      Already have an account?
      <a
        href="/auth/login"
        class="font-medium text-brand-600 hover:text-brand-500 dark:text-brand-400"
      >
        Sign in
      </a>
    </p>
  </div>
</template>
