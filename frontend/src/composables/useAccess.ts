/**
 * useAccess — reactive feature-access checking composable.
 *
 * Provides convenient methods to check the current user's access
 * permissions based on the access map returned by billing.auth.me().
 * Internally delegates to useAuth() for the data source.
 *
 * Usage:
 *   const { hasAccess, getAccess, accessKeys } = useAccess();
 *
 *   // Template guard
 *   if (hasAccess("reports")) { showReports(); }
 *
 *   // Typed value retrieval
 *   const maxAccounts = getAccess<number>("max_bank_accounts", 1);
 *
 *   // List all available keys
 *   console.log(accessKeys.value);  // ["dashboard", "reports", "api_access", ...]
 */

import { computed, type ComputedRef } from "vue";
import { useAuth } from "./useAuth";

export function useAccess() {
  const { access, loading, refetch: refetchAuth } = useAuth();

  /**
   * Reactive boolean — true when the given access key exists
   * and its value is truthy. Automatically recomputes when the
   * access map changes (e.g. after a plan change or billing return).
   *
   * Supports boolean, number, and string values:
   *   - boolean true  → true
   *   - number  > 0   → true
   *   - string truthy → true (everything except "", "false", "0")
   */
  function hasAccess(key: string): ComputedRef<boolean> {
    return computed(() => {
      const value = access.value[key];
      if (value === undefined || value === null) return false;
      if (typeof value === "boolean") return value;
      if (typeof value === "number") return value > 0;
      if (typeof value === "string") {
        return value !== "" && value !== "false" && value !== "0";
      }
      return Boolean(value);
    });
  }

  /**
   * Get a typed access value for a given key.
   *
   * @param key        - The access key to look up (e.g. "max_bank_accounts")
   * @param defaultValue - Returned when the key is missing (defaults to undefined)
   *
   * @example
   *   const maxAccounts = getAccess<number>("max_bank_accounts", 1);
   *   const retention  = getAccess<number>("data_retention_days", 7);
   *   const label      = getAccess<string>("plan_label", "Free");
   */
  function getAccess<T extends boolean | number | string>(
    key: string,
    defaultValue?: T,
  ): ComputedRef<T | undefined> {
    return computed(() => {
      const value = access.value[key];
      if (value === undefined || value === null) return defaultValue;
      return value as T;
    });
  }

  /** Reactive list of all available access keys. */
  const accessKeys: ComputedRef<string[]> = computed(() =>
    Object.keys(access.value),
  );

  return {
    hasAccess,
    getAccess,
    accessKeys,
    loading,
    refetch: refetchAuth,
  };
}
