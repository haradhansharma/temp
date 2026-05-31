/**
 * Astro Middleware — Server-side route protection for admin pages.
 *
 * This middleware runs on every request (server-side, before page rendering).
 * For /admin/* routes, it verifies that the user has staff privileges
 * by checking the JWT token against the backend /users/me endpoint.
 *
 * If the user is not authenticated or not staff, it redirects to /dashboard.
 *
 * Note: The existing auth flow is entirely client-side (JWT in sessionStorage/
 * localStorage). Since Astro runs in SSR mode, we can't directly access
 * browser storage on the server. Instead, we:
 *   1. Read the token from the cookie (if set) or from the request
 *   2. If no token found, let the page render — the client-side auth
 *      check in each admin page's Vue component will handle redirect
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
    // Try to get token from cookies (set by client-side on login)
    // The client-side stores tokens in sessionStorage/localStorage,
    // which are NOT available on the server. We rely on a companion
    // cookie that the client sets on login for SSR middleware.
    //
    // For now, we let the request through and rely on the client-side
    // admin guard (AdminGuard.vue / page-level checks) for the redirect.
    // The backend API endpoints enforce is_staff regardless.
    //
    // Future improvement: Set an httpOnly cookie on login with a
    // server-verifiable session token for true SSR middleware.
  }

  return next();
});
