import { describe, expect, it } from "vitest";
import { BRAND } from "@/config/brand";
import { CARD_LOCALES, DEFAULT_CARD_LOCALE, UI_LOCALES, UI_LOCALE_TAG } from "@/config/locales";
import { getOccasion, OCCASION_IDS, OCCASIONS, TONES } from "@/config/occasions";
import { ACTIVE_CURRENCIES, PRODUCTS } from "@/config/prices";

describe("locales", () => {
  it("maps UI locales to en-US and pt-PT (never pt-BR)", () => {
    expect(UI_LOCALE_TAG).toEqual({ en: "en-US", pt: "pt-PT" });
    expect(CARD_LOCALES).not.toContain("pt-BR");
  });

  it("defaults the card language to the UI language variety", () => {
    for (const locale of UI_LOCALES)
      expect(DEFAULT_CARD_LOCALE[locale]).toBe(UI_LOCALE_TAG[locale]);
  });
});

describe("brand", () => {
  it("is defined in one place", () => {
    expect(BRAND.name.length).toBeGreaterThan(0);
    expect(BRAND.url).toMatch(/^https:\/\//);
  });
});

describe("occasions", () => {
  it("lists every occasion exactly once", () => {
    expect(OCCASIONS.map((o) => o.id)).toEqual([...OCCASION_IDS]);
    expect(new Set(OCCASION_IDS).size).toBe(OCCASION_IDS.length);
  });

  it("restricts condolence tones to sober, affectionate, hopeful, religious, formal", () => {
    expect([...getOccasion("condolence").allowedTones].sort()).toEqual([
      "affectionate",
      "formal",
      "hopeful",
      "religious",
      "sober",
    ]);
  });

  it("allows all tones for other occasions", () => {
    expect(getOccasion("birthday").allowedTones).toEqual(TONES);
  });

  it("features locale-specific occasions in the right market", () => {
    expect(getOccasion("thanksgiving").featuredIn).toEqual(["en"]);
    expect(getOccasion("baptism").featuredIn).toEqual(["pt"]);
    expect(getOccasion("first-communion").featuredIn).toEqual(["pt"]);
  });
});

describe("prices (placeholders)", () => {
  it("sells 1, 5 and 12 credits", () => {
    expect(PRODUCTS.map((p) => p.credits)).toEqual([1, 5, 12]);
  });

  it("prices every product in every active currency as positive integer cents", () => {
    for (const product of PRODUCTS) {
      for (const currency of ACTIVE_CURRENCIES) {
        const amount = product.prices[currency];
        expect(Number.isInteger(amount) && (amount ?? 0) > 0, `${product.id}/${currency}`).toBe(
          true,
        );
      }
    }
  });
});
