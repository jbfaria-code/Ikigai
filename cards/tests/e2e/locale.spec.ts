import { expect, test } from "@playwright/test";

test.describe("root locale negotiation", () => {
  // Chromium derives Accept-Language from the context locale.
  for (const [browserLocale, expected] of [
    ["pt-PT", "/pt"],
    ["pt-BR", "/pt"],
    ["en-US", "/en"],
    ["en-GB", "/en"],
    ["fr-FR", "/en"],
  ] as const) {
    test(`browser locale ${browserLocale} → ${expected}`, async ({ browser }) => {
      const context = await browser.newContext({ locale: browserLocale });
      const page = await context.newPage();
      await page.goto("/");
      await expect(page).toHaveURL(new RegExp(`${expected}$`));
      await context.close();
    });
  }

  test("redirects from the server using Accept-Language", async ({ request }) => {
    const res = await request.get("/", {
      headers: { "Accept-Language": "pt-PT,pt;q=0.9" },
      maxRedirects: 0,
    });
    expect(res.status()).toBe(307);
    expect(res.headers()["location"]).toMatch(/\/pt$/);
    expect(res.headers()["set-cookie"]).toBeUndefined();
  });

  test("sets no cookies", async ({ page, context }) => {
    await page.goto("/");
    expect(await context.cookies()).toEqual([]);
  });
});

test.describe("localized pages", () => {
  test("en: American English landing with lang=en-US", async ({ page }) => {
    await page.goto("/en");
    await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
    await expect(page.getByRole("link", { name: "Create a card" })).toBeVisible();
  });

  test("pt: European Portuguese landing with lang=pt-PT", async ({ page }) => {
    await page.goto("/pt");
    await expect(page.locator("html")).toHaveAttribute("lang", "pt-PT");
    await expect(page.getByRole("link", { name: "Criar um postal" })).toBeVisible();
  });

  test("language switcher and CTA keep the locale", async ({ page }) => {
    await page.goto("/en");
    await page.getByRole("link", { name: "Português" }).click();
    await expect(page).toHaveURL(/\/pt$/);
    await page.getByRole("link", { name: "Criar um postal" }).click();
    await expect(page).toHaveURL(/\/pt\/create$/);
    await expect(page.getByRole("heading", { name: "Criar um postal" })).toBeVisible();
  });
});
