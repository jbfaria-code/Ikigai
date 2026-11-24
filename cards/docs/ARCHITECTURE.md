# Architecture

Status: **M0 (setup)**. Sections marked _(Mx)_ are planned, not yet built.

## Overview

A privacy-first Next.js app that builds personalized greeting cards and imposes them into
print-ready PDFs **in the browser**. The server only (a) proxies tokenized text to the AI
provider and (b) manages anonymous credit codes. No accounts, no photo uploads, no card
content stored server-side.

```
Browser (all card data, photos, PDF generation, IndexedDB 30-day expiry)
   │  tokenized text only ({{R}}, {{S}})            │  credit code only
   ▼                                                ▼
/api/generate (EU) ──► AI provider            /api/redeem, /api/checkout, /api/stripe/webhook (EU)
                                                    │
                                                    ▼
                                          Postgres (EU): credit_codes, redemptions
```

## Stack

Next.js 16 (App Router, Cache Components, `proxy.ts`), TypeScript strict
(+ `noUncheckedIndexedAccess`), Tailwind CSS 4, shadcn/ui, next-intl 4, zod, Vitest,
Playwright, ESLint + Prettier, pnpm. Later milestones add the libraries listed in the brief
(react-pdf, pdf-lib, Stripe, Drizzle, Upstash, Turnstile, Anthropic SDK, pdfjs-dist,
Zustand, idb-keyval).

## Locales

- **UI locale** = URL segment: `en` (en-US) at `/en`, `pt` (pt-PT) at `/pt`.
- **Card locale** = language variety of the card text (`en-US` | `pt-PT`), chosen
  independently of the UI locale.
- `/` is redirected by `proxy.ts` (next-intl middleware) from `Accept-Language`; fallback
  `en`. No locale cookie.
- Registry: `config/locales.ts`. Strings: `messages/{locale}.json`, type-checked against
  `en.json` (`global.d.ts`).
- Adding a locale (e.g. `pt-BR`, `es`): add to `config/locales.ts`, add a catalog and a
  denylist entry in `lib/locale/denylist.ts`. `pt-BR` must be a separate locale, never merged
  with `pt-PT`.

## Folder map

| Path                                                           | Purpose                                                   | Milestone        |
| -------------------------------------------------------------- | --------------------------------------------------------- | ---------------- |
| `app/[locale]/(marketing)`                                     | Landing                                                   | M0 (placeholder) |
| `app/[locale]/create/*`                                        | Card wizard                                               | M3               |
| `app/[locale]/{occasions,print-guide,calibrate,privacy,terms}` | Content pages                                             | M6–M7            |
| `app/api/{generate,redeem,checkout,stripe/webhook}`            | Stateless EU functions                                    | M4–M5            |
| `config/`                                                      | brand, locales, occasions, prices (placeholders)          | M0               |
| `i18n/`                                                        | next-intl routing, request config, navigation             | M0               |
| `lib/locale`                                                   | denylist (M0); paperDefault, units, occasionCalendar (M3) | M0/M3            |
| `lib/imposition`                                               | Pure imposition engine + fold simulator                   | M1               |
| `lib/pdf`                                                      | Panel rendering, assembly, watermark, metadata, fonts     | M1–M5            |
| `lib/design`                                                   | Layouts, palettes, font pairs, designer                   | M2               |
| `lib/photos`                                                   | Client-side photo pipeline                                | M3               |
| `lib/ai`                                                       | TextGenerator, adapter, tokenization, moderation          | M4               |
| `lib/payments`                                                 | Stripe, pricing, credits, unlock token                    | M5               |
| `lib/privacy`                                                  | Local storage + purge                                     | M3               |
| `messages/`                                                    | UI strings                                                | M0               |
| `prompts/`                                                     | Versioned system prompt + few-shots                       | M4               |
| `db/`                                                          | Drizzle schema + migrations                               | M5               |
| `tests/{unit,pdf,e2e,fixtures}`                                | Vitest projects `unit` and `pdf`; Playwright              | M0               |

## Commands

| Command                            | What it does                                                         |
| ---------------------------------- | -------------------------------------------------------------------- |
| `pnpm dev`                         | Dev server                                                           |
| `pnpm check`                       | lint + format check + typecheck + Vitest                             |
| `pnpm test:unit` / `pnpm test:pdf` | Vitest projects                                                      |
| `pnpm test:e2e`                    | Playwright (starts the dev server, or `pnpm start` when `CI` is set) |

CI: `.github/workflows/cards-ci.yml` (repo root), jobs `checks` and `e2e`.
