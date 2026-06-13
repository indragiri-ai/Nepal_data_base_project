-- 0001_provenance.rollback.sql
-- Undo of 0001_provenance.sql. Tables are dropped in reverse dependency order
-- (children before parents) so foreign keys never block the drop. The trigger
-- function is removed last, after the triggers that used it are gone with their
-- tables.

DROP TABLE IF EXISTS ingestion_log;
DROP TABLE IF EXISTS releases;
DROP TABLE IF EXISTS datasets;
DROP TABLE IF EXISTS sources;
DROP FUNCTION IF EXISTS set_updated_at();
