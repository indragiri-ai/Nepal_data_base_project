-- 0002_dimensions.rollback.sql
-- Undo of 0002_dimensions.sql. Dropped in reverse dependency order: indicators
-- references units (and sources), so it goes before units. The shared
-- set_updated_at() function is left in place — it was created by 0001 and is
-- still used by the provenance tables.

DROP TABLE IF EXISTS time_periods;
DROP TABLE IF EXISTS geographies;
DROP TABLE IF EXISTS indicators;
DROP TABLE IF EXISTS units;
