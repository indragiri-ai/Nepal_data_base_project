"""BIPAD incidents into the warehouse (DIS.S2).

Nepal's own record of what happened where: 63,151 incidents since 2011-04-14,
each with a point on the ground and, usually, a count of who was harmed.

SHAPE OF A RUN
--------------
    read reference (short DB connection)
      -> fetch every page from BIPAD with NO DB connection open
      -> archive the untouched pages to the raw lake BEFORE parsing any of them
      -> resolve each incident's geography, rejecting what cannot be placed
      -> upsert under one release, in batches
      -> close the ingestion_log

That order is the house rule (docs/runbooks/adding-a-data-source.md): nothing is
parsed until the bytes it came from are safely stored, and the database is not
held open across a long HTTP harvest — Supabase's free tier drops connections
that idle through one.

WHY THIS UPSERTS, WHERE EVERY OTHER PIPELINE ONLY INSERTS
---------------------------------------------------------
Rule 5 — revisions never overwrite — governs published statistics, where a
revised figure is a new release a reader can compare against the old one. A
BIPAD incident is not that. It is a live operational record: the death toll of a
landslide rises over the days after it, as reports come in. The portal must show
the current count, so the row is updated, and `first_seen_release_id` /
`last_seen_release_id` record when it was first taken and last confirmed. Every
run's untouched payload stays in the raw lake, so any earlier state is
recoverable from the archive rather than from the warehouse.

PLACING AN INCIDENT
-------------------
The incident's OWN coordinates are used first, tested against the official
boundary the website draws. That is more accurate than any name, and more
accurate than the municipality BIPAD files it under. Only when a point is
missing or falls outside every boundary does it fall back to the ward, and then
to BIPAD's municipality through the reviewed crosswalk. An incident that neither
method places is REJECTED and counted — never attached to a guess.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.bipad.client import BipadError, fetch_all, fetch_pages, point_of  # noqa: E402
from ingestion.common.geo_point import BoundaryIndex  # noqa: E402
from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.raw_lake import RawLake, RawLakeError  # noqa: E402

SOURCE_NAME = "National Disaster Risk Reduction and Management Authority"
SOURCE_URL = "https://bipadportal.gov.np/"
DATASET_NAME = "BIPAD Portal — disaster incidents"
DATASET_DOCS = "https://bipadportal.gov.np/api/v1/"
DATASET_CODE = "bipad/incidents"

# BIPAD publishes no licence statement. Recording a guess ("CC BY", "open")
# would be inventing terms on a government's behalf, so the field says exactly
# what is known and no more.
DATASET_LICENSE = "No licence stated by the publisher (Government of Nepal, NDRRMA)"

BATCH = 2000  # Supabase drops connections under sustained row-by-row writes

# How far back an incremental run re-reads. BIPAD corrects an incident's death
# toll for days after the event, so resuming from exactly the newest date we
# hold would miss every one of those corrections.
OVERLAP_DAYS = 30

# Supabase Storage refuses an object over 50 MB on the free tier, and a full
# harvest is far larger than that: 63,151 incidents with their losses expanded
# is roughly 90 MB of JSON, which the snapshot's base64 encoding inflates
# further. So the archive is written in parts, each well under the ceiling.
# Every part's path is recorded, so the run is still reconstructible from the
# raw lake alone.
ARCHIVE_CHUNK_BYTES = 15 * 1024 * 1024


class BipadPipelineError(Exception):
    pass


@dataclass(frozen=True)
class Placed:
    """One incident, resolved and ready to write."""

    source_incident_id: str
    hazard_code: str
    geography_code: str
    lat: float | None
    lon: float | None
    incident_on: date
    reported_on: date | None
    title_en: str
    title_ne: str | None
    street_address: str | None
    verified: bool
    deaths: int | None
    missing: int | None
    injured: int | None
    affected_people: int | None
    affected_families: int | None
    houses_destroyed: int | None
    estimated_loss_npr: float | None


def _scalar(cur: psycopg.Cursor[Any]) -> Any:
    row = cur.fetchone()
    return None if row is None else row[0]


def slugify(title: str) -> str:
    """A stable code from a hazard's English title: 'Forest Fire' -> forest_fire."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", title.strip().lower())
    return cleaned.strip("_")


