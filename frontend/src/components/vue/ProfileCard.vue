<script setup lang="ts">
// Profile card — Vue interactive island
// GET /users/me (display) + PUT /users/me (update)

import { ref, reactive, computed, onMounted } from "vue";
import { useAuth } from "@/composables";
import {
  updateProfile,
  updateAvatar,
  deleteAvatar,
  requestEmailVerification,
  getErrorMessage,
  fetchChoices,
} from "@/lib/auth";
import type { Choices, ChoiceOption } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { getMediaUrl } from "@/lib/api";
import type { UserProfile } from "@/lib/auth";
import SearchableSelect from "@/components/vue/SearchableSelect.vue";
import type { SelectOption } from "@/components/vue/SearchableSelect.vue";

const { user, loading, initAuth } = useAuth();
const editing = ref(false);
const saving = ref(false);
const error = ref("");
const fieldErrors = ref<Record<string, string>>({});
const resendLoading = ref(false);
const resendCooldown = ref(0);
const avatarUploading = ref(false);
const avatarDeleting = ref(false);
const avatarError = ref("");
const fileInputRef = ref<HTMLInputElement | null>(null);

const form = reactive({
  first_name: "",
  last_name: "",
  phone: "",
  timezone: "UTC",
  currency: "USD",
  language: "en",
});

// ─── Choices from API (synced with backend enums) ────────────────────────────

const choices = ref<Choices>({ timezones: [], currencies: [], languages: [] });

function toSelectOptions(items: ChoiceOption[]): SelectOption[] {
  return items.map((item) => ({ value: item.value, label: item.label }));
}

const currencyOptions = computed(() => toSelectOptions(choices.value.currencies));
const languageOptions = computed(() => toSelectOptions(choices.value.languages));
const timezoneOptions = computed(() => toSelectOptions(choices.value.timezones));

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(async () => {
  const authenticated = await initAuth();
  if (!authenticated) return;

  // Fetch choices first (public endpoint, no auth issues)
  try {
    choices.value = await fetchChoices();
  } catch (err) {
    console.error("Failed to load choices:", err);
  }

  // User profile is already loaded by useAuth's initAuth()
  populateForm();
});

function populateForm() {
  if (!user.value) return;
  form.first_name = user.value.first_name;
  form.last_name = user.value.last_name;
  form.phone = user.value.phone;
  form.timezone = user.value.timezone;
  form.currency = user.value.currency;
  form.language = user.value.language;
}

function startEditing() {
  populateForm();
  editing.value = true;
  error.value = "";
  fieldErrors.value = {};
}

function cancelEditing() {
  editing.value = false;
  error.value = "";
  fieldErrors.value = {};
}

async function handleSave() {
  error.value = "";
  fieldErrors.value = {};
  saving.value = true;

  try {
    const updated = await updateProfile({
      first_name: form.first_name,
      last_name: form.last_name,
      phone: form.phone,
      timezone: form.timezone,
      currency: form.currency,
      language: form.language,
    });
    user.value = updated;
    editing.value = false;
    showToast("Profile updated successfully.", "success");
  } catch (err: any) {
    const msg = getErrorMessage(err);
    error.value = msg;
    if (err?.errors && typeof err.errors === "object") {
      fieldErrors.value = {};
      for (const [field, messages] of Object.entries(err.errors)) {
        if (Array.isArray(messages) && messages.length > 0) {
          fieldErrors.value[field] = messages[0];
        }
      }
    }
    showToast(msg, "error");
  } finally {
    saving.value = false;
  }
}

// ─── Avatar upload ───────────────────────────────────────────────────────

function triggerAvatarUpload() {
  avatarError.value = "";
  fileInputRef.value?.click();
}

async function handleAvatarChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  avatarUploading.value = true;
  avatarError.value = "";

  try {
    const updated = await updateAvatar(file);
    user.value = updated;
    showToast("Avatar updated successfully.", "success");
  } catch (err: any) {
    const msg = getErrorMessage(err);
    avatarError.value = msg;
    showToast(msg, "error");
  } finally {
    avatarUploading.value = false;
    // Reset input so the same file can be selected again
    if (fileInputRef.value) fileInputRef.value.value = "";
  }
}

