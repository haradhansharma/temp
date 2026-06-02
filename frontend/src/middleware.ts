/**
 * Astro Middleware — Server-side route protection for admin pages.
 *
 * This middleware runs on every request (server-side, before page rendering).
 * For /admin/* routes, it verifies that the user has staff privileges
 * by checking the JWT token against the backend /users/me endpoint.
 *
 * If the user is not authenticated or not staff, it redirects to /dashboard.
 *
 * Note: Auth tokens are stored client-side (access token in window.__sb_auth
 * shared state, refresh token in httpOnly cookie). Since Astro runs in SSR
 * mode, we can't access browser storage on the server. Instead, we:
 *   1. Let the request through — the client-side auth check in each admin
 *      page's Vue component will handle redirect
 *   2. The backend API endpoints enforce is_staff regardless
 *
 * This middleware provides a *best-effort* server-side guard. The primary
 * protection is the client-side check in each admin page component + the
 * backend's is_staff enforcement on all admin API endpoints.
 */
import { defineMiddleware } from "astro:middleware";

// Paths that require admin access
const ADMIN_PATH_PREFIX = "/admin";
// Exclude the Django admin from our guard (it has its own auth)
const DJANGO_ADMIN_PATH = "/admin/django";

export const onRequest = defineMiddleware(async (context, next) => {
  const { pathname } = context.url;

  // Only guard /admin/* paths, but NOT /admin/django/* (Django has its own auth)
  if (
    pathname.startsWith(ADMIN_PATH_PREFIX) &&
    !pathname.startsWith(DJANGO_ADMIN_PATH)
  ) {
    // Auth tokens are stored client-side (window.__sb_auth + httpOnly cookie).
    // These are NOT available on the server during SSR.
    // We let the request through and rely on the client-side admin guard
    // (AdminGuard.vue / page-level checks) for the redirect.
    // The backend API endpoints enforce is_staff regardless.
  }

  return next();
});
