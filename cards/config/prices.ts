/**
 * PLACEHOLDER prices, to be confirmed before M5. Amounts in minor units
 * (cents). EUR prices are tax-inclusive. USD tax treatment and fixed prices vs
 * Stripe Adaptive Pricing are open decisions (see docs/DECISIONS.md).
 */
export const CURRENCIES = ["EUR", "USD", "GBP"] as const;
export type Currency = (typeof CURRENCIES)[number];

/** Currencies with prices configured for the MVP. GBP is ready but unpriced. */
export const ACTIVE_CURRENCIES = ["EUR", "USD"] as const satisfies readonly Currency[];

export const PRODUCT_IDS = ["single", "pack5", "pack12"] as const;
export type ProductId = (typeof PRODUCT_IDS)[number];

export interface Product {
  id: ProductId;
  credits: number;
  prices: Partial<Record<Currency, number>>;
}

export const PRODUCTS: readonly Product[] = [
  { id: "single", credits: 1, prices: { EUR: 150, USD: 199 } },
  { id: "pack5", credits: 5, prices: { EUR: 499, USD: 599 } },
  { id: "pack12", credits: 12, prices: { EUR: 999, USD: 1199 } },
];

export const TAX_INCLUSIVE: Record<(typeof ACTIVE_CURRENCIES)[number], boolean | "TBD"> = {
  EUR: true,
  USD: "TBD",
};
