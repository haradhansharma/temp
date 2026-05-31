/**
 * useAsyncAction — generic async action state composable.
 *
 * Provides loading/error state management for async operations.
 * Eliminates duplicated loading ref + try/catch/finally patterns
 * across every component.
 *
 * Usage:
 *   const { loading, error, execute } = useAsyncAction();
 *   await execute(async () => {
 *     await someApiCall();
 *   }, { successMessage: "Saved!" });
 */

import { ref } from "vue";
import { getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";

export interface AsyncActionOptions {
  /** Show a success toast with this message */
  successMessage?: string;
  /** Show an error toast automatically */
  showErrorToast?: boolean;
  /** Clear error before executing */
  clearErrorBefore?: boolean;
}

export function useAsyncAction(defaultOptions: AsyncActionOptions = {}) {
  const loading = ref(false);
  const error = ref("");

  async function execute<T>(
    fn: () => Promise<T>,
    options: AsyncActionOptions = {}
  ): Promise<T | null> {
    const opts = { ...defaultOptions, ...options };
    if (opts.clearErrorBefore !== false) {
      error.value = "";
    }

    loading.value = true;
    try {
      const result = await fn();
      if (opts.successMessage) {
        showToast(opts.successMessage, "success");
      }
      return result;
    } catch (err) {
      const message = getErrorMessage(err);
      error.value = message;
      if (opts.showErrorToast !== false) {
        showToast(message, "error");
      }
      return null;
    } finally {
      loading.value = false;
    }
  }

  return {
    loading,
    error,
    execute,
  };
}
