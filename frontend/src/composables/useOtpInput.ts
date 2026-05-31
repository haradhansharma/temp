/**
 * useOtpInput — OTP digit input handling composable.
 *
 * Provides reactive OTP digit state and keyboard navigation helpers
 * for multi-digit OTP input fields. Eliminates duplicated OTP logic
 * in VerifyEmailForm and SettingsPanel.
 *
 * Usage:
 *   const { digits, otpValue, refs, handleInput, handleKeydown, handlePaste, reset, focusFirst }
 *     = useOtpInput(6);
 */

import { reactive, ref, computed, nextTick, onMounted, type Ref } from "vue";

export function useOtpInput(digitCount: number = 6) {
  const digits = reactive<string[]>(Array(digitCount).fill(""));
  const refs = ref<(HTMLInputElement | null)[]>([]);

  const otpValue = computed(() => digits.join(""));
  const isComplete = computed(() => otpValue.value.length === digitCount);

  function focusAt(index: number) {
    const el = refs.value[index];
    if (el) el.focus();
  }

  function focusFirst() {
    focusAt(0);
  }

  function handleInput(index: number, event: Event) {
    const target = event.target as HTMLInputElement;
    const value = target.value.replace(/[^0-9]/g, "");

    // Take only the last digit
    digits[index] = value.slice(-1);

    // Auto-advance to next input
    if (value && index < digitCount - 1) {
      focusAt(index + 1);
    }
  }

  function handleKeydown(index: number, event: KeyboardEvent) {
    // Backspace: clear current and go back
    if (event.key === "Backspace") {
      if (!digits[index] && index > 0) {
        digits[index - 1] = "";
        focusAt(index - 1);
      } else {
        digits[index] = "";
      }
      event.preventDefault();
    }
    // Arrow left
    if (event.key === "ArrowLeft" && index > 0) {
      focusAt(index - 1);
      event.preventDefault();
    }
    // Arrow right
    if (event.key === "ArrowRight" && index < digitCount - 1) {
      focusAt(index + 1);
      event.preventDefault();
    }
  }

  function handlePaste(event: ClipboardEvent) {
    event.preventDefault();
    const paste = event.clipboardData?.getData("text") || "";
    const pastedDigits = paste.replace(/[^0-9]/g, "").slice(0, digitCount);

    for (let i = 0; i < pastedDigits.length; i++) {
      digits[i] = pastedDigits[i];
    }

    // Focus on the next empty slot or the last filled one
    const nextEmpty = digits.findIndex((d) => !d);
    if (nextEmpty !== -1) {
      focusAt(nextEmpty);
    } else {
      focusAt(digitCount - 1);
    }
  }

  /** Simple OTP input handler for single-field OTP inputs (SettingsPanel style) */
  function handleSimpleInput(event: Event, _index: number) {
    const input = event.target as HTMLInputElement;
    const val = input.value.replace(/\D/g, "");

    if (val.length > 1) {
      // Paste support — fill all digits
      const pastedDigits = val.slice(0, digitCount).split("");
      for (let i = 0; i < digitCount; i++) {
        digits[i] = pastedDigits[i] || "";
      }
      const lastIdx = Math.min(val.length, digitCount - 1);
      const nextInput = input.parentElement?.querySelectorAll("input")[lastIdx] as HTMLInputElement;
      nextInput?.focus();
      return;
    }

    digits[_index] = val;
    if (val && _index < digitCount - 1) {
      const nextInput = input.parentElement?.querySelectorAll("input")[_index + 1] as HTMLInputElement;
      nextInput?.focus();
    }
  }

  /** Simple keydown handler for single-field OTP inputs (SettingsPanel style) */
  function handleSimpleKeydown(event: KeyboardEvent, index: number) {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      const inputs = (event.target as HTMLInputElement).parentElement?.querySelectorAll("input");
      (inputs?.[index - 1] as HTMLInputElement)?.focus();
    }
  }

  function reset() {
    for (let i = 0; i < digitCount; i++) {
      digits[i] = "";
    }
  }

  return {
    digits,
    otpValue,
    isComplete,
    refs,
    digitCount,
    handleInput,
    handleKeydown,
    handlePaste,
    handleSimpleInput,
    handleSimpleKeydown,
    reset,
    focusFirst,
    focusAt,
  };
}
