-- 0005_nrb_bfs_staging.sql
-- Staging table for NRB "Banking and Financial Statistics — Monthly" (BFS).
--
-- Blueprint §2.2 / Master Prompt §3.3: data extracted from human-made files
-- (Excel/PDF) must pass through a STAGING + REVIEW step before it may be
-- promoted to `observations`. This table is that holding area for the BFS
-- publication's table C4 ("Major Financial Indicators").
--
-- One row = one value of one indicator for one BFI class in one BS month,
-- as extracted from one raw-lake object. The review workflow moves
-- review_status: pending -> approved -> promoted (or rejected).
-- A re-extraction that finds a CHANGED value for an already-promoted cell
-- resets it to 'pending' — that is a source revision awaiting human review;
-- promotion then relies on the observations is_latest mechanics (P1.S5).

CREATE TABLE nrb_bfs_staging (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- provenance back to the exact raw file (raw-lake payload path + URL)
    raw_ref        text        NOT NULL,
    source_url     text        NOT NULL,
    -- the BS month this value describes (NRB publishes "as on <month> End")
    bs_year        integer     NOT NULL CHECK (bs_year BETWEEN 2000 AND 2199),
    bs_month       integer     NOT NULL CHECK (bs_month BETWEEN 1 AND 12),
    period_label   text        NOT NULL,   -- C4's title line, verbatim
    -- what was extracted
    sheet          text        NOT NULL DEFAULT 'C4',
    row_label      text        NOT NULL,   -- label exactly as printed
    section        text        NOT NULL,   -- e.g. 'Credit & deposit ratios'
    indicator_code text        NOT NULL,   -- canonical portal code (indicators.code)
    bfi_class      text        NOT NULL,
    value          numeric     NOT NULL,   -- numeric, never float (Master Prompt §3.2)
    unit_code      text        NOT NULL,
    -- review workflow
    review_status  text        NOT NULL DEFAULT 'pending',
    review_note    text,
    extracted_at   timestamptz NOT NULL DEFAULT now(),
    reviewed_at    timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT nrb_bfs_staging_class_check
        CHECK (bfi_class IN ('commercial_banks', 'development_banks',
                             'finance_companies', 'overall')),
    CONSTRAINT nrb_bfs_staging_status_check
        CHECK (review_status IN ('pending', 'approved', 'rejected', 'promoted')),
    -- one cell per (month, indicator, class); re-extraction upserts it
    CONSTRAINT nrb_bfs_staging_cell_unique
        UNIQUE (bs_year, bs_month, indicator_code, bfi_class)
);

-- Keep updated_at truthful (shared function from 0001).
CREATE TRIGGER nrb_bfs_staging_set_updated_at
    BEFORE UPDATE ON nrb_bfs_staging
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The review queue is always consulted by status.
CREATE INDEX nrb_bfs_staging_status_idx ON nrb_bfs_staging (review_status);
