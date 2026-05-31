<template>
  <div class="space-y-6">
    <!-- ═══ Page Header ═══ -->
    <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-foreground">API Keys</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Manage service credentials for sister domain authentication.
        </p>
      </div>
      <button
        type="button"
        class="btn-primary inline-flex items-center gap-2 self-start"
        :disabled="actionLoading !== null"
        @click="openCreateModal"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        Create Key
      </button>
    </div>

    <!-- ═══ Filters ═══ -->
    <div class="card flex flex-wrap items-center gap-3 p-4">
      <!-- Search by domain -->
      <div class="relative flex-1 min-w-[200px]">
        <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Filter by domain..."
          class="input-field pl-9"
        />
      </div>

      <!-- Status filter -->
      <div class="flex items-center gap-1 rounded-lg border border-border bg-background p-1">
        <button
          v-for="option in statusOptions"
          :key="option.value"
          type="button"
          class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
          :class="statusFilter === option.value
            ? 'bg-brand-100 text-brand-700 dark:bg-brand-900/50 dark:text-brand-300'
            : 'text-muted-foreground hover:text-foreground hover:bg-accent'"
          @click="statusFilter = option.value"
        >
          {{ option.label }}
        </button>
      </div>

      <!-- Results count -->
      <span class="text-xs text-muted-foreground">
        {{ meta.total_items }} key{{ meta.total_items !== 1 ? 's' : '' }}
      </span>
    </div>

    <!-- ═══ Loading Skeleton ═══ -->
    <div v-if="loading && apiKeys.length === 0" class="space-y-3">
      <div v-for="i in 3" :key="i" class="card animate-pulse p-4">
        <div class="flex items-center gap-4">
          <div class="h-10 w-10 rounded-lg bg-muted"></div>
          <div class="flex-1 space-y-2">
            <div class="h-4 w-1/3 rounded bg-muted"></div>
            <div class="h-3 w-1/4 rounded bg-muted"></div>
          </div>
          <div class="h-8 w-20 rounded-lg bg-muted"></div>
        </div>
      </div>
    </div>

    <!-- ═══ Error State ═══ -->
    <div v-else-if="loadError" class="card flex flex-col items-center gap-4 p-10 text-center">
      <svg class="h-12 w-12 text-destructive/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <div>
        <p class="font-medium text-foreground">Failed to load API keys</p>
        <p class="mt-1 text-sm text-muted-foreground">{{ loadError }}</p>
      </div>
      <button type="button" class="btn-secondary" @click="fetchKeys">Try again</button>
    </div>

    <!-- ═══ Empty State ═══ -->
    <div v-else-if="apiKeys.length === 0" class="card flex flex-col items-center gap-4 p-10 text-center">
      <svg class="h-12 w-12 text-muted-foreground/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
      </svg>
      <div>
        <p class="font-medium text-foreground">No API keys yet</p>
        <p class="mt-1 text-sm text-muted-foreground">
          {{ statusFilter !== null ? 'No keys match the current filter.' : 'Create your first service credential to get started.' }}
        </p>
      </div>
      <button
        v-if="statusFilter === null"
        type="button"
        class="btn-primary"
        @click="openCreateModal"
      >
        Create API Key
      </button>
    </div>

    <!-- ═══ Keys Table ═══ -->
    <div v-else class="space-y-3">
      <TransitionGroup name="list" tag="div" class="space-y-3">
        <div
          v-for="key in apiKeys"
          :key="key.id"
          class="card group relative overflow-hidden p-4 transition-shadow hover:shadow-md"
        >
          <!-- Active status indicator strip -->
          <div
            class="absolute left-0 top-0 bottom-0 w-1"
            :class="key.is_active ? 'bg-brand-500' : 'bg-muted-foreground/30'"
          />

          <div class="flex items-start gap-4 pl-3">
            <!-- Key icon -->
            <div
              class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors"
              :class="key.is_active
                ? 'bg-brand-50 text-brand-600 dark:bg-brand-950/50 dark:text-brand-400'
                : 'bg-muted text-muted-foreground'"
            >
              <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
            </div>

            <!-- Key info -->
            <div class="flex-1 min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="font-semibold text-foreground truncate">{{ key.name }}</h3>
                <span
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                  :class="key.is_active
                    ? 'bg-brand-100 text-brand-700 dark:bg-brand-950 dark:text-brand-400'
                    : 'bg-muted text-muted-foreground'"
                >
                  {{ key.is_active ? 'Active' : 'Revoked' }}
                </span>
              </div>

              <div class="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span class="inline-flex items-center gap-1">
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                  </svg>
                  {{ key.service_domain }}
                </span>
                <span class="inline-flex items-center gap-1 font-mono text-[11px]">
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" />
                  </svg>
                  {{ key.api_key_prefix }}...
                </span>
                <span class="inline-flex items-center gap-1">
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Last used: {{ formatDateTime(key.last_used_at) }}
                </span>
                <span class="inline-flex items-center gap-1">
                  <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  {{ key.created_by || 'Unknown' }}
                </span>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex shrink-0 items-center gap-2">
              <button
                v-if="key.is_active"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400 dark:hover:bg-amber-950/50"
                :disabled="actionLoading === `revoke-${key.id}`"
                @click="handleRevoke(key)"
              >
                <svg v-if="actionLoading === `revoke-${key.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                </svg>
                Revoke
              </button>

              <button
                v-if="key.is_active"
                type="button"
                class="inline-flex items-center gap-1.5 rounded-lg border border-brand-200 bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 transition-colors hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-400 dark:hover:bg-brand-950/50"
                :disabled="actionLoading === `rotate-${key.id}`"
                @click="handleRotate(key)"
              >
                <svg v-if="actionLoading === `rotate-${key.id}`" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Rotate
              </button>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- ═══ Pagination ═══ -->
      <div v-if="meta.total_pages > 1" class="flex items-center justify-between pt-2">
        <p class="text-xs text-muted-foreground">
          Page {{ meta.current_page }} of {{ meta.total_pages }}
        </p>
        <div class="flex items-center gap-1">
          <button
            type="button"
            class="btn-ghost px-3 py-1.5 text-xs"
            :disabled="!meta.has_previous || loading"
            @click="goToPage(meta.current_page - 1)"
          >
            Previous
          </button>
          <button
            type="button"
            class="btn-ghost px-3 py-1.5 text-xs"
            :disabled="!meta.has_next || loading"
            @click="goToPage(meta.current_page + 1)"
          >
            Next
          </button>
        </div>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════════
         CREATE MODAL
         ═══════════════════════════════════════════════════════════ -->
    <Teleport to="body">
      <div
        v-if="showCreateModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Create API Key"
      >
        <!-- Backdrop -->
        <div
          class="fixed inset-0 bg-black/60 backdrop-blur-sm"
          @click="closeCreateModal"
        />

        <!-- Panel -->
        <div class="relative z-10 w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl">
          <!-- Header -->
          <div class="flex items-center justify-between mb-6">
            <div>
              <h2 class="text-lg font-bold text-foreground">Create API Key</h2>
              <p class="mt-1 text-sm text-muted-foreground">
                Generate a new service credential.
              </p>
            </div>
            <button
              type="button"
              class="inline-flex items-center justify-center rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
              @click="closeCreateModal"
              aria-label="Close"
            >
              <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Create form -->
          <form v-if="!createResult" @submit.prevent="handleCreate" class="space-y-4">
            <!-- Name -->
            <div>
              <label for="key-name" class="mb-1.5 block text-sm font-medium text-foreground">
                Credential Name
              </label>
              <input
                id="key-name"
                v-model="createForm.name"
                type="text"
                placeholder="e.g. Finance App Production"
                class="input-field"
                required
                maxlength="100"
                autocomplete="off"
              />
              <p class="mt-1 text-xs text-muted-foreground">
                A label to identify this credential in the admin panel.
              </p>
            </div>

            <!-- Service Domain -->
            <div>
              <label for="key-domain" class="mb-1.5 block text-sm font-medium text-foreground">
                Service Domain
              </label>
              <select
                id="key-domain"
                v-model.number="createForm.service_domain_id"
                class="input-field"
                required
              >
                <option :value="null" disabled>Select a domain...</option>
                <option
                  v-for="domain in serviceDomains"
                  :key="domain.id"
                  :value="domain.id"
                  :disabled="!domain.is_active"
                >
                  {{ domain.domain }}
                  {{ !domain.is_active ? ' (inactive)' : ` — ${domain.product_name}` }}
                </option>
              </select>
              <p class="mt-1 text-xs text-muted-foreground">
                The sister domain this credential will authenticate.
              </p>
            </div>

            <!-- Error -->
            <div v-if="createError" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
              {{ createError }}
            </div>

            <!-- Submit -->
            <div class="flex items-center justify-end gap-3 pt-2">
              <button type="button" class="btn-ghost" @click="closeCreateModal">
                Cancel
              </button>
              <button
                type="submit"
                class="btn-primary inline-flex items-center gap-2"
                :disabled="actionLoading === 'create' || !createForm.name || !createForm.service_domain_id"
              >
                <svg v-if="actionLoading === 'create'" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                </svg>
                Create Key
              </button>
            </div>
          </form>

          <!-- Success: Show raw key -->
          <div v-else class="space-y-4">
            <div class="rounded-lg border border-brand-200 bg-brand-50 p-4 dark:border-brand-800 dark:bg-brand-950/30">
              <div class="flex items-start gap-3">
                <svg class="h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
                <div class="flex-1 min-w-0">
                  <p class="font-semibold text-brand-800 dark:text-brand-300">API Key Created</p>
                  <p class="mt-1 text-sm text-brand-700 dark:text-brand-400">
                    Save this key now. It cannot be recovered after closing this dialog.
                  </p>
                </div>
              </div>
            </div>

            <!-- Raw key display -->
            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">Raw API Key</label>
              <div class="relative">
                <input
                  :value="createResult!.raw_api_key"
                  type="text"
                  readonly
                  class="input-field pr-10 font-mono text-sm bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-800"
                  @focus="($event.target as HTMLInputElement).select()"
                />
                <button
                  type="button"
                  class="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                  :title="copied ? 'Copied!' : 'Copy to clipboard'"
                  @click="copyToClipboard(createResult!.raw_api_key)"
                >
                  <svg v-if="copied" class="h-4 w-4 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
              </div>
            </div>

            <!-- Key details -->
            <div class="grid grid-cols-2 gap-3 text-sm">
              <div class="rounded-lg bg-muted/50 p-3">
                <p class="text-xs text-muted-foreground">Prefix</p>
                <p class="mt-0.5 font-mono text-xs font-medium">{{ createResult!.api_key_prefix }}...</p>
              </div>
              <div class="rounded-lg bg-muted/50 p-3">
                <p class="text-xs text-muted-foreground">Service Domain</p>
                <p class="mt-0.5 font-medium truncate">{{ createResult!.service_domain }}</p>
              </div>
            </div>

            <div class="flex justify-end pt-2">
              <button
                type="button"
                class="btn-primary"
                @click="closeCreateModal"
              >
                Done — I've saved the key
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════════════════════════════════════════════════════
         ROTATE CONFIRMATION MODAL
         ═══════════════════════════════════════════════════════════ -->
    <Teleport to="body">
      <div
        v-if="showRotateModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Rotate API Key"
      >
        <div class="fixed inset-0 bg-black/60 backdrop-blur-sm" @click="closeRotateModal" />
        <div class="relative z-10 w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl">
          <div v-if="!rotateResult">
            <h2 class="text-lg font-bold text-foreground">Rotate API Key</h2>
            <p class="mt-2 text-sm text-muted-foreground">
              This will immediately revoke the current key (<code class="rounded bg-muted px-1.5 py-0.5 text-xs font-mono">{{ rotatingKey?.api_key_prefix }}...</code>) and generate a new one. The old key will stop working instantly.
            </p>
            <div class="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/30">
              <p class="text-sm text-amber-800 dark:text-amber-300 font-medium">
                Make sure the new key is deployed before rotating. Any service using the old key will be rejected.
              </p>
            </div>
            <div v-if="rotateError" class="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
              {{ rotateError }}
            </div>
            <div class="mt-6 flex items-center justify-end gap-3">
              <button type="button" class="btn-ghost" @click="closeRotateModal">Cancel</button>
              <button
                type="button"
                class="btn-primary inline-flex items-center gap-2"
                :disabled="actionLoading === `rotate-${rotatingKey?.id}`"
                @click="confirmRotate"
              >
                <svg v-if="actionLoading === `rotate-${rotatingKey?.id}`" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Rotate Key
              </button>
            </div>
          </div>

          <!-- Rotate success: Show new raw key -->
          <div v-else class="space-y-4">
            <div class="rounded-lg border border-brand-200 bg-brand-50 p-4 dark:border-brand-800 dark:bg-brand-950/30">
              <div class="flex items-start gap-3">
                <svg class="h-5 w-5 shrink-0 text-brand-600 dark:text-brand-400 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                </svg>
                <div>
                  <p class="font-semibold text-brand-800 dark:text-brand-300">Key Rotated</p>
                  <p class="mt-1 text-sm text-brand-700 dark:text-brand-400">
                    Old key <code class="rounded bg-brand-100 px-1 py-0.5 text-xs font-mono dark:bg-brand-900/50">{{ rotateResult!.old_prefix }}...</code> is revoked. Save the new key now.
                  </p>
                </div>
              </div>
            </div>

            <div>
              <label class="mb-1.5 block text-sm font-medium text-foreground">New API Key</label>
              <div class="relative">
                <input
                  :value="rotateResult!.new_api_key"
                  type="text"
                  readonly
                  class="input-field pr-10 font-mono text-sm bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-800"
                  @focus="($event.target as HTMLInputElement).select()"
                />
                <button
                  type="button"
                  class="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                  :title="rotateCopied ? 'Copied!' : 'Copy to clipboard'"
                  @click="copyToClipboard(rotateResult!.new_api_key)"
                >
                  <svg v-if="rotateCopied" class="h-4 w-4 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
              </div>
            </div>

            <div class="flex justify-end pt-2">
              <button type="button" class="btn-primary" @click="closeRotateModal">
                Done — I've saved the new key
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ═══════════════════════════════════════════════════════════
         REVOKE CONFIRMATION MODAL
         ═══════════════════════════════════════════════════════════ -->
    <Teleport to="body">
      <div
        v-if="showRevokeModal"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Revoke API Key"
      >
        <div class="fixed inset-0 bg-black/60 backdrop-blur-sm" @click="closeRevokeModal" />
        <div class="relative z-10 w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl">
          <h2 class="text-lg font-bold text-foreground">Revoke API Key</h2>
          <p class="mt-2 text-sm text-muted-foreground">
            Are you sure you want to revoke <strong class="text-foreground">{{ revokingKey?.name }}</strong> (<code class="rounded bg-muted px-1.5 py-0.5 text-xs font-mono">{{ revokingKey?.api_key_prefix }}...</code>)? This action cannot be undone. The key will stop working immediately.
          </p>
          <div v-if="revokeError" class="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
            {{ revokeError }}
          </div>
          <div class="mt-6 flex items-center justify-end gap-3">
            <button type="button" class="btn-ghost" @click="closeRevokeModal">Cancel</button>
            <button
              type="button"
              class="btn-destructive inline-flex items-center gap-2"
              :disabled="actionLoading === `revoke-${revokingKey?.id}`"
              @click="confirmRevoke"
            >
              <svg v-if="actionLoading === `revoke-${revokingKey?.id}`" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Revoke Key
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import { requireAuth, getErrorMessage } from "@/lib/auth";
import { showToast } from "@/lib/toast";
import { adminApi, formatDateTime } from "@/lib/admin";
import type { ApiKeyItem, ApiKeyCreateResponse, ApiKeyRotateResponse, ServiceDomainOption } from "@/lib/admin";