def ensure_source_and_dataset(cur: psycopg.Cursor[Any]) -> int:
    """NDRRMA is the SOURCE; BIPAD is the portal it publishes through.

    BIPAD is an origin, not an aggregator: these are the government's own
    records, fed by police and local-government reporting.
    """
    cur.execute(
        "INSERT INTO sources (name_en, name_ne, type, url, default_license, notes)"
        " VALUES (%s, %s, 'ministry', %s, %s, %s)"
        " ON CONFLICT (name_en) DO UPDATE SET url = EXCLUDED.url,"
        "   name_ne = EXCLUDED.name_ne,"
        "   default_license = EXCLUDED.default_license, notes = EXCLUDED.notes"
        " RETURNING id",
        (
            SOURCE_NAME,
            "राष्ट्रिय विपद् जोखिम न्यूनीकरण तथा व्यवस्थापन प्राधिकरण",
            SOURCE_URL,
            DATASET_LICENSE,
            "The authority under the Ministry of Home Affairs that runs Nepal's "
            "disaster information system. 'ministry' is the closest value the "
            "sources.type CHECK allows; NDRRMA is an authority under one.",
        ),
    )
    source_id = _scalar(cur)
    cur.execute(
        "INSERT INTO datasets (source_id, name_en, license, update_frequency,"
        "  access_method, documentation_url)"
        " VALUES (%s, %s, %s, %s, 'api', %s)"
        " ON CONFLICT (source_id, name_en) DO UPDATE SET license = EXCLUDED.license,"
        "   update_frequency = EXCLUDED.update_frequency,"
        "   documentation_url = EXCLUDED.documentation_url"
        " RETURNING id",
        (source_id, DATASET_NAME, DATASET_LICENSE, "continuous", DATASET_DOCS),
    )
    return int(_scalar(cur))


def load_hazards(cur: psycopg.Cursor[Any], source_id: int) -> dict[int, str]:
    """Mirror BIPAD's hazard vocabulary. Returns {bipad hazard id: our code}.

    `hazard_group` is set to the hazard's own code: BIPAD publishes 47 hazards
    and no grouping of them, and inventing an editorial taxonomy here — is
    "Heavy Rainfall" a flood? — would be this project putting words in the
    government's mouth. A curated grouping seed can be added later if the charts
    need coarser buckets; the column exists so that change needs no migration.
    """
    hazards = fetch_all("hazard")
    if not hazards:
        raise BipadPipelineError("BIPAD returned no hazards; refusing to load incidents")
    mapping: dict[int, str] = {}
    for hazard in hazards:
        title_en = hazard.get("titleEn") or hazard.get("title") or ""
        code = slugify(title_en)
        if not code:
            raise BipadPipelineError(f"hazard {hazard.get('id')} has no usable title")
        kind = (hazard.get("type") or "").strip().lower().replace(" ", "_")
        if kind not in ("natural", "non_natural"):
            raise BipadPipelineError(
                f"hazard {hazard.get('id')} has an unknown type {hazard.get('type')!r} — "
                "the vocabulary changed upstream and needs a look"
            )
        cur.execute(
            "INSERT INTO disaster_hazards"
            " (source_id, source_code, code, hazard_group, name_en, name_ne, hazard_type, color)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (source_id, source_code) DO UPDATE SET"
            "   name_en = EXCLUDED.name_en, name_ne = EXCLUDED.name_ne,"
            "   hazard_type = EXCLUDED.hazard_type, color = EXCLUDED.color",
            (
                source_id,
                str(hazard["id"]),
                code,
                code,
                title_en,
                hazard.get("titleNe") or None,
                kind,
                hazard.get("color") or None,
            ),
        )
        mapping[int(hazard["id"])] = code
    return mapping


