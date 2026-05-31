/**
 * Toast notification system — lightweight, no-dependency implementation.
 *
 * Creates and manages toast notifications in the DOM.
 *
 * Usage in Vue components:
 *   import { showToast } from "@/lib/toast";
 *   showToast("Profile updated!", "success");
 *   showToast("Something went wrong.", "error");
 */

export type ToastType = "success" | "error" | "info" | "warning";

interface ToastOptions {
  type?: ToastType;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

const TOAST_CONTAINER_ID = "toast-container";
const DEFAULT_DURATION = 4000;

// ─── Styling maps ───────────────────────────────────────────────────────────

const TOAST_STYLES: Record<ToastType, { bg: string; border: string; text: string; icon: string }> = {
  success: {
    bg: "bg-brand-50 dark:bg-brand-950/80",
    border: "border-brand-200 dark:border-brand-800",
    text: "text-brand-700 dark:text-brand-300",
    icon: `<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>`,
  },
  error: {
    bg: "bg-red-50 dark:bg-red-950/80",
    border: "border-red-200 dark:border-red-800",
    text: "text-red-700 dark:text-red-300",
    icon: `<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>`,
  },
  warning: {
    bg: "bg-yellow-50 dark:bg-yellow-950/80",
    border: "border-yellow-200 dark:border-yellow-800",
    text: "text-yellow-700 dark:text-yellow-300",
    icon: `<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>`,
  },
  info: {
    bg: "bg-sky-50 dark:bg-sky-950/80",
    border: "border-sky-200 dark:border-sky-800",
    text: "text-sky-700 dark:text-sky-300",
    icon: `<svg class="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>`,
  },
};

// ─── Container management ───────────────────────────────────────────────────

function getContainer(): HTMLElement {
  let container = document.getElementById(TOAST_CONTAINER_ID);
  if (!container) {
    container = document.createElement("div");
    container.id = TOAST_CONTAINER_ID;
    container.className =
      "fixed top-20 right-4 flex flex-col gap-2 pointer-events-none";
    // Force z-index via inline style to guarantee above navbar/sidebar/overlays
    container.style.zIndex = "2147483647";
    container.setAttribute("aria-live", "polite");
    container.setAttribute("aria-label", "Notifications");
    // Append to documentElement (not body) to avoid stacking context issues
    document.documentElement.appendChild(container);
  }
  return container;
}

// ─── Toast creation ─────────────────────────────────────────────────────────

function createToastElement(
  message: string,
  type: ToastType,
  options?: ToastOptions,
): HTMLElement {
  const styles = TOAST_STYLES[type];

  const toast = document.createElement("div");
  toast.className = [
    "toast-enter pointer-events-auto flex items-center gap-3 rounded-lg border px-4 py-3 shadow-lg backdrop-blur-sm",
    "max-w-sm w-full",
    styles.bg,
    styles.border,
  ].join(" ");

  // Icon + message
  const content = document.createElement("div");
  content.className = ["flex items-center gap-2 flex-1 min-w-0", styles.text].join(" ");
  content.innerHTML = `${styles.icon}<span class="text-sm font-medium">${escapeHtml(message)}</span>`;

  toast.appendChild(content);

  // Dismiss button
  const dismissBtn = document.createElement("button");
  dismissBtn.type = "button";
  dismissBtn.className = [
    "shrink-0 inline-flex items-center justify-center rounded-md p-1",
    "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-accent)]",
    "transition-colors",
  ].join(" ");
  dismissBtn.setAttribute("aria-label", "Dismiss");
  dismissBtn.innerHTML = `<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>`;
  dismissBtn.addEventListener("click", () => dismissToast(toast));
  toast.appendChild(dismissBtn);

  // Action button (optional)
  if (options?.action) {
    const actionBtn = document.createElement("button");
    actionBtn.type = "button";
    actionBtn.className = [
      "shrink-0 text-xs font-semibold underline underline-offset-2 hover:no-underline",
      styles.text,
      "transition-opacity hover:opacity-80",
    ].join(" ");
    actionBtn.textContent = options.action.label;
    actionBtn.addEventListener("click", () => {
      options.action!.onClick();
      dismissToast(toast);
    });
    toast.appendChild(actionBtn);
  }

  return toast;
}

// ─── Dismiss animation ──────────────────────────────────────────────────────

function dismissToast(toast: HTMLElement): void {
  toast.style.transition = "opacity 0.2s ease, transform 0.2s ease";
  toast.style.opacity = "0";
  toast.style.transform = "translateX(1rem)";
  setTimeout(() => {
    toast.remove();
    // Remove container if empty
    const container = document.getElementById(TOAST_CONTAINER_ID);
    if (container?.children.length === 0) {
      container.remove();
    }
  }, 200);
}

// ─── HTML escape ────────────────────────────────────────────────────────────

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return text.replace(/[&<>"']/g, (char) => map[char] || char);
}

// ─── Public API ─────────────────────────────────────────────────────────────

/**
 * Show a toast notification.
 *
 * @param message - The message to display
 * @param type - Toast type: "success" | "error" | "info" | "warning"
 * @param options - Optional: duration (ms) and action button
 */
export function showToast(
  message: string,
  type: ToastType = "info",
  options?: ToastOptions,
): void {
  if (typeof document === "undefined") return;

  const container = getContainer();
  const toast = createToastElement(message, type, options);
  container.appendChild(toast);

  // Auto-dismiss
  const duration = options?.duration ?? DEFAULT_DURATION;
  if (duration > 0) {
    setTimeout(() => {
      if (toast.parentNode) {
        dismissToast(toast);
      }
    }, duration);
  }
}

/**
 * Initialize the toast container on page load.
 * Call this once in your root layout or app initialization.
 */
export function initToasts(): void {
  if (typeof document === "undefined") return;
  getContainer(); // Pre-create container
}