// ─── State ───────────────────────────────────────────────────────────────────

const loading = ref(false);
const loadError = ref<string | null>(null);
const actionLoading = ref<string | null>(null);
const apiKeys = ref<ApiKeyItem[]>([]);
const searchQuery = ref("");
const statusFilter = ref<boolean | null>(null);
const currentPage = ref(1);

const meta = ref({
  total_items: 0,
  total_pages: 0,
  current_page: 1,
  page_size: 20,
  has_next: false,
  has_previous: false,
});

// Create modal
const showCreateModal = ref(false);
const createForm = ref({ name: "", service_domain_id: null as number | null });
const createResult = ref<ApiKeyCreateResponse | null>(null);
const createError = ref<string | null>(null);
const serviceDomains = ref<ServiceDomainOption[]>([]);
const copied = ref(false);

// Rotate modal
const showRotateModal = ref(false);
const rotatingKey = ref<ApiKeyItem | null>(null);
const rotateResult = ref<ApiKeyRotateResponse | null>(null);
const rotateError = ref<string | null>(null);
const rotateCopied = ref(false);

// Revoke modal
const showRevokeModal = ref(false);
const revokingKey = ref<ApiKeyItem | null>(null);
const revokeError = ref<string | null>(null);

const statusOptions = [
  { label: "All", value: null as boolean | null },
  { label: "Active", value: true },
  { label: "Revoked", value: false },
];

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  if (!requireAuth()) return;
  await Promise.all([fetchKeys(), fetchDomains()]);
});

