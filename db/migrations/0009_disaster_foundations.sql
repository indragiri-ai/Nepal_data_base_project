-- 0009_disaster_foundations.sql
-- Tables for Nepal's disaster record (DIS.S1). No data is loaded here.
--
-- WHY A NEW TABLE AT ALL, when every other source fits `observations`
-- -------------------------------------------------------------------
-- `observations` stores ONE NUMBER about a place, a period and an indicator.
-- That is the right shape for a price, a population or a budget line, and it
-- is the wrong shape for "a landslide at Jalbire on 31 August 2026 that killed
-- three people at 27.907N 85.756E". An incident is not a statistic: it has its
-- own identity, its own point on the ground, and several facts attached to
-- that one identity. Forcing it into `observations` would collide two floods
-- in the same district on the same day into a single cell (the unique
-- constraint is indicator+geography+period+breakdowns, with no room for an
-- event id) and would throw the coordinates away entirely.
--
-- So incidents live here, and the YEARLY TOTALS derived from them go into
-- `observations` in the normal way (DIS.S3). The portal then gets both: a map
-- of individual events, and disaster figures that flow through search, sector
-- cards, choropleths and CSV export like every other indicator.
--
-- WHY THESE ROWS MAY BE UPDATED, when observations may never be
-- -------------------------------------------------------------
-- Rule 5 of CLAUDE.md — revisions never overwrite — governs published
-- statistics, where a revised figure is a new release the public can compare
-- against the old one. A BIPAD incident is not that. It is a live operational
-- record: a death toll rises through the days after a flood as reports come in,
-- and the portal must show the current count, not the first wire report. Every
-- row therefore records `first_seen_release_id` and `last_seen_release_id`, so
-- when a record was first taken and when it was last confirmed is always
-- answerable, and the untouched payload of every run stays in the raw lake.
--
-- NO POSTGIS
-- ----------
-- Coordinates are two plain doubles with a Nepal bounding-box CHECK. The one
-- geometric question this project asks — which district contains this point —
-- is answered before insert by ray casting against the same boundary files the
-- website draws (`ingestion/common/geo_point.py`). Installing PostGIS to
-- answer it in SQL would add an extension to a 500 MB free tier for no gain.

-- Pre-2015 boundaries, per blueprint §5.2: data is stored against the
-- boundaries it was published in, and comparison across the 2015 restructuring
-- goes through this crosswalk, never through a silent reassignment.
-- Seeded from db/seeds/geography_crosswalk.csv.
CREATE TABLE geography_crosswalk (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    old_geography_id bigint      NOT NULL REFERENCES geographies (id),
    new_geography_id bigint      NOT NULL REFERENCES geographies (id),
    -- 1.0 where a district survived the restructuring unchanged. A district
    -- that was SPLIT has no honest share without a weighting nobody has
    -- published, so it gets NO ROW here at all: its records stay at the old
    -- district and are reported as such. Nawalparasi and Rukum are the two.
    allocation_share numeric     NOT NULL CHECK (allocation_share > 0 AND allocation_share <= 1),
    method           text        NOT NULL CHECK (method IN ('exact_name', 'manual_review', 'boundary')),
    note             text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT geography_crosswalk_unique UNIQUE (old_geography_id, new_geography_id)
);

