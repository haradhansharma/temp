/**
 * useFormErrors — form field error management composable.
 *
 * Provides reactive field-level and general error state with
 * clear/validate helpers. Eliminates duplicated error handling
 * across all form components.
 *
 * Usage:
 *   const { fieldErrors, generalError, clearErrors, setFieldError, setGeneralError }
 *     = useFormErrors(["email", "password"]);
 */

import { reactive, ref } from "vue";

export function useFormErrors(fields: string[] = []) {
  const fieldErrors = reactive<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f, ""]))
  );
  const generalError = ref("");

  function clearErrors(): void {
    generalError.value = "";
    Object.keys(fieldErrors).forEach((key) => {
      fieldErrors[key] = "";
    });
  }

  function setFieldError(field: string, message: string): void {
    fieldErrors[field] = message;
  }

  function setGeneralError(message: string): void {
    generalError.value = message;
  }

  /**
   * Map API-level field errors to local fieldErrors.
   * Handles the Django Ninja error format.
   */
  function setApiFieldErrors(errors?: Record<string, string[]>): void {
    if (!errors) return;
    for (const [field, messages] of Object.entries(errors)) {
      if (field in fieldErrors) {
        fieldErrors[field] = messages.join(" ");
      }
    }
  }

  /** Whether there are any errors set */
  function hasErrors(): boolean {
    if (generalError.value) return true;
    return Object.values(fieldErrors).some((v) => !!v);
  }

  return {
    fieldErrors,
    generalError,
    clearErrors,
    setFieldError,
    setGeneralError,
    setApiFieldErrors,
    hasErrors,
  };
}
