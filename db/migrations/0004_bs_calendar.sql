-- 0004_bs_calendar.sql
-- The Bikram Sambat (BS) <-> Gregorian (AD) day-level reference table.
--
-- Blueprint §5.1: Nepali-date conversion is NEVER done by formula at query time.
-- BS month lengths are irregular (29-32 days) and vary year to year, published
-- each year in the Nepal Rajpatra; no arithmetic reproduces them. Instead we load
-- an authoritative day-level lookup once, and every later step (fiscal-year
-- periods in P2.S2, NRB fiscal-year data in P2.S8+) reads exact dates from here.
--
-- One row per Nepali calendar day. Loaded by scripts/load_bs_calendar.py from the
-- month-length table in reference/calendar/ (see reference/calendar/PROVENANCE.md).

CREATE TABLE bs_calendar (
    bs_year        smallint    NOT NULL,           -- e.g. 2080
    bs_month       smallint    NOT NULL,           -- 1 (Baisakh) .. 12 (Chaitra)
    bs_day         smallint    NOT NULL,           -- 1 .. 32 (month length varies)
    gregorian_date date        NOT NULL,           -- the exact AD date this BS day is
    weekday        smallint    NOT NULL,           -- 0=Sunday (आइतबार) .. 6=Saturday
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),

    -- One Nepali date is one row.
    CONSTRAINT bs_calendar_pk PRIMARY KEY (bs_year, bs_month, bs_day),
    -- ...and one Gregorian day maps to exactly one Nepali day (bijective).
    -- This is the strongest integrity guard we have: any off-by-one or duplicated
    -- day in the source would violate it and fail the load loudly.
    CONSTRAINT bs_calendar_gregorian_unique UNIQUE (gregorian_date),

    CONSTRAINT bs_calendar_month_check   CHECK (bs_month BETWEEN 1 AND 12),
    CONSTRAINT bs_calendar_day_check     CHECK (bs_day   BETWEEN 1 AND 32),
    CONSTRAINT bs_calendar_weekday_check CHECK (weekday  BETWEEN 0 AND 6)
);

-- The two lookup directions we actually use: AD date -> BS (covered by the unique
-- index above) and BS (year, month) -> its days (covered by the PK prefix).
CREATE INDEX bs_calendar_year_month_idx ON bs_calendar (bs_year, bs_month);

-- Keep updated_at truthful (shared function from 0001).
CREATE TRIGGER bs_calendar_set_updated_at
    BEFORE UPDATE ON bs_calendar
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
