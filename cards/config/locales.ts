/**
 * Locale registry. Adding a locale = add it here + messages/{locale}.json.
 * UI locale (URL segment) and card locale (language variety of the card text)
 * are separate concepts: a pt UI user may write an en-US card and vice versa.
 */
export const UI_LOCALES = ["en", "pt"] as const;
export type UiLocale = (typeof UI_LOCALES)[number];

export const DEFAULT_UI_LOCALE: UiLocale = "en";

export const CARD_LOCALES = ["en-US", "pt-PT"] as const;
export type CardLocale = (typeof CARD_LOCALES)[number];

/** BCP 47 tag used for <html lang>, hreflang and Intl formatting. */
export const UI_LOCALE_TAG: Record<UiLocale, CardLocale> = {
  en: "en-US",
  pt: "pt-PT",
};

/** Default card language for a given UI language (user can change it). */
export const DEFAULT_CARD_LOCALE: Record<UiLocale, CardLocale> = UI_LOCALE_TAG;

export function isUiLocale(value: unknown): value is UiLocale {
  return typeof value === "string" && (UI_LOCALES as readonly string[]).includes(value);
}