async function handleAvatarRemove() {
  if (!user.value?.avatar) return;

  avatarDeleting.value = true;
  avatarError.value = "";

  try {
    const updated = await deleteAvatar();
    user.value = updated;
    showToast("Avatar removed.", "success");
  } catch (err: any) {
    const msg = getErrorMessage(err);
    avatarError.value = msg;
    showToast(msg, "error");
  } finally {
    avatarDeleting.value = false;
  }
}

// ─── Resend verification ────────────────────────────────────────────────────

async function handleResendVerification() {
  if (!user.value || resendCooldown.value > 0) return;

  resendLoading.value = true;
  try {
    await requestEmailVerification(user.value.email);
    showToast("Verification email sent!", "success");
    startResendCooldown();
  } catch (err) {
    showToast(getErrorMessage(err), "error");
  } finally {
    resendLoading.value = false;
  }
}

function startResendCooldown(seconds: number = 60) {
  resendCooldown.value = seconds;
  const interval = setInterval(() => {
    resendCooldown.value--;
    if (resendCooldown.value <= 0) {
      clearInterval(interval);
    }
  }, 1000);
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function getInitials(): string {
  if (!user.value) return "?";
  return (
    (user.value.first_name?.[0] || "") + (user.value.last_name?.[0] || "")
  ).toUpperCase() || "?";
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function getFieldError(field: string): string {
  return fieldErrors.value[field] || "";
}

function getCurrencyLabel(code: string): string {
  return Array.isArray(currencyOptions) ? currencyOptions.find((c) => c.value === code)?.label || code : code;
}

function getTimezoneLabel(tz: string): string {
  return Array.isArray(timezoneOptions) ? timezoneOptions.find((t) => t.value === tz)?.label || tz : tz;
}

function getLanguageLabel(code: string): string {
  return Array.isArray(languageOptions) ? languageOptions.find((l) => l.value === code)?.label || code : code;
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="mb-8 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Profile</h1>
        <p class="mt-1 text-sm text-[var(--color-muted-foreground)]">
          Manage your personal information
        </p>
      </div>
      <button
        v-if="!editing && user"
        @click="startEditing"
        class="btn-secondary"
      >
        Edit profile
      </button>
    </div>

    <!-- Loading Skeleton -->
    <div v-if="loading" class="grid gap-6 lg:grid-cols-3">
      <div class="card p-6 text-center animate-pulse">
        <div class="mx-auto mb-4 h-20 w-20 rounded-full bg-[var(--color-muted)]" />
        <div class="mx-auto mb-2 h-5 w-32 rounded bg-[var(--color-muted)]" />
        <div class="mx-auto mb-4 h-4 w-48 rounded bg-[var(--color-muted)]" />
        <div class="flex justify-center gap-2">
          <div class="h-5 w-16 rounded-full bg-[var(--color-muted)]" />
          <div class="h-5 w-12 rounded-full bg-[var(--color-muted)]" />
        </div>
      </div>
      <div class="card p-6 lg:col-span-2 animate-pulse">
        <div class="grid gap-4 sm:grid-cols-2">
          <div v-for="i in 8" :key="i">
            <div class="mb-1 h-3 w-20 rounded bg-[var(--color-muted)]" />
            <div class="h-4 w-36 rounded bg-[var(--color-muted)]" />
          </div>
        </div>
      </div>
    </div>

    <!-- Error: Not loaded -->
    <div v-else-if="!user" class="card p-8 text-center">
      <p class="text-[var(--color-muted-foreground)]">
        Unable to load profile data. Please try refreshing the page.
      </p>
    </div>

    <!-- Profile Content -->
    <div v-else class="grid gap-6 lg:grid-cols-3">
      <!-- Left: Avatar Card -->
      <div class="card p-6 text-center">
        <div class="relative mx-auto mb-4">
          <div
            v-if="user.avatar"
            class="mx-auto h-20 w-20 overflow-hidden rounded-full"
          >
            <img
              :src="getMediaUrl(user.avatar) ?? undefined"
              :alt="`${user.full_name}'s avatar`"
              class="h-full w-full object-cover"
            />
          </div>
          <div
            v-else
            class="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-brand-100 text-2xl font-bold text-brand-700 dark:bg-brand-950 dark:text-brand-300"
          >
            {{ getInitials() }}
          </div>
          <!-- Hidden file input for avatar upload -->
          <input
            ref="fileInputRef"
            type="file"
            accept="image/jpeg,image/png,image/gif,image/webp"
            class="hidden"
            @change="handleAvatarChange"
          />
          <!-- Upload button -->
          <button
            type="button"
            @click="triggerAvatarUpload"
            :disabled="avatarUploading"
            class="absolute bottom-0 right-0 flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-white shadow-sm hover:bg-brand-700 transition-colors"
            :class="{ 'opacity-50 cursor-wait': avatarUploading }"
            aria-label="Upload avatar"
            title="Upload avatar (JPEG, PNG, GIF, WebP — max 2 MB)"
          >
            <svg v-if="!avatarUploading" class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <svg v-else class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </button>
          <!-- Remove avatar button (only shown when avatar exists) -->
          <button
            v-if="user.avatar && !avatarUploading"
            type="button"
            @click="handleAvatarRemove"
            :disabled="avatarDeleting"
            class="absolute top-0 right-0 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white shadow-sm hover:bg-red-600 transition-colors"
            :class="{ 'opacity-50 cursor-wait': avatarDeleting }"
            aria-label="Remove avatar"
            title="Remove avatar"
          >
            <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <!-- Avatar error -->
          <p v-if="avatarError" class="mt-2 text-xs text-red-600 dark:text-red-400">{{ avatarError }}</p>
        </div>
        <h3 class="text-lg font-semibold">{{ user.full_name }}</h3>
        <p class="text-sm text-[var(--color-muted-foreground)]">{{ user.email }}</p>
        <div class="mt-3 flex items-center justify-center gap-2">
          <span
            :class="[
              'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium',
              user.is_email_verified
                ? 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300'
                : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300'
            ]"
          >
            <svg v-if="user.is_email_verified" class="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
            </svg>
            <svg v-else class="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
            {{ user.is_email_verified ? "Verified" : "Unverified" }}
          </span>
          <span class="inline-flex items-center rounded-full bg-[var(--color-muted)] px-2.5 py-0.5 text-xs font-medium capitalize">
            {{ user.role }}
          </span>
        </div>
        <p class="mt-4 text-xs text-[var(--color-muted-foreground)]">
          Member since {{ formatDate(user.created_at) }}
        </p>
        <!-- Resend verification -->
        <div v-if="!user.is_email_verified" class="mt-4 border-t border-[var(--color-border)] pt-4">
          <p class="mb-2 text-xs text-yellow-600 dark:text-yellow-400">
            Your email is not verified. Some features may be limited.
          </p>
          <a
            href="/auth/verify-email"
            class="btn-ghost text-xs w-full"
            aria-label="Verify your email address"
          >
            Verify email now
          </a>
          <button
            type="button"
            @click="handleResendVerification"
            :disabled="resendLoading || resendCooldown > 0"
            class="btn-ghost text-xs w-full mt-2"
            :class="{ 'opacity-50 cursor-not-allowed': resendCooldown > 0 }"
          >
            <svg v-if="resendLoading" class="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            {{ resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend verification email" }}
          </button>
        </div>
      </div>

      <!-- Right: Form / Info -->
      <div class="card p-6 lg:col-span-2">
        <!-- Alerts -->
        <div v-if="error" class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
          {{ error }}
        </div>

        <!-- View Mode -->
        <div v-if="!editing" class="space-y-6">
          <div class="grid gap-4 sm:grid-cols-2">
            <div>
              <p class="text-xs font-medium text-[var(--color-muted-foreground)] uppercase tracking-wider">First name</p>
              <p class="mt-1 text-sm font-medium">{{ user.first_name || "—" }}</p>
            </div>
            <div>
              <p class="text-xs font-medium text-[var(--color-muted-foreground)] uppercase tracking-wider">Last name</p>
              <p class="mt-1 text-sm font-medium">{{ user.last_name || "—" }}</p>
            </div>
            <div>
              <p class="text-xs font-medium text-[var(--color-muted-foreground)] uppercase tracking-wider">Email</p>
              <p class="mt-1 text-sm font-medium">{{ user.email }}</p>
            </div>
            <div>
              <p class="text-xs font-medium text-[var(--color-muted-foreground)] uppercase tracking-wider">Phone</p>
              <p class="mt-1 text-sm font-medium">{{ user.phone || "—" }}</p>
            </div>
            <div>
              <p class="text-xs font-medium text-[var(--color-muted-foreground)] uppercase tracking-wider">Timezone</p>
              <p class="mt-1 text-sm font-medium">{{ getTimezoneLabel(user.timezone) }}</p>
              <p class="mt-0.5 text-xs text-[var(--color-muted-foreground)] font-mono">{{ user.timezone }}</p>
            </div>
            <div>
              <p class="text-xs font-medium text-[var(--color-muted-foreground)] uppercase tracking-wider">Currency</p>
              <p class="mt-1 text-sm font-medium">{{ getCurrencyLabel(user.currency) }}</p>
            </div>
            <div>
              <p class="text-xs font-medium text-[var(--color-muted-foreground)] uppercase tracking-wider">Language</p>
              <p class="mt-1 text-sm font-medium">{{ getLanguageLabel(user.language) }}</p>
            </div>
            <div>
              <p class="text-xs font-medium text-[var(--color-muted-foreground)] uppercase tracking-wider">Slug</p>
              <p class="mt-1 font-mono text-xs">{{ user.slug }}</p>
            </div>
          </div>
        </div>

        <!-- Edit Mode -->
        <form v-else @submit.prevent="handleSave" class="space-y-4">
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="space-y-2">
              <label for="profile-first" class="label-text">First name</label>
              <input id="profile-first" v-model="form.first_name" type="text" class="input-field" :class="{ 'border-red-400 dark:border-red-600': getFieldError('first_name') }" />
              <p v-if="getFieldError('first_name')" class="text-xs text-red-600 dark:text-red-400">{{ getFieldError('first_name') }}</p>
            </div>
            <div class="space-y-2">
              <label for="profile-last" class="label-text">Last name</label>
              <input id="profile-last" v-model="form.last_name" type="text" class="input-field" :class="{ 'border-red-400 dark:border-red-600': getFieldError('last_name') }" />
              <p v-if="getFieldError('last_name')" class="text-xs text-red-600 dark:text-red-400">{{ getFieldError('last_name') }}</p>
            </div>
            <div class="space-y-2">
              <label for="profile-phone" class="label-text">Phone</label>
              <input id="profile-phone" v-model="form.phone" type="tel" class="input-field" placeholder="+1 (555) 000-0000" :class="{ 'border-red-400 dark:border-red-600': getFieldError('phone') }" />
              <p v-if="getFieldError('phone')" class="text-xs text-red-600 dark:text-red-400">{{ getFieldError('phone') }}</p>
            </div>
            <div class="space-y-2">
              <label class="label-text">Timezone</label>
              <SearchableSelect
                v-model="form.timezone"
                :options="timezoneOptions"
                placeholder="Select timezone"
                search-placeholder="Search timezones..."
              />
              <p v-if="getFieldError('timezone')" class="text-xs text-red-600 dark:text-red-400">{{ getFieldError('timezone') }}</p>
            </div>
            <div class="space-y-2">
              <label class="label-text">Currency</label>
              <SearchableSelect
                v-model="form.currency"
                :options="currencyOptions"
                placeholder="Select currency"
                search-placeholder="Search currencies..."
              />
              <p v-if="getFieldError('currency')" class="text-xs text-red-600 dark:text-red-400">{{ getFieldError('currency') }}</p>
            </div>
            <div class="space-y-2">
              <label class="label-text">Language</label>
              <SearchableSelect
                v-model="form.language"
                :options="languageOptions"
                placeholder="Select language"
                search-placeholder="Search languages..."
              />
              <p v-if="getFieldError('language')" class="text-xs text-red-600 dark:text-red-400">{{ getFieldError('language') }}</p>
            </div>
          </div>
          <div class="flex gap-3 pt-2">
            <button type="submit" :disabled="saving" class="btn-primary">
              {{ saving ? "Saving..." : "Save changes" }}
            </button>
            <button type="button" @click="cancelEditing" class="btn-secondary">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
