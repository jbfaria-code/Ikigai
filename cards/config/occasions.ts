import type { UiLocale } from "./locales";

export const TONES = [
  "funny",
  "affectionate",
  "hopeful",
  "formal",
  "nostalgic",
  "poetic",
  "religious",
  "sober",
] as const;
export type Tone = (typeof TONES)[number];

export const OCCASION_IDS = [
  // Shared
  "birthday",
  "wedding",
  "anniversary",
  "new-baby",
  "condolence",
  "retirement",
  "graduation",
  "christmas",
  "happy-holidays",
  "mothers-day",
  "fathers-day",
  "valentines-day",
  "thank-you",
  "get-well",
  // Locale-featured (available in both languages)
  "thanksgiving",
  "baby-shower",
  "bridal-shower",
  "baptism",
  "first-communion",
] as const;
export type OccasionId = (typeof OCCASION_IDS)[number];

export interface OccasionConfig {
  id: OccasionId;
  /** UI locales where the occasion is highlighted. Empty = shared, no highlight. */
  featuredIn: readonly UiLocale[];
  /** Tones the user may pick. */
  allowedTones: readonly Tone[];
}

const CONDOLENCE_TONES = ["sober", "affectionate", "hopeful", "religious", "formal"] as const;

const featured: Partial<Record<OccasionId, readonly UiLocale[]>> = {
  thanksgiving: ["en"],
  "baby-shower": ["en"],
  "bridal-shower": ["en"],
  baptism: ["pt"],
  "first-communion": ["pt"],
};

export const OCCASIONS: readonly OccasionConfig[] = OCCASION_IDS.map((id) => ({
  id,
  featuredIn: featured[id] ?? [],
  allowedTones: id === "condolence" ? CONDOLENCE_TONES : TONES,
}));

export function getOccasion(id: OccasionId): OccasionConfig {
  const occasion = OCCASIONS.find((o) => o.id === id);
  if (!occasion) throw new Error(`Unknown occasion: ${id}`);
  return occasion;
}
