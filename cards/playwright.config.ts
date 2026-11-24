import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.PORT ?? 3100);
const baseURL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: { baseURL, trace: "off" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // CI runs against the production build; locally reuse a running dev server.
    command: process.env.CI ? `pnpm start --port ${PORT}` : `pnpm dev --port ${PORT}`,
    url: `${baseURL}/en`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
