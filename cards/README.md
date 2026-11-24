# {BRAND} — personal greeting cards to print at home

Privacy-first MVP. Bilingual: American English (`/en`) and European Portuguese (`/pt`).

```bash
pnpm install
pnpm dev        # http://localhost:3000 → redirects to /en or /pt
pnpm check      # lint, format, typecheck, unit + pdf tests
pnpm test:e2e   # Playwright
```

Copy `.env.example` to `.env.local` when later milestones need keys. Never commit secrets.

Docs: [Architecture](docs/ARCHITECTURE.md) · [Privacy](docs/PRIVACY.md) ·
[Printing](docs/PRINTING.md) · [Decisions](docs/DECISIONS.md)
