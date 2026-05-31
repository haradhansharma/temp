<template>
  <div class="flex flex-col items-center gap-4 p-8">
    <!-- Loading state -->
    <div v-if="status === 'loading'" class="flex flex-col items-center gap-4">
      <div
        class="h-10 w-10 animate-spin rounded-full border-4 border-brand-200 border-t-brand-600"
      ></div>
      <p class="text-lg font-medium text-gray-700 dark:text-gray-300">
        Completing sign-in...
      </p>
      <p class="text-sm text-gray-500 dark:text-gray-400">
        You'll be redirected automatically.
      </p>
    </div>

    <!-- Error state -->
    <div v-else-if="status === 'error'" class="flex flex-col items-center gap-4">
      <div
        class="flex h-14 w-14 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30"
      >
        <svg class="h-7 w-7 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </div>
      <p class="text-lg font-medium text-gray-700 dark:text-gray-300">
        Sign-in failed
      </p>
      <p class="text-sm text-gray-500 dark:text-gray-400 text-center max-w-md">
        {{ errorMessage }}
      </p>
      <a
        href="/auth/login"
        class="mt-2 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors"
      >
        Go to Login
      </a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { exchangeAuthCode } from '@lib/auth';

const status = ref<'loading' | 'error'>('loading');
const errorMessage = ref('Something went wrong. Please try logging in again.');

onMounted(async () => {
  try {
    // Parse the authorization code and return URL from query params
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const returnTo = params.get('return_to') || '/dashboard';

    if (!code) {
      status.value = 'error';
      errorMessage.value = 'No authorization code found in the URL. Please try again from the sister domain.';
      return;
    }

    // Exchange the one-time code for JWT tokens
    await exchangeAuthCode(code);

    // Tokens are now stored in the base domain's storage.
    // Redirect to the intended destination.
    window.location.href = returnTo;
  } catch (err: any) {
    status.value = 'error';

    // Map common error messages to user-friendly text
    const msg = err?.message || '';
    if (msg.includes('expired')) {
      errorMessage.value = 'The authorization code has expired. Please try again from the sister domain.';
    } else if (msg.includes('Invalid')) {
      errorMessage.value = 'The authorization code is invalid or has already been used.';
    } else if (msg.includes('not verified')) {
      errorMessage.value = 'Your email has not been verified. Please verify your email first.';
    } else {
      errorMessage.value = 'Unable to complete sign-in. Please try logging in directly.';
    }

    console.error('[AuthCallback] Code exchange failed:', err);
  }
});
</script>
