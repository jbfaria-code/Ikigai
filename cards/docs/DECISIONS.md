# Decisions

Lightweight ADR log. Newest first.

## D-005 · shadcn/ui set up by hand (M0)

The shadcn CLI could not reach `ui.shadcn.com` from the build environment. `components.json`,
`lib/utils.ts` (`cn`) and `components/ui/button.tsx` were written by hand, following
shadcn conventions. Future components can be added with the CLI once the host is reachable.
**Open:** primitive library for interactive components (Radix vs Base UI), decided in M2/M3.

## D-004 · hreflang deferred to M7 (M0)

next-intl's automatic `Link` header would emit `hreflang="en"`/`"pt"`. The brief requires
`en-US`/`pt-PT`, so `alternateLinks: false`; alternates will be emitted through metadata in M7.

## D-003 · No locale cookie (M0)

`localeCookie: false`. `/` is negotiated from `Accept-Language` on every visit; the URL is the
only locale state. Consistent with "nothing kept" and avoids any cookie notice.

## D-002 · Stricter TypeScript (M0)

`strict` plus `noUncheckedIndexedAccess`, `noImplicitOverride`, `noFallthroughCasesInSwitch`.
Indexed access safety matters for the imposition tables in M1.

## D-001 · App lives in `cards/` (M0)

The repository root already contains an unrelated app (Ikigai: `server.js`, `server.py`,
`public/`). To avoid collisions (notably `public/`), the card app is a self-contained project
in `cards/`; CI runs with `working-directory: cards`.
