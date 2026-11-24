import type { CardLocale } from "@/config/locales";

/**
 * Shared language-variety denylists. Used by the UI message tests (M0) and by
 * the AI post-generation locale check (M4). Matching is whole-word and
 * case-insensitive.
 */
export const DENYLIST: Record<CardLocale, readonly string[]> = {
  // Brazilian Portuguese markers that must never appear in pt-PT.
  "pt-PT": ["ônibus", "celular", "tela", "time", "baixar", "arquivo", "usuário", "registrar"],
  // British spellings/vocabulary that must never appear in en-US.
  "en-US": ["colour", "favourite", "personalise", "organise", "centre", "cancelled", "Mum"],
};

function wordRegex(term: string): RegExp {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?<![\\p{L}\\p{N}])${escaped}(?![\\p{L}\\p{N}])`, "iu");
}

/** Returns the denylisted terms found in `text` for the given variety. */
export function findDenylisted(text: string, locale: CardLocale): string[] {
  return DENYLIST[locale].filter((term) => wordRegex(term).test(text));
}
