-- 0006_indicator_origin_source.sql
-- Separate an indicator's ORIGIN (where its data actually comes from — immutable
-- provenance) from its PREFERRED source (the headline choice for display,
-- P2B.S4 / decision 0005).
--
-- Until now preferred_source_id doubled as both, which breaks down once two
-- sources measure the same fact: the census is the headline (preferred) for
-- population/literacy, while the World Bank series stays a labelled alternative
-- that must STILL be refreshed from the World Bank. The WB ingestion therefore
-- scopes on origin_source_id (stable) and never on the mutable preferred choice.
--
-- Backfill: today the two coincide for every indicator (nothing has been
-- repointed yet), so origin = the current preferred value. After this migration,
-- `make seed` maintains origin_source_id (= the indicator's own source) and
-- repoints preferred_source_id for the collision alternatives.

ALTER TABLE indicators ADD COLUMN origin_source_id bigint REFERENCES sources (id);

UPDATE indicators SET origin_source_id = preferred_source_id;

ALTER TABLE indicators ALTER COLUMN origin_source_id SET NOT NULL;
