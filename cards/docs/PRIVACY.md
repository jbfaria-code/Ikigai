# Privacy

Same GDPR-level protection for every user, whatever their country. This file tracks each
hard constraint from the brief and how it is enforced.

| Constraint                                                                     | Enforcement                                                       | Status               |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------- | -------------------- |
| No cookies for locale                                                          | `localeCookie: false`; E2E asserts no cookies and no `Set-Cookie` | ✅ M0                |
| Photos never leave the browser; no upload endpoints                            | Test: no route accepts `multipart/form-data` or image data        | M3–M4                |
| Names never sent to AI (`{{R}}`, `{{S}}`), emails/phones stripped              | Client tokenization + server rejection; round-trip tests          | M4                   |
| Stateless APIs, no body logging                                                | Logger spy tests                                                  | M4                   |
| No third-party scripts except Stripe redirect and Turnstile; self-hosted fonts | CSP + review                                                      | M2 (fonts), M8 (CSP) |
| Cookieless analytics only                                                      | —                                                                 | M7                   |
| CSP, HSTS, nosniff, Referrer-Policy, Permissions-Policy                        | Header tests                                                      | M8                   |
| EU region for functions and DB                                                 | Deployment config                                                 | M8                   |
| Server DB holds only credit codes and redemptions (no content, names, IPs)     | Drizzle schema review                                             | M5                   |
| Local data: IndexedDB, 30-day expiry, "Delete everything now"                  | Unit + E2E                                                        | M3                   |
| EXIF/GPS stripped from photos                                                  | Fixture test                                                      | M3                   |

## Known accepted risk

Client-side watermark bypass by technical users is accepted for the MVP (documented in M5).
