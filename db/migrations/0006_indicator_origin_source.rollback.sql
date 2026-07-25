-- Rollback for 0006_indicator_origin_source.sql
ALTER TABLE indicators DROP COLUMN IF EXISTS origin_source_id;
