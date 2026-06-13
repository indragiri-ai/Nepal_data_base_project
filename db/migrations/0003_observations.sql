-- 0003_observations.sql
-- The observations fact table (Blueprint §4.2, §4.3) — the heart of the portal.
-- Every statistic from every source ends up as ONE row here:
--   "this indicator, for this geography, in this time period (with these
--    breakdowns) = this value, in this unit, from this dataset/release."
--
-- Two mechanisms built here are what make revisions safe:
--   1. A uniqueness constraint so the same cell cannot be duplicated within a
--      release (but CAN recur across releases — that is a revision).
--   2. An `is_latest` flag, maintained by a trigger, so the newest published
--      value wins the default view while older values are never deleted.

CREATE TABLE observations (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    indicator_id   bigint      NOT NULL REFERENCES indicators (id),
    geography_id   bigint      NOT NULL REFERENCES geographies (id),
    time_period_id bigint      NOT NULL REFERENCES time_periods (id),
    dataset_id     bigint      NOT NULL REFERENCES datasets (id),
    release_id     bigint      NOT NULL REFERENCES releases (id),
    value          numeric     NOT NULL,   -- numeric, never float (Master Prompt §3.2)
    unit_id        bigint      NOT NULL REFERENCES units (id),
    breakdowns     jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- e.g. {"sex":"female","age":"15+"}
    status         text        NOT NULL,
    is_latest      boolean     NOT NULL DEFAULT true,
    footnote       text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT observations_status_check
        CHECK (status IN ('provisional', 'revised', 'final', 'estimated')),
    -- Blueprint §4.2: the same (indicator, geography, period, breakdowns) may
    -- appear once PER release. A newer release becomes a new row (a revision);
    -- the same number twice in one release is rejected.
    CONSTRAINT observations_unique_per_release
        UNIQUE (indicator_id, geography_id, time_period_id, breakdowns, release_id)
);

-- Keep updated_at truthful (shared function from 0001).
CREATE TRIGGER observations_set_updated_at
    BEFORE UPDATE ON observations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- is_latest maintenance. On INSERT of a new observation, demote any earlier row
-- for the SAME cell (indicator, geography, period, breakdowns) so only the newest
-- carries is_latest = true. Assumes inserts arrive in release order, which the
-- ingestion pipeline guarantees (each run creates a new release dated today).
-- Nothing is deleted — old rows remain, just flagged is_latest = false.
CREATE FUNCTION observations_set_is_latest() RETURNS trigger AS $$
BEGIN
    UPDATE observations
       SET is_latest = false
     WHERE indicator_id   = NEW.indicator_id
       AND geography_id   = NEW.geography_id
       AND time_period_id = NEW.time_period_id
       AND breakdowns     = NEW.breakdowns
       AND id <> NEW.id
       AND is_latest;
    RETURN NULL;  -- AFTER trigger: return value is ignored
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER observations_is_latest
    AFTER INSERT ON observations
    FOR EACH ROW EXECUTE FUNCTION observations_set_is_latest();

-- Index: serves GET /v1/data?indicator=&geo= — the latest series for one
-- indicator and geography, ordered by period. Partial on is_latest because the
-- default public view only ever shows current values. Also speeds the is_latest
-- trigger's own lookup.
CREATE INDEX observations_latest_series_idx
    ON observations (indicator_id, geography_id, time_period_id)
    WHERE is_latest;

-- Index: serves revision/audit queries that fetch or join all rows of one
-- release (e.g. "everything loaded in release X").
CREATE INDEX observations_release_idx
    ON observations (release_id);
