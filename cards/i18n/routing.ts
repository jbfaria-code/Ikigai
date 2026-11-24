import { defineRouting } from "next-intl/routing";
import { DEFAULT_UI_LOCALE, UI_LOCALES } from "@/config/locales";

export const routing = defineRouting({
  locales: UI_LOCALES,
  defaultLocale: DEFAULT_UI_LOCALE,
  localePrefix: "always",
  // Privacy: no locale cookie. "/" is negotiated from Accept-Language on every
  // visit; once on /en or /pt the URL is the only state.
  localeCookie: false,
  // hreflang must be en-US / pt-PT, not en / pt; emitted via metadata in M7.
  alternateLinks: false,
});
