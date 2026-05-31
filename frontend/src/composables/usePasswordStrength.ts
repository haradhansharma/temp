/**
 * usePasswordStrength — password validation composable.
 *
 * Provides reactive password strength checks, strength level, and
 * validation helpers. Eliminates identical duplication across
 * RegisterForm, ForgotPasswordForm, and ResetPasswordForm.
 *
 * Usage:
 *   const { passwordChecks, passwordStrength, strengthSegments } = usePasswordStrength(passwordRef);
 */

import { computed, type Ref } from "vue";

export interface PasswordChecks {
  length: boolean;
  uppercase: boolean;
  lowercase: boolean;
  number: boolean;
  special: boolean;
}

export interface PasswordStrengthResult {
  level: number; // 0 = empty, 1 = weak, 2 = fair, 3 = good, 4 = strong
  label: string; // "", "Weak", "Fair", "Good", "Strong"
  color: string; // "", "bg-red-500", "bg-yellow-500", "bg-brand-400", "bg-brand-600"
  textClass: string; // "", "text-red-500", "text-yellow-500", "text-brand-400", "text-brand-600"
}

export function usePasswordStrength(password: Ref<string>) {
  const SPECIAL_CHARS = /[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`;\']/;

  const passwordChecks = computed<PasswordChecks>(() => {
    const pw = password.value;
    return {
      length: pw.length >= 8,
      uppercase: /[A-Z]/.test(pw),
      lowercase: /[a-z]/.test(pw),
      number: /[0-9]/.test(pw),
      special: SPECIAL_CHARS.test(pw),
    };
  });

  const passwordStrength = computed<PasswordStrengthResult>(() => {
    const checks = Object.values(passwordChecks.value);
    const passed = checks.filter(Boolean).length;

    if (password.value.length === 0) {
      return { level: 0, label: "", color: "", textClass: "" };
    }
    if (passed <= 2) {
      return { level: 1, label: "Weak", color: "bg-red-500", textClass: "text-red-500" };
    }
    if (passed <= 3) {
      return { level: 2, label: "Fair", color: "bg-yellow-500", textClass: "text-yellow-500" };
    }
    if (passed <= 4) {
      return { level: 3, label: "Good", color: "bg-brand-400", textClass: "text-brand-400" };
    }
    return { level: 4, label: "Strong", color: "bg-brand-600", textClass: "text-brand-600" };
  });

  /** All checks passed — password meets all requirements */
  const isValid = computed(() => {
    return Object.values(passwordChecks.value).every(Boolean);
  });

  /** Segment indices for the strength bar [0, 1, 2, 3] */
  const strengthSegments = [0, 1, 2, 3];

  return {
    passwordChecks,
    passwordStrength,
    isValid,
    strengthSegments,
  };
}
