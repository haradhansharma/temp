/**
 * useCooldownTimer — countdown timer composable.
 *
 * Provides a reactive cooldown timer that counts down from N seconds.
 * Used in OTP resend flows (VerifyEmailForm, ForgotPasswordForm, SettingsPanel).
 *
 * Usage:
 *   const { cooldown, isCooling, startCooldown } = useCooldownTimer(60);
 *   startCooldown(); // starts 60s countdown
 */

import { ref, onUnmounted } from "vue";

export function useCooldownTimer(defaultSeconds: number = 60) {
  const cooldown = ref(0);
  let timer: ReturnType<typeof setInterval> | null = null;

  const isCooling = ref(false);

  function startCooldown(seconds?: number) {
    const duration = seconds ?? defaultSeconds;
    cooldown.value = duration;
    isCooling.value = true;

    if (timer) clearInterval(timer);

    timer = setInterval(() => {
      cooldown.value--;
      if (cooldown.value <= 0) {
        if (timer) clearInterval(timer);
        timer = null;
        isCooling.value = false;
      }
    }, 1000);
  }

  function stopCooldown() {
    if (timer) clearInterval(timer);
    timer = null;
    cooldown.value = 0;
    isCooling.value = false;
  }

  // Auto-cleanup on component unmount to prevent memory leaks
  onUnmounted(() => {
    if (timer) clearInterval(timer);
  });

  return {
    cooldown,
    isCooling,
    startCooldown,
    stopCooldown,
  };
}
