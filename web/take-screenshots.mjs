import { chromium } from "@playwright/test";

const WIDTHS = [
  [360, 780],
  [768, 1024],
  [1440, 900],
];
const PAGES = [
  ["home", "/"],
  ["economy", "/economy"],
];
const BASE = "http://localhost:3199";

const browser = await chromium.launch();
for (const [name, path] of PAGES) {
  for (const [w, h] of WIDTHS) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: h },
      deviceScaleFactor: 1.5,
    });
    const page = await ctx.newPage();
    await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2800); // let orbit numbers + charts settle
    await page.screenshot({
      path: `../Screenshots/preview-${name}-${w}.png`,
      fullPage: true,
    });
    await ctx.close();
    console.log("captured", name, `${w}x${h}`);
  }
}
await browser.close();
console.log("done");