def read_crosswalk(cur: psycopg.Cursor[Any]) -> dict[int, str]:
    """{BIPAD municipality id: our P-code}, from the reviewed seed."""
    cur.execute(
        "SELECT x.bipad_id, g.code FROM bipad_geography_crosswalk x"
        " JOIN geographies g ON g.id = x.geography_id"
        " WHERE x.bipad_level = 'municipality'"
    )
    return {int(bipad_id): code for bipad_id, code in cur.fetchall()}


def _int_or_none(value: Any) -> int | None:
    """NULL and 0 are different claims: 'not published' against 'published as
    zero'. Keeping them apart matters when a column is summed."""
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _float_or_none(value: Any) -> float | None:
    """A published money figure, or None when the source gave none."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _date_or_none(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def place(
    incident: dict[str, Any],
    boundaries: dict[str, BoundaryIndex],
    ward_to_municipality: dict[int, int],
    crosswalk: dict[int, str],
) -> tuple[str | None, float | None, float | None, str]:
    """(P-code, lat, lon, how) for one incident. P-code None means unplaceable.

    The coordinate is tried against the finest boundary first and then the
    coarser ones. That cascade is not a nicety: Nepal's national parks lie
    OUTSIDE every local unit, so a snake bite in Shuklaphanta has a perfectly
    good coordinate that belongs to no municipality — but does belong to
    Kanchanpur district. Rejecting it would lose a real record; assigning it to
    the nearest municipality would invent one. Recording it at the district,
    with its coordinate intact, is the precision the source actually supports.
    """
    point = point_of(incident)
    if point is not None:
        lon, lat = point
        for level in ("local_unit", "district", "province"):
            located = boundaries[level].locate(lon, lat)
            if located is not None:
                return located, lat, lon, f"point ({level})"
        # A real coordinate outside Nepal altogether. Keep it — it is what the
        # source published — but let the ward decide the place.
        for ward in incident.get("wards") or []:
            municipality = ward_to_municipality.get(int(ward))
            if municipality and municipality in crosswalk:
                return crosswalk[municipality], lat, lon, "ward (point outside Nepal)"
        return None, lat, lon, "unplaceable"
    for ward in incident.get("wards") or []:
        municipality = ward_to_municipality.get(int(ward))
        if municipality and municipality in crosswalk:
            return crosswalk[municipality], None, None, "ward"
    return None, None, None, "unplaceable"


def parse(
    incidents: list[dict[str, Any]],
    hazards: dict[int, str],
    boundaries: dict[str, BoundaryIndex],
    ward_to_municipality: dict[int, int],
    crosswalk: dict[int, str],
) -> tuple[list[Placed], dict[str, int], dict[str, int], list[str]]:
    """Turn BIPAD's records into rows, counting everything refused and why.

    Returns (rows, how each was placed, rejections by reason, examples).
    """
    placed: list[Placed] = []
    how_placed: dict[str, int] = {}
    rejected: dict[str, int] = {}
    examples: list[str] = []

    def refuse(reason: str, incident: dict[str, Any]) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1
        if len(examples) < 10:
            examples.append(f"{reason}: incident {incident.get('id')} {incident.get('title')!r}")

    for incident in incidents:
        hazard_id = incident.get("hazard")
        if hazard_id is None or int(hazard_id) not in hazards:
            refuse("unknown hazard", incident)
            continue
        occurred = _date_or_none(incident.get("incidentOn"))
        if occurred is None:
            refuse("no usable date", incident)
            continue
        geography_code, lat, lon, how = place(
            incident, boundaries, ward_to_municipality, crosswalk
        )
        if geography_code is None:
            refuse("could not be placed", incident)
            continue
        how_placed[how] = how_placed.get(how, 0) + 1
        loss = incident.get("loss")
        if not isinstance(loss, dict):
            loss = {}
        estimated = _float_or_none(loss.get("estimatedLoss"))
        placed.append(
            Placed(
                source_incident_id=str(incident["id"]),
                hazard_code=hazards[int(hazard_id)],
                geography_code=geography_code,
                lat=lat,
                lon=lon,
                incident_on=occurred,
                reported_on=_date_or_none(incident.get("reportedOn")),
                title_en=(incident.get("title") or "").strip() or "Untitled incident",
                title_ne=(incident.get("titleNe") or "").strip() or None,
                street_address=(incident.get("streetAddress") or "").strip() or None,
                verified=bool(incident.get("verified")),
                deaths=_int_or_none(loss.get("peopleDeathCount")),
                missing=_int_or_none(loss.get("peopleMissingCount")),
                injured=_int_or_none(loss.get("peopleInjuredCount")),
                affected_people=_int_or_none(loss.get("peopleAffectedCount")),
                affected_families=_int_or_none(loss.get("familyAffectedCount")),
                houses_destroyed=_int_or_none(loss.get("infrastructureDestroyedHouseCount")),
                estimated_loss_npr=estimated,
            )
        )
    return placed, how_placed, rejected, examples


def harvest(since: date | None) -> tuple[list[dict[str, Any]], list[tuple[str, bytes, str]]]:
    """Every incident from BIPAD, plus the untouched bytes of each page.

    ORDERED BY `id`, WHICH IS NOT A DETAIL. Offset paging is only correct when
    the ordering is total. Ordering by `incident_on` is not: thousands of
    incidents share a date and the database breaks those ties however it likes,
    differently on each request. Proved on 2026-09-07 by asking for the same
    offset twice — `ordering=incident_on` returned two different sets of five
    incidents, `ordering=id` returned the same five both times. The first full
    harvest used the date ordering and fetched 63,151 records containing only
    62,729 distinct ids: 422 arrived twice, and as many were skipped entirely.
    `id` is unique, so the walk is stable and the harvest complete.
    """
    params: dict[str, Any] = {"expand": "loss", "ordering": "id"}
    if since is not None:
        params["incident_on__gt"] = since.isoformat()
    incidents: list[dict[str, Any]] = []
    pages: list[tuple[str, bytes, str]] = []
    for number, page in enumerate(fetch_pages("incident", params)):
        incidents.extend(page.results)
        pages.append((f"page_{number:04d}.json", page.raw, page.url))
        print(f"    page {number + 1:>4}  {len(incidents):>7,} incidents", flush=True)
    return incidents, pages


def check_harvest_is_whole(incidents: list[dict[str, Any]]) -> int:
    """Refuse a harvest that repeated itself. Returns the duplicate count.

    A duplicate is the fingerprint of unstable paging, and unstable paging
    silently DROPS as many records as it repeats. Better to fail the run than
    to publish a record with holes in it that nobody can see.
    """
    seen = {str(incident.get("id")) for incident in incidents}
    duplicates = len(incidents) - len(seen)
    if duplicates:
        raise BipadPipelineError(
            f"the harvest returned {len(incidents):,} records but only {len(seen):,} "
            f"distinct ids ({duplicates:,} repeats). Offset paging drifted, which means "
            "records were skipped as well as repeated — refusing to load a partial record."
        )
    return duplicates


def chunk_pages(
    pages: list[tuple[str, bytes, str]], budget: int = ARCHIVE_CHUNK_BYTES
) -> list[list[tuple[str, bytes, str]]]:
    """Split the harvested pages into archive-sized parts.

    Splits by BYTES, not by a page count: a page of 500 flood incidents with
    long Nepali titles is many times the size of a page of 500 snake bites, so
    a fixed page count would still blow the ceiling on a bad day.
    """
    chunks: list[list[tuple[str, bytes, str]]] = []
    current: list[tuple[str, bytes, str]] = []
    size = 0
    for page in pages:
        if current and size + len(page[1]) > budget:
            chunks.append(current)
            current, size = [], 0
        current.append(page)
        size += len(page[1])
    if current:
        chunks.append(current)
    return chunks


def archive(pages: list[tuple[str, bytes, str]]) -> list[str]:
    """Store the untouched pages, in parts. Returns every path written."""
    lake = RawLake.from_env()
    chunks = chunk_pages(pages)
    refs: list[str] = []
    for number, chunk in enumerate(chunks, start=1):
        stored = lake.store_snapshot(
            DATASET_CODE, chunk, snapshot_filename=f"snapshot_part{number:02d}.json"
        )
        refs.append(stored.payload_path)
        megabytes = sum(len(p[1]) for p in chunk) / 1024 / 1024
        print(f"    part {number}/{len(chunks)}: {len(chunk)} pages, {megabytes:.1f} MB raw")
    return refs


def resume_point(cur: psycopg.Cursor[Any], dataset_id: int) -> date | None:
    """Where an incremental run starts: the newest incident we hold, less an
    overlap, so corrections to recent tolls are picked up rather than frozen."""
    cur.execute(
        "SELECT max(incident_on) FROM disaster_incidents WHERE dataset_id = %s", (dataset_id,)
    )
    newest = _scalar(cur)
    if newest is None:
        return None
    return newest - timedelta(days=OVERLAP_DAYS)


def load(placed: list[Placed], dataset_id: int, conn: psycopg.Connection[Any]) -> tuple[int, int]:
    """Upsert every incident under one release. Returns (release id, rows)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO releases (dataset_id, release_date) VALUES (%s, CURRENT_DATE)"
            " RETURNING id",
            (dataset_id,),
        )
        release_id = int(_scalar(cur))
        cur.execute("SELECT code, id FROM geographies")
        geography_ids = {code: gid for code, gid in cur.fetchall()}
        cur.execute("SELECT code, id FROM disaster_hazards")
        hazard_ids = {code: hid for code, hid in cur.fetchall()}

        rows = [
            (
                dataset_id,
                p.source_incident_id,
                release_id,
                release_id,
                hazard_ids[p.hazard_code],
                geography_ids[p.geography_code],
                p.lat,
                p.lon,
                p.incident_on,
                p.reported_on,
                p.title_en,
                p.title_ne,
                p.street_address,
                p.verified,
                p.deaths,
                p.missing,
                p.injured,
                p.affected_people,
                p.affected_families,
                p.houses_destroyed,
                p.estimated_loss_npr,
                DATASET_CODE,
            )
            for p in placed
        ]
        for start in range(0, len(rows), BATCH):
            cur.executemany(
                "INSERT INTO disaster_incidents"
                " (dataset_id, source_incident_id, first_seen_release_id, last_seen_release_id,"
                "  hazard_id, geography_id, lat, lon, incident_on, reported_on, title_en,"
                "  title_ne, street_address, verified, deaths, missing, injured,"
                "  affected_people, affected_families, houses_destroyed, estimated_loss_npr,"
                "  raw_ref)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                "         %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (dataset_id, source_incident_id) DO UPDATE SET"
                "   last_seen_release_id = EXCLUDED.last_seen_release_id,"
                "   hazard_id = EXCLUDED.hazard_id, geography_id = EXCLUDED.geography_id,"
                "   lat = EXCLUDED.lat, lon = EXCLUDED.lon,"
                "   incident_on = EXCLUDED.incident_on, reported_on = EXCLUDED.reported_on,"
                "   title_en = EXCLUDED.title_en, title_ne = EXCLUDED.title_ne,"
                "   street_address = EXCLUDED.street_address, verified = EXCLUDED.verified,"
                "   deaths = EXCLUDED.deaths, missing = EXCLUDED.missing,"
                "   injured = EXCLUDED.injured, affected_people = EXCLUDED.affected_people,"
                "   affected_families = EXCLUDED.affected_families,"
                "   houses_destroyed = EXCLUDED.houses_destroyed,"
                "   estimated_loss_npr = EXCLUDED.estimated_loss_npr,"
                "   raw_ref = EXCLUDED.raw_ref",
                rows[start : start + BATCH],
            )
            conn.commit()
            print(f"  committed {min(start + BATCH, len(rows)):>7,} / {len(rows):,}", flush=True)
    return release_id, len(rows)