// ─── Keyboard shortcuts ──────────────────────────────────────────────────────

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (showCreateModal.value) closeCreateModal();
    if (showRotateModal.value) closeRotateModal();
    if (showRevokeModal.value) closeRevokeModal();
  }
}

onMounted(() => document.addEventListener("keydown", handleKeydown));
onUnmounted(() => document.removeEventListener("keydown", handleKeydown));

// ─── Watchers ────────────────────────────────────────────────────────────────

// Re-fetch when filters change (debounced for search)
let searchTimeout: ReturnType<typeof setTimeout>;
watch([searchQuery, statusFilter], () => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    currentPage.value = 1;
    fetchKeys();
  }, 300);
});

// ─── API Calls ───────────────────────────────────────────────────────────────

async function fetchKeys() {
  loading.value = true;
  loadError.value = null;
  try {
    const params: Parameters<typeof adminApi.listApiKeys>[0] = {
      page: currentPage.value,
      page_size: 20,
    };
    if (statusFilter.value !== null) params.is_active = statusFilter.value;
    // Client-side search: we filter locally by domain after fetch
    const data = await adminApi.listApiKeys(params);
    meta.value = data.meta;

    // Apply client-side search filter on service_domain
    let results = data.results;
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.trim().toLowerCase();
      results = results.filter(
        (k) =>
          k.service_domain.toLowerCase().includes(q) ||
          k.name.toLowerCase().includes(q) ||
          k.api_key_prefix.toLowerCase().includes(q)
      );
    }
    apiKeys.value = results;
  } catch (err) {
    loadError.value = getErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

async function fetchDomains() {
  try {
    serviceDomains.value = await adminApi.fetchServiceDomains();
  } catch {
    // Non-critical — domains can be typed manually
    serviceDomains.value = [];
  }
}

function goToPage(page: number) {
  currentPage.value = page;
  fetchKeys();
  nextTick(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

// ─── Create ──────────────────────────────────────────────────────────────────

function openCreateModal() {
  createForm.value = { name: "", service_domain_id: null };
  createResult.value = null;
  createError.value = null;
  copied.value = false;
  showCreateModal.value = true;
}

function closeCreateModal() {
  showCreateModal.value = false;
  if (createResult.value) {
    createResult.value = null;
    fetchKeys(); // Refresh the list
  }
}

async function handleCreate() {
  if (!createForm.value.name || !createForm.value.service_domain_id) return;
  actionLoading.value = "create";
  createError.value = null;
  try {
    createResult.value = await adminApi.createApiKey({
      name: createForm.value.name,
      service_domain_id: createForm.value.service_domain_id,
    });
    showToast("API key created successfully.", "success");
  } catch (err) {
    createError.value = getErrorMessage(err);
  } finally {
    actionLoading.value = null;
  }
}

// ─── Revoke ──────────────────────────────────────────────────────────────────

function handleRevoke(key: ApiKeyItem) {
  revokingKey.value = key;
  revokeError.value = null;
  showRevokeModal.value = true;
}

function closeRevokeModal() {
  showRevokeModal.value = false;
  revokingKey.value = null;
}

async function confirmRevoke() {
  if (!revokingKey.value) return;
  actionLoading.value = `revoke-${revokingKey.value.id}`;
  revokeError.value = null;
  try {
    await adminApi.revokeApiKey(revokingKey.value.id);
    showToast(`API key '${revokingKey.value.api_key_prefix}...' revoked.`, "success");
    closeRevokeModal();
    fetchKeys();
  } catch (err) {
    revokeError.value = getErrorMessage(err);
  } finally {
    actionLoading.value = null;
  }
}

// ─── Rotate ──────────────────────────────────────────────────────────────────

function handleRotate(key: ApiKeyItem) {
  rotatingKey.value = key;
  rotateResult.value = null;
  rotateError.value = null;
  rotateCopied.value = false;
  showRotateModal.value = true;
}

function closeRotateModal() {
  showRotateModal.value = false;
  if (rotateResult.value) {
    rotateResult.value = null;
    fetchKeys(); // Refresh the list
  }
}

async function confirmRotate() {
  if (!rotatingKey.value) return;
  actionLoading.value = `rotate-${rotatingKey.value.id}`;
  rotateError.value = null;
  try {
    rotateResult.value = await adminApi.rotateApiKey(rotatingKey.value.id);
    showToast("API key rotated successfully.", "success");
  } catch (err) {
    rotateError.value = getErrorMessage(err);
  } finally {
    actionLoading.value = null;
  }
}

// ─── Clipboard ───────────────────────────────────────────────────────────────

async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    copied.value = text === (createResult.value?.raw_api_key ?? "");
    rotateCopied.value = text === (rotateResult.value?.new_api_key ?? "");
    showToast("Copied to clipboard.", "info", { duration: 2000 });
    setTimeout(() => {
      copied.value = false;
      rotateCopied.value = false;
    }, 3000);
  } catch {
    // Fallback for older browsers
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    showToast("Copied to clipboard.", "info", { duration: 2000 });
  }
}
</script>

<style scoped>
  /* List transition */
  .list-enter-active,
  .list-leave-active {
    transition: all 0.3s ease;
  }
  .list-enter-from {
    opacity: 0;
    transform: translateY(8px);
  }
  .list-leave-to {
    opacity: 0;
    transform: translateX(-8px);
  }
</style>