CREATE TRIGGER geography_crosswalk_set_updated_at
    BEFORE UPDATE ON geography_crosswalk
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- BIPAD names places its own way ("Phaktanglung" for our "Phaktanlung"), and
-- 161 of its 830 places differ from ours by romanisation alone. This table is
-- the reviewed answer, seeded from db/seeds/bipad_geography_crosswalk.csv,
-- which is built from two independent kinds of evidence — an exact name match
-- within the district, and the place's own centroid tested against the
-- official boundary. `evidence` records which supported each row. On the build
-- of 2026-09-07 the two methods agreed 669 times and disagreed zero times.
CREATE TABLE bipad_geography_crosswalk (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bipad_level    text        NOT NULL CHECK (bipad_level IN ('district', 'municipality')),
    bipad_id       integer     NOT NULL,
    bipad_code     text,
    bipad_title_en text        NOT NULL,
    geography_id   bigint      NOT NULL REFERENCES geographies (id),
    -- 'manual_review' is a person's decision, recorded in
    -- db/seeds/bipad_geography_overrides.csv with the reasoning; it is never
    -- the tool's own fallback when the evidence runs out.
    evidence       text        NOT NULL
        CHECK (evidence IN ('both', 'name', 'boundary', 'manual_review')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bipad_geography_crosswalk_unique UNIQUE (bipad_level, bipad_id)
);

CREATE TRIGGER bipad_geography_crosswalk_set_updated_at
    BEFORE UPDATE ON bipad_geography_crosswalk
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- The hazard vocabulary, mirrored from BIPAD's own /hazard/ endpoint so that a
-- hazard we have never seen fails loudly at load time instead of arriving as an
-- unlabelled number. `hazard_group` is the coarser bucket used for breakdowns
-- and map colours, so that adding a 13th hazard upstream does not silently
-- reshape every chart.
CREATE TABLE disaster_hazards (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id    bigint      NOT NULL REFERENCES sources (id),
    source_code  text        NOT NULL,   -- the publisher's own id, as text
    code         text        NOT NULL,   -- our stable code, e.g. 'flood'
    hazard_group text        NOT NULL,
    name_en      text        NOT NULL,
    name_ne      text,
    hazard_type  text        NOT NULL CHECK (hazard_type IN ('natural', 'non_natural')),
    color        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT disaster_hazards_code_unique UNIQUE (code),
    CONSTRAINT disaster_hazards_source_unique UNIQUE (source_id, source_code)
);

CREATE TRIGGER disaster_hazards_set_updated_at
    BEFORE UPDATE ON disaster_hazards
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE disaster_incidents (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id            bigint      NOT NULL REFERENCES datasets (id),
    source_incident_id    text        NOT NULL,   -- the publisher's own id
    first_seen_release_id bigint      NOT NULL REFERENCES releases (id),
    last_seen_release_id  bigint      NOT NULL REFERENCES releases (id),
    hazard_id             bigint      NOT NULL REFERENCES disaster_hazards (id),
    -- The geography the incident's OWN coordinates fall inside, resolved before
    -- insert. NOT NULL on purpose: an incident we cannot place is rejected and
    -- counted in ingestion_log.rows_rejected, never filed against a guess.
    geography_id          bigint      NOT NULL REFERENCES geographies (id),
    lat                   double precision CHECK (lat BETWEEN 26.0 AND 30.7),
    lon                   double precision CHECK (lon BETWEEN 79.9 AND 88.3),
    incident_on           date        NOT NULL,
    reported_on           date,
    title_en              text        NOT NULL,
    title_ne              text,
    street_address        text,
    verified              boolean     NOT NULL DEFAULT false,
    -- Human impact. NULL means the source published no figure; 0 means it
    -- published a zero. The difference matters when a total is summed, so it
    -- is kept rather than flattened.
    deaths                integer     CHECK (deaths >= 0),
    missing               integer     CHECK (missing >= 0),
    injured               integer     CHECK (injured >= 0),
    affected_people       integer     CHECK (affected_people >= 0),
    affected_families     integer     CHECK (affected_families >= 0),
    houses_destroyed      integer     CHECK (houses_destroyed >= 0),
    estimated_loss_npr    numeric     CHECK (estimated_loss_npr >= 0),
    raw_ref               text        NOT NULL,   -- raw-lake payload this came from
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT disaster_incidents_source_unique UNIQUE (dataset_id, source_incident_id),
    -- Coordinates are both present or both absent. DesInventar's 24,257
    -- historical records carry latitude 0 for every one of them, which means
    -- "not recorded" — those load with NULL coordinates and appear in the
    -- district figures without pretending to a location they never had.
    CONSTRAINT disaster_incidents_point_complete
        CHECK ((lat IS NULL) = (lon IS NULL))
);

CREATE TRIGGER disaster_incidents_set_updated_at
    BEFORE UPDATE ON disaster_incidents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The map asks "what happened here, between these dates"; the feed asks "what
-- happened lately"; the aggregates ask "how many in this district this year".
CREATE INDEX disaster_incidents_date_idx ON disaster_incidents (incident_on DESC);
CREATE INDEX disaster_incidents_geo_date_idx ON disaster_incidents (geography_id, incident_on);
CREATE INDEX disaster_incidents_hazard_idx ON disaster_incidents (hazard_id);
CREATE INDEX disaster_incidents_point_idx ON disaster_incidents (lon, lat)
    WHERE lat IS NOT NULL;
