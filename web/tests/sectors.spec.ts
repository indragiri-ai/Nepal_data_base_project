import { expect, test } from "@playwright/test";

import type { IndicatorSummary } from "../lib/api";
import {
  ECONOMY_THEMES,
  OTHER_THEME,
  groupByTheme,
} from "../lib/sectors";

function indicator(code: string, name: string): IndicatorSummary {
  return { code, name, topic: "economy", unit: "" };
}

test("all 647 economy indicators make one complete round trip through the shelves", () => {
  const indicators = Array.from({ length: 647 }, (_, index) =>
    indicator(`ECONOMY_${index}`, `Unclassified economy measure ${index}`),
  );
  indicators[0] = indicator(
    "CPIA_RATING",
    "CPIA economic management cluster average (1=low to 6=high)",
  );
  indicators[1] = indicator("TRADE_GDP", "Trade in services (% of GDP)");
  indicators[2] = indicator(
    "ADJUSTED_SAVINGS",
    "Adjusted savings: education expenditure (% of GNI)",
  );

  const groups = groupByTheme(ECONOMY_THEMES, indicators);
  const shelved = groups.flatMap((group) => group.rows);
  const frequencies = new Map<string, number>();
  for (const row of shelved) {
    frequencies.set(row.code, (frequencies.get(row.code) ?? 0) + 1);
  }

  expect(shelved).toHaveLength(647);
  expect(frequencies.size).toBe(647);
  expect([...frequencies.values()]).toEqual(Array(647).fill(1));
  expect(new Set(shelved.map((row) => row.code))).toEqual(
    new Set(indicators.map((row) => row.code)),
  );
  expect(groups.at(-1)?.label).toBe(OTHER_THEME);
  expect(groups.at(-1)?.rows).toHaveLength(644);
});

test("known matching traps remain fixed", () => {
  const groups = groupByTheme(ECONOMY_THEMES, [
    indicator("CPIA_RATING", "CPIA economic management cluster average (1=low to 6=high)"),
    indicator("TRADE_GDP", "Trade in services (% of GDP)"),
  ]);
  const shelfFor = (code: string) =>
    groups.find((group) => group.rows.some((row) => row.code === code))?.label;

  expect(shelfFor("CPIA_RATING")).toBe("Policy & institutions");
  expect(shelfFor("CPIA_RATING")).not.toBe("Prices & inflation");
  expect(shelfFor("TRADE_GDP")).toBe("Trade");
  expect(shelfFor("TRADE_GDP")).not.toBe("Growth & national accounts");
});

test("the founder-facing shelf names remain unchanged", () => {
  expect(ECONOMY_THEMES.map((theme) => theme.label)).toEqual(expect.arrayContaining([
    "Prices & inflation",
    "Government finance",
    "Trade",
    "External & remittances",
    "Money, credit & interest",
    "Poverty & inequality",
    "Business & investment",
    "Growth & national accounts",
  ]));
  expect(ECONOMY_THEMES.at(-1)?.label).toBe("Growth & national accounts");
});

test("new shelves use only phrases visible in indicator names", () => {
  const cases = [
    ["TOURISM", "International tourism, number of arrivals", "Tourism & transport"],
    ["BROADBAND", "Fixed broadband subscriptions", "Digital connectivity"],
    ["PATENTS", "Patent applications, residents", "Research & innovation"],
    ["CPIA", "CPIA social protection rating", "Policy & institutions"],
    ["GNI", "GNI per capita (current US$)", "Growth & national accounts"],
  ] as const;
  const groups = groupByTheme(
    ECONOMY_THEMES,
    cases.map(([code, name]) => indicator(code, name)),
  );

  for (const [code, , expectedShelf] of cases) {
    expect(groups.find((group) => group.rows.some((row) => row.code === code))?.label).toBe(
      expectedShelf,
    );
  }
  expect(groups.some((group) => group.label === OTHER_THEME)).toBe(false);
});
