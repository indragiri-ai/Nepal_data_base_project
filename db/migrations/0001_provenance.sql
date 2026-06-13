-- 0001_provenance.sql
-- The provenance spine (Blueprint §4.2, Master Prompt §3.2).
-- These four tables record WHERE every number comes from. They are created
-- first, before any data tables, so that no statistic can ever exist in this
-- database without a traceable source, dataset, and release behind it.
--
-- Standards applied: snake_case; plural table names; `id` primary keys;
-- `<table>_id` foreign keys; timestamptz created_at/updated_at on every table;
-- NOT NULL by default; CHECK constraints documenting allowed enum values.

-- A reusable trigger that stamps updated_at = now() on every UPDATE, so the
-- column is always truthful without the application having to remember.
CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- sources: one row per publishing organization (e.g. World Bank, Nepal Rastra Bank).
CREATE TABLE sources (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name_en         text        NOT NULL,
    name_ne         text,                      -- Nepali name; nullable (e.g. World Bank has none)
    type            text        NOT NULL,
    url             text,
    default_license text,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sources_type_check
        CHECK (type IN ('international', 'central_bank', 'statistics_office', 'ministry')),
    CONSTRAINT sources_name_en_unique UNIQUE (name_en)
);

CREATE TRIGGER sources_set_updated_at
    BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- datasets: a specific publication or API from a source (e.g. "World Development Indicators").
CREATE TABLE datasets (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id         bigint      NOT NULL REFERENCES sources (id),
    name_en           text        NOT NULL,
    name_ne           text,
    license           text,
    update_frequency  text,                    -- free text for now, e.g. "annual", "monthly"
    access_method     text        NOT NULL,
    documentation_url text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT datasets_access_method_check
        CHECK (access_method IN ('api', 'file', 'scrape', 'manual')),
    CONSTRAINT datasets_source_name_unique UNIQUE (source_id, name_en)
);

CREATE TRIGGER datasets_set_updated_at
    BEFORE UPDATE ON datasets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- releases: one row each time a dataset is published or updated. This is what
-- makes revision tracking possible — a newer release of the same figure becomes
-- a new observation rather than overwriting the old one.
CREATE TABLE releases (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id     bigint      NOT NULL REFERENCES datasets (id),
    release_date   date        NOT NULL,
    period_covered text,                       -- e.g. "1960–2024"; nullable
    raw_file_refs  jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- paths to raw-lake payloads
    notes          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER releases_set_updated_at
    BEFORE UPDATE ON releases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ingestion_log: the audit trail — one row per pipeline run, success or failure
-- (Master Prompt §3.3). Written whether the run succeeds or fails.
CREATE TABLE ingestion_log (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id    bigint      NOT NULL REFERENCES datasets (id),
    release_id    bigint      REFERENCES releases (id),  -- nullable: a failed run may make no release
    status        text        NOT NULL,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    rows_in       integer,
    rows_loaded   integer,
    rows_rejected integer,
    raw_file_refs jsonb       NOT NULL DEFAULT '[]'::jsonb,
    error_note    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ingestion_log_status_check
        CHECK (status IN ('running', 'success', 'failed'))
);

CREATE TRIGGER ingestion_log_set_updated_at
    BEFORE UPDATE ON ingestion_log
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
