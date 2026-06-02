<script setup lang="ts">
/**
 * AdminGuard — invisible Vue component that enforces admin role checks.
 *
 * SECURITY: This component is placed in AdminLayout.astro so it runs
 * on EVERY admin page. It uses useAdminGuard() to check if the current
 * user is_staff / owner / admin. If not, it redirects to /dashboard.
 *
 * This replaces the broken pattern of importing useAdminGuard in Astro
 * <script> blocks (which can't work because Vue composables need Vue's
 * reactive context). By placing it as a Vue island in the layout, the
 * guard runs reliably on every admin page.
 *
 * Place this component ONCE in AdminLayout.astro.
 * It renders nothing and only performs the admin role check + redirect.
 */
import { onMounted } from "vue";
import { useAdminGuard } from "@/composables/useAdminGuard";

const { isAuthorized, isLoading } = useAdminGuard();

// Show unauthorized message briefly before redirect (handled by useAdminGuard)
onMounted(() => {
  // useAdminGuard's onMounted handles the redirect automatically
  // if the user is not authorized. This component is just a vehicle
  // to mount the composable in the Vue reactive context.
});
</script>

<template>
  <!-- This component renders nothing — it's purely a side-effect guard -->
</template>
