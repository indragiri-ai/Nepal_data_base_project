-- 0004_bs_calendar.rollback.sql
-- Undo of 0004_bs_calendar.sql. Dropping the table removes its trigger and
-- indexes automatically. The shared set_updated_at() function (from 0001) is
-- left in place.

DROP TABLE IF EXISTS bs_calendar;
