-- 0007_day_periods.sql
-- Allow DAY as a period type (ODN.S2 — Kalimati daily market prices).
--
-- Every period type so far has been a year, a fiscal year, a quarter, a month
-- or a census round, because every source so far published at that grain. The
-- Kalimati series is a price per commodity per DAY across a decade, and there
-- is no honest way to store it: rolling it up to months before it is even
-- loaded would throw away the source's own resolution and make the daily
-- question ("what did tomatoes cost on this date?") unanswerable forever.
--
-- A CHECK extension only. No column is added, no row changes, nothing is
-- rewritten — an existing row cannot violate the wider constraint, so this is
-- safe to apply to a live table and trivially reversible.
--
-- Day periods are created ON DEMAND for dates the data actually contains (the
-- loader does this), never pre-seeded: the alternative is ~3,600 calendar rows
-- for a decade, most of which no source would ever reference.

ALTER TABLE time_periods DROP CONSTRAINT time_periods_type_check;

ALTER TABLE time_periods
    ADD CONSTRAINT time_periods_type_check
    CHECK (period_type IN ('year', 'fiscal_year', 'quarter', 'month', 'day', 'census_round'));
