-- Rollback of 0009_disaster_foundations.sql.
--
-- Dropped in foreign-key order: incidents reference hazards, and both
-- crosswalks reference geographies, which is left untouched. No `observations`
-- row and no seeded reference data is affected — the disaster indicators and
-- their yearly totals arrive in a later migration and are removed by its own
-- rollback, not this one.

DROP TABLE IF EXISTS disaster_incidents;
DROP TABLE IF EXISTS disaster_hazards;
DROP TABLE IF EXISTS bipad_geography_crosswalk;
DROP TABLE IF EXISTS geography_crosswalk;
