/**
 * useMediaQuery — reactive CSS media query matching.
 *
 * Provides a reactive boolean ref that tracks whether a CSS media query
 * matches the current viewport. Updates automatically on resize.
 *
 * Usage:
 *   const { isMobile } = useMediaQuery("(max-width: 768px)");
 *   const { isDesktop } = useMediaQuery("(min-width: 1024px)");
 */

import { ref, onMounted, onUnmounted } from "vue";

export function useMediaQuery(query: string) {
  const matches = ref(false);
  let mediaQuery: MediaQueryList | null = null;

  function handleChange(e: MediaQueryListEvent | MediaQueryList) {
    matches.value = e.matches;
  }

  onMounted(() => {
    if (typeof window === "undefined") return;
    mediaQuery = window.matchMedia(query);
    matches.value = mediaQuery.matches;
    mediaQuery.addEventListener("change", handleChange as (e: MediaQueryListEvent) => void);
  });

  onUnmounted(() => {
    if (mediaQuery) {
      mediaQuery.removeEventListener("change", handleChange as (e: MediaQueryListEvent) => void);
    }
  });

  return { matches };
}