def main() -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=date.fromisoformat, default=None,
                        help="only incidents AFTER this date (YYYY-MM-DD)")
    parser.add_argument("--full", action="store_true",
                        help="ignore what is already loaded and re-read everything")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch, parse and report; write nothing")
    args = parser.parse_args()

    load_dotenv()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise BipadPipelineError("DATABASE_URL is not set")

    # --- reference, on a short connection -----------------------------------
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        dataset_id = ensure_source_and_dataset(cur)
        cur.execute("SELECT source_id FROM datasets WHERE id = %s", (dataset_id,))
        source_id = int(_scalar(cur))
        print("Reading BIPAD's hazard vocabulary...")
        hazards = load_hazards(cur, source_id)
        print(f"  {len(hazards)} hazards")
        crosswalk = read_crosswalk(cur)
        if not crosswalk:
            raise BipadPipelineError(
                "bipad_geography_crosswalk is empty — run `make seed` first (DIS.S1)"
            )
        since = args.since
        if since is None and not args.full:
            since = resume_point(cur, dataset_id)
        conn.commit()

    print(f"  {len(crosswalk)} municipalities in the reviewed crosswalk")
    boundaries = {
        level: BoundaryIndex.for_level(level)
        for level in ("local_unit", "district", "province")
    }
    print("  boundaries: " + ", ".join(f"{len(v)} {k}" for k, v in boundaries.items()))
    print("Reading BIPAD's ward list (to place incidents that carry no point)...")
    ward_to_municipality = {
        int(w["id"]): int(w["municipality"])
        for w in fetch_all("ward")
        if w.get("municipality") is not None
    }
    print(f"  {len(ward_to_municipality):,} wards")

    # --- harvest, with no DB connection open --------------------------------
    print(f"\nHarvesting incidents{f' after {since}' if since else ' (everything)'}...")
    incidents, pages = harvest(since)
    print(f"  {len(incidents):,} incidents in {len(pages)} pages")
    if not incidents:
        print("Nothing new to load.")
        return 0
    check_harvest_is_whole(incidents)

    # --- raw first ----------------------------------------------------------
    raw_refs: list[str] = []
    if not args.dry_run:
        try:
            raw_refs = archive(pages)
            print(f"  archived {len(pages)} pages as {len(raw_refs)} object(s)")
        except RawLakeError as exc:
            raise BipadPipelineError(
                f"raw archive failed, so nothing is parsed or loaded: {exc}"
            ) from exc

    placed, how_placed, rejected, examples = parse(
        incidents, hazards, boundaries, ward_to_municipality, crosswalk
    )
    print(f"\nPlaced: {len(placed):,}   rejected: {sum(rejected.values()):,}")
    for how, count in sorted(how_placed.items(), key=lambda kv: -kv[1]):
        print(f"    {count:>6,}  placed by {how}")
    for reason, count in sorted(rejected.items(), key=lambda kv: -kv[1]):
        print(f"    {count:>6,}  REJECTED: {reason}")
    for example in examples:
        print(f"      e.g. {example}")

    if args.dry_run:
        print("\nDRY RUN — nothing written.")
        return 0
    if not placed:
        raise BipadPipelineError("every incident was rejected; refusing to record a release")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingestion_log (dataset_id, status, raw_file_refs)"
                " VALUES (%s, 'running', %s::jsonb) RETURNING id",
                (dataset_id, json.dumps(raw_refs)),
            )
            log_id = _scalar(cur)
            conn.commit()
        try:
            release_id, written = load(placed, dataset_id, conn)
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE ingestion_log SET status = 'failed', finished_at = now(),"
                    " error_note = %s WHERE id = %s",
                    (f"{type(exc).__name__}: {exc}"[:500], log_id),
                )
                conn.commit()
            raise
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ingestion_log SET status = 'success', finished_at = now(),"
                " release_id = %s, rows_in = %s, rows_loaded = %s, rows_rejected = %s"
                " WHERE id = %s",
                (release_id, len(incidents), written, sum(rejected.values()), log_id),
            )
            conn.commit()
            cur.execute("SELECT count(*) FROM disaster_incidents WHERE dataset_id = %s",
                        (dataset_id,))
            total = _scalar(cur)
    print(f"\nWrote {written:,} incidents under release {release_id}.")
    print(f"The warehouse now holds {total:,} BIPAD incidents.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BipadError, BipadPipelineError) as error:
        print(f"\nFAILURE: {error}")
        raise SystemExit(1) from error
