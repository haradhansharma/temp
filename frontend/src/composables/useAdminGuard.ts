/**
 * useAdminGuard — Client-side composable for admin route protection.
 *
 * Checks if the current user is staff (is_staff or owner/admin role).
 * If not, redirects to /dashboard. This is the primary admin route
 * guard since tokens are stored client-side (window.__sb_auth + httpOnly cookie)
 * and cannot be accessed server-side.
 *
 * VUE 3 CONVENTION: Navigation uses authHelpers.navigateTo() (Astro's
 * navigate() from 'astro:transitions') instead of window.location.href,
 * deferred with setTimeout(0) to avoid the "querySelector null" error
 * during View Transitions.
 *
 * Usage in admin page components:
 *   <script setup>
 *   import { useAdminGuard } from "@/composables/useAdminGuard";
 *   const { isAuthorized, isLoading } = useAdminGuard();
 *   </script>
 *
 *   <template>
 *     <div v-if="isLoading">Loading...</div>
 *     <div v-else-if="isAuthorized">Admin content here</div>
 *   </template>
 */
import { ref, onMounted } from "vue";

interface AdminUser {
  is_staff: boolean;
  role: string;
  email: string;
  display_name?: string;
}

export function useAdminGuard() {
  const isAuthorized = ref(false);
  const isLoading = ref(true);
  const adminUser = ref<AdminUser | null>(null);

  onMounted(async () => {
    try {
      const { apiClient, authHelpers } = await import("@/lib/api");
      const user = await apiClient.get<AdminUser>("/users/me");

      const hasAccess =
        user.is_staff === true ||
        user.role === "owner" ||
        user.role === "admin";

      if (hasAccess) {
        isAuthorized.value = true;
        adminUser.value = user;
      } else {
        // Not authorized — redirect to user dashboard
        // VUE 3 CONVENTION: Use navigateTo() deferred with setTimeout
        setTimeout(() => {
          authHelpers.navigateTo("/dashboard");
        }, 0);
      }
    } catch {
      // Not authenticated — redirect to login
      // VUE 3 CONVENTION: Use navigateTo() deferred with setTimeout
      const { authHelpers } = await import("@/lib/api");
      setTimeout(() => {
        authHelpers.navigateTo("/auth/login");
      }, 0);
    } finally {
      isLoading.value = false;
    }
  });

  return { isAuthorized, isLoading, adminUser };
}
