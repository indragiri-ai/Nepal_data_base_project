-- 0003_observations.rollback.sql
-- Undo of 0003_observations.sql. Dropping the table removes its triggers and
-- indexes automatically; then the is_latest trigger function is removed. The
-- shared set_updated_at() function (from 0001) is left in place.

DROP TABLE IF EXISTS observations;
DROP FUNCTION IF EXISTS observations_set_is_latest();
