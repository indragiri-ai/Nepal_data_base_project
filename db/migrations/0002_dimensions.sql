-- 0002_dimensions.sql
-- The dimension tables (Blueprint §4.2, §2.1 "one universal data model").
-- Where 0001 recorded WHERE data comes from, these record WHAT each number means:
--   units         -- the unit a value is measured in (%, US$, persons, ...)
--   indicators    -- the master list of measurable things (GDP, population, ...)
--   geographies   -- every place, at every level, with validity periods
--   time_periods  -- every period once, on one true timeline (calendar + fiscal + BS)
-- Every future dataset plugs into these same four tables.
--
-- Standards: snake_case; plural names; `id` PKs; `<table>_id` FKs; NOT NULL by
-- default; timestamptz created_at/updated_at on every table; CHECK constraints
-- for enums. name_ne / definition_ne hold Nepali text as UTF-8 Devanagari.

-- units: the measurement units a value can be expressed in.
CREATE TABLE units (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code       text        NOT NULL,   -- stable short code, e.g. 'USD', 'PCT', 'PERSONS'
    name_en    text        NOT NULL,
    name_ne    text,                   -- Nepali name; UTF-8 Devanagari; nullable
    notes      text,                   -- e.g. conversion notes
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT units_code_unique UNIQUE (code)
);

CREATE TRIGGER units_set_updated_at
    BEFORE UPDATE ON units
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- indicators: the master list of measurable things. `code` is permanent and
-- human-readable (e.g. GDP_USD); `source_concept` records the source's own code
-- (e.g. World Bank 'SP.POP.TOTL') so we can map back to it.
CREATE TABLE indicators (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                text        NOT NULL,   -- permanent stable code, e.g. 'GDP_USD'
    name_en             text        NOT NULL,
    name_ne             text,                   -- Nepali name; UTF-8 Devanagari; filled in Phase 3
    definition_en       text,
    definition_ne       text,                   -- Nepali definition; UTF-8 Devanagari
    unit_id             bigint      NOT NULL REFERENCES units (id),  -- every indicator has a unit
    topic               text        NOT NULL,
    source_concept      text,                   -- the source's own code, e.g. WDI 'SP.POP.TOTL'
    preferred_source_id bigint      REFERENCES sources (id),  -- nullable: default source for display
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT indicators_code_unique UNIQUE (code),
    CONSTRAINT indicators_topic_check
        CHECK (topic IN ('population', 'economy', 'labor', 'health', 'education',
                         'agriculture', 'environment', 'governance'))
);

CREATE TRIGGER indicators_set_updated_at
    BEFORE UPDATE ON indicators
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- geographies: every place at every administrative level. The self-referencing
-- parent_id builds the hierarchy (country → province → district → local_unit);
-- valid_from/valid_to capture the 2015 boundary restructuring (old units stay as
-- rows, distinguished by level and validity dates).
CREATE TABLE geographies (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code         text        NOT NULL,
    name_en      text        NOT NULL,
    name_ne      text,                   -- Nepali name; UTF-8 Devanagari, e.g. 'नेपाल'
    level        text        NOT NULL,
    parent_id    bigint      REFERENCES geographies (id),  -- self-FK; null for country
    valid_from   date,                   -- nullable: not always known
    valid_to     date,                   -- nullable: null means still valid
    geometry_ref text,                   -- link/path to a boundary (GeoJSON) file; nullable
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT geographies_code_unique UNIQUE (code),
    CONSTRAINT geographies_level_check
        CHECK (level IN ('country', 'province', 'district', 'local_unit',
                         'old_region', 'old_district'))
);

CREATE TRIGGER geographies_set_updated_at
    BEFORE UPDATE ON geographies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- time_periods: every period stored exactly once with its true Gregorian start/
-- end dates, plus labels for the calendar (gregorian_label), fiscal year, and
-- Bikram Sambat (bs_label). Data attaches to a period, never to a bare year, so
-- BS / fiscal / calendar series can share one true time axis (Blueprint §5.1).
CREATE TABLE time_periods (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_type     text        NOT NULL,
    gregorian_start date        NOT NULL,
    gregorian_end   date        NOT NULL,
    bs_label        text,                   -- e.g. '2080/81'; nullable (international data has none)
    gregorian_label text        NOT NULL,   -- e.g. '2024' or 'FY 2023/24'
    sort_key        integer     NOT NULL,   -- orders periods along the timeline
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT time_periods_type_check
        CHECK (period_type IN ('year', 'fiscal_year', 'quarter', 'month', 'census_round')),
    CONSTRAINT time_periods_unique UNIQUE (period_type, gregorian_start, gregorian_end)
);

CREATE TRIGGER time_periods_set_updated_at
    BEFORE UPDATE ON time_periods
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
