-- Rollback for 0007_day_periods.sql
--
-- Narrows the CHECK back to its original set. This FAILS if any day periods
-- exist, which is correct: silently deleting loaded periods (and cascading to
-- the observations that reference them) to satisfy a rollback would destroy
-- data. Remove the day rows deliberately first if that is really intended.

ALTER TABLE time_periods DROP CONSTRAINT time_periods_type_check;

ALTER TABLE time_periods
    ADD CONSTRAINT time_periods_type_check
    CHECK (period_type IN ('year', 'fiscal_year', 'quarter', 'month', 'census_round'));
