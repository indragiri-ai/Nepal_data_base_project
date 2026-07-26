import { chromium } from "@playwright/test";

const BASE = "http://localhost:3199";
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1.5 });
const page = await ctx.newPage();

async function shot(name) {
  await page.waitForTimeout(2600);
  await page.screenshot({ path: `../Screenshots/preview-population-${name}.png`, fullPage: true });
  console.log("captured", name);
}

await page.goto(`${BASE}/population`, { waitUntil: "networkidle", timeout: 30000 });
await page.waitForSelector("canvas", { timeout: 20000 });
await shot("district");

// National municipality view
await page.getByRole("button", { name: "By municipality" }).click();
await shot("municipality");

// Drill: back to districts, open the table, click Kathmandu to drill into it
await page.getByRole("button", { name: "By district" }).click();
await page.waitForTimeout(1800);
await page.getByRole("button", { name: "View table" }).click();
await page.waitForTimeout(500);
await page.getByRole("button", { name: "Kathmandu", exact: true }).first().click();
await shot("drill");

await browser.close();
console.log("done");
