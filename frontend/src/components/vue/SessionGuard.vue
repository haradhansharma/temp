<script setup lang="ts">
/**
 * SessionGuard — invisible Vue component that monitors auth state
 * and automatically redirects to login when the session expires.
 *
 * VUE 3 CONVENTION: This component is the SOLE handler for auth-related
 * navigation. api.ts only emits events and sets flags — it never navigates.
 * This separation ensures that navigation always uses Astro's navigate()
 * from 'astro:transitions' (equivalent to router.push() in Vue Router),
 * properly deferred with setTimeout(0) to avoid race conditions with
 * Astro's View Transition lifecycle events.
 *
 * The "querySelector null" error was caused by calling navigate() or
 * window.location.replace() synchronously inside astro:before-preparation.
 * Now, all navigation is deferred to the next event loop tick, giving
 * Astro's router time to complete its transition lifecycle.
 *
 * Place this component ONCE in protected layouts (DashboardLayout, AdminLayout).
 * It renders nothing and handles:
 *
 * 1. Vue watch (via useSessionGuard): Detects when isLoggedIn transitions
 *    from true → false on a protected page and redirects to login.
 *
 * 2. Auth event listeners: Listens for "auth:session-expired" events from
 *    the API layer and redirects immediately (deferred with setTimeout).
 *
 * 3. Window CustomEvent fallback: Listens for "sb:auth:session-expired" on
 *    the window object. Backup path that works even when the module-level
 *    event listeners are lost during Astro View Transitions.
 *
 * 4. Astro navigate() registration: On mount, dynamically imports navigate()
 *    from 'astro:transitions' and registers it via registerNavigate() so that
 *    authHelpers.navigateTo() can use it. (Also registered in BaseLayout.astro
 *    as the primary registration — this is a safety net.)
 *
 * 5. Periodic session check: Every 15 seconds, verifies that we still have
 *    a valid access token on a protected page. If not, redirects.
 *
 * 6. astro:page-load handler: Checks for pending redirect flags set by
 *    api.ts during astro:before-preparation (when session expired during
 *    a cancelled transition).
 */

import { onMounted, onUnmounted } from "vue";
import { useAuth } from "@/composables/useAuth";
import { authHelpers, registerNavigate } from "@/lib/api";

const { useSessionGuard, isLoggedIn } = useAuth();

// Activate the session guard (sets up Vue watch + event listener + CustomEvent fallback)
useSessionGuard();

// VUE 3 CONVENTION: Register Astro's navigate() function on mount.
// This is a safety net — the primary registration is in BaseLayout.astro,
// which runs earlier. But if BaseLayout's script hasn't loaded yet (e.g.,
// during HMR or a module re-evaluation), this ensures navigate() is still
// available.
onMounted(async () => {
  try {
    const { navigate } = await import("astro:transitions/client");
    registerNavigate(navigate);
  } catch {
    // navigate() not available — already registered by BaseLayout.astro
  }
});

// ── Redirect helper (Vue 3 Convention) ──────────────────────────────────────
//
// All redirects go through this single function. It uses Astro's navigate()
// from 'astro:transitions' (equivalent to router.push() in Vue Router).
//
// CRITICAL: The redirect is DEFERRED with setTimeout(0) to avoid the
// "querySelector null" error. This error occurs when navigate() is called
// synchronously during an Astro View Transition lifecycle event
// (astro:before-preparation, astro:after-swap, etc.). By deferring to the
// next event loop tick, we ensure Astro's router has finished processing
// the current transition before we start a new navigation.
function scheduleRedirect(path: string): void {
  if (typeof window === "undefined") return;
  if (window.location.pathname.startsWith("/auth/")) return;

  // Defer navigation to the next event loop tick.
  // This is the Vue 3 equivalent of nextTick() for navigation —
  // it ensures the current event handler completes before navigation starts.
  setTimeout(() => {
    authHelpers.navigateTo(path);
  }, 0);
}

// ── Direct window CustomEvent listener ──────────────────────────────────────
//
// This is a LAST-RESORT redirect that fires even if:
// - The module-level onAuthEvent listeners were lost during View Transition
// - The Vue watch didn't fire because of reactivity issues
// - The useAuth.ts event sync was never re-registered after module re-evaluation
//
// SSR SAFE: Only register on the client — window is not available during SSR.
const handleSessionExpiredFallback = () => {
  scheduleRedirect("/auth/login");
};
if (typeof window !== "undefined") {
  window.addEventListener("sb:auth:session-expired", handleSessionExpiredFallback);
}

// ── astro:page-load handler ────────────────────────────────────────────────
//
// Checks for pending redirect flags set by api.ts during
// astro:before-preparation. When the session is expired during a transition,
// api.ts cancels the transition and sets __sb_redirect_reason. We pick it up
// here after the page loads and perform the redirect.
//
// This is the Vue 3 convention equivalent of a route guard:
// api.ts is the "store" that sets state, SessionGuard is the "guard" that
// reads state and navigates.
let pageLoadHandler: (() => void) | null = null;
if (typeof window !== "undefined") {
  pageLoadHandler = () => {
    // Check for pending redirect from api.ts
    const redirectReason = (window as any).__sb_redirect_reason;
    if (redirectReason) {
      delete (window as any).__sb_redirect_reason;
      scheduleRedirect("/auth/login");
    }
  };
  document.addEventListener("astro:page-load", pageLoadHandler);
}

// ── Periodic session health check ───────────────────────────────────────────
//
// This catches edge cases where all other redirect mechanisms fail:
// - The proactive refresh timer was cleared by a View Transition
// - The token expired between checks
// - The Vue watch didn't fire because of module re-evaluation
let sessionCheckInterval: ReturnType<typeof setInterval> | null = null;

if (typeof window !== "undefined") {
  sessionCheckInterval = setInterval(() => {
    const onProtectedPage = !window.location.pathname.startsWith("/auth/");

    if (onProtectedPage) {
      // Check the access token directly, not just isLoggedIn.
      const hasToken = authHelpers.isAuthenticated();

      if (!hasToken) {
        // No token — session is dead. Redirect using navigateTo().
        scheduleRedirect("/auth/login");
      }
    }
  }, 15_000); // Check every 15 seconds
}

// ── Cleanup on component unmount ────────────────────────────────────────────
onUnmounted(() => {
  if (sessionCheckInterval) {
    clearInterval(sessionCheckInterval);
    sessionCheckInterval = null;
  }
  if (typeof window !== "undefined") {
    window.removeEventListener("sb:auth:session-expired", handleSessionExpiredFallback);
  }
  if (pageLoadHandler && typeof document !== "undefined") {
    document.removeEventListener("astro:page-load", pageLoadHandler);
  }
});
</script>

<template>
  <!-- This component renders nothing — it's purely a side-effect guard -->
</template>
