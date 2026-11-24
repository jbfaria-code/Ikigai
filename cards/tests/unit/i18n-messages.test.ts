import { describe, expect, it } from "vitest";
import { UI_LOCALES, UI_LOCALE_TAG } from "@/config/locales";
import { findDenylisted } from "@/lib/locale/denylist";
import en from "@/messages/en.json";
import pt from "@/messages/pt.json";

type Tree = { [key: string]: string | Tree };

function flatten(tree: Tree, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out.set(path, value);
    else for (const [k, v] of flatten(value, path)) out.set(k, v);
  }
  return out;
}

const catalogs: Record<(typeof UI_LOCALES)[number], Map<string, string>> = {
  en: flatten(en),
  pt: flatten(pt),
};

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)/g)].map((m) => m[1]).sort();

describe("message catalogs", () => {
  it("has a catalog for every UI locale", () => {
    expect(Object.keys(catalogs).sort()).toEqual([...UI_LOCALES].sort());
  });

  for (const locale of UI_LOCALES) {
    it(`${locale}: has exactly the same keys as en`, () => {
      expect([...catalogs[locale].keys()].sort()).toEqual([...catalogs.en.keys()].sort());
    });

    it(`${locale}: has no empty strings`, () => {
      const empty = [...catalogs[locale]].filter(([, v]) => v.trim() === "").map(([k]) => k);
      expect(empty).toEqual([]);
    });

    it(`${locale}: uses the same ICU placeholders as en`, () => {
      for (const [key, value] of catalogs.en) {
        expect(placeholders(catalogs[locale].get(key) ?? ""), key).toEqual(placeholders(value));
      }
    });

    it(`${locale}: contains no denylisted terms for ${UI_LOCALE_TAG[locale]}`, () => {
      const hits = [...catalogs[locale]]
        .map(([key, value]) => ({ key, terms: findDenylisted(value, UI_LOCALE_TAG[locale]) }))
        .filter((h) => h.terms.length > 0);
      expect(hits).toEqual([]);
    });
  }
});
