"""Server-side limits; the browser cannot raise these values.

Every cap is sized from a live count of the warehouse (2026-09-07), with room
to grow, so that no honest request the portal itself makes is refused. The
point is to refuse the *dishonest* ones: the unfiltered Kalimati series is
106,236 observations (about 15 MB of JSON) and would otherwise be served to
anyone who asks, repeatedly.

  measured today            cap here
  ----------------------    ---------
  4,675  widest one series  8,000   KALIMATI_PRICE_AVG / Cauli Local, daily since 2013
  753    widest map         800     every local unit, census 2021
  6,777  widest breakdown   8,000   CENSUS_HH_DRINKING_WATER by local unit
  1,496  indicators served  4,000   grows with the World Bank catalog
"""

from datetime import date

MAX_ROWS = 8_000
MAX_GEO_ROWS = 800
MAX_BREAKDOWN_ROWS = 8_000
MAX_INDICATOR_ROWS = 4_000
MAX_META_ROWS = 100
MAX_SEASONALITY_ROWS = 500
MAX_SPARK_CODES = 120
MAX_SPARK_POINTS = 16
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

# A day per row for a century: long enough that no real series is refused,
# short enough that a hand-typed range cannot ask for the whole warehouse.
MAX_WINDOW_DAYS = 36_600


class QueryTooBroad(ValueError):
    """The request would return more than the server is willing to build."""


def bounded[T](rows: list[T], maximum: int = MAX_ROWS) -> list[T]:
    """Refuse an oversized result instead of serving it.

    Every caller asks the database for `maximum + 1` rows, so an overflow is
    detected without ever materialising the whole thing.
    """
    if len(rows) > maximum:
        raise QueryTooBroad(
            f"That request covers more than {maximum:,} rows. Narrow it with a "
            "breakdown filter, a date range, or a smaller geography."
        )
    return rows


def validate_window(
    key: str | None,
    value: str | None,
    start: date | None,
    end: date | None,
) -> None:
    """Reject nonsense filters before they reach the database."""
    if (key is None) != (value is None):
        raise QueryTooBroad("breakdown_key and breakdown_value must be given together")
    if (start is None) != (end is None):
        raise QueryTooBroad("start and end must be given together")
    if start is not None and end is not None:
        if end < start:
            raise QueryTooBroad("The date range ends before it starts.")
        if (end - start).days + 1 > MAX_WINDOW_DAYS:
            raise QueryTooBroad(f"Date range must be no longer than {MAX_WINDOW_DAYS:,} days.")
