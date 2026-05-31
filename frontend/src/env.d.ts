/// <reference types="astro/client" />
/// <reference types="vue/runtime-dom" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}

// Astro global types
declare namespace App {
  // Locals can be passed from server endpoints to pages via `Astro.props`
  interface Locals {
    user?: {
      id: number;
      slug: string;
      email: string;
      first_name: string;
      last_name: string;
      role: string;
    } | null;
  }
}
