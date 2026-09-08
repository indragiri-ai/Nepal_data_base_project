"""Which Nepali geography contains this point?

Disaster records arrive with coordinates and a place NAME, and the two do not
agree often enough to trust names alone: BIPAD writes "Phaktanglung" where the
official gazetteer writes "Phaktanlung", and 199 of 774 BIPAD municipalities
differ from ours by transliteration. Matching those by eye, or by fuzzy string
distance, would be guessing — which this project does not do (CLAUDE.md rule 1).

A coordinate inside an official boundary is not a guess. It is a geometric fact
anybody can re-check, so that is what we use. Measured on 2026-09-07 against
BIPAD's own municipality centroids: 554 places where the name and the boundary
both resolved AGREED, with **zero** disagreements, and the boundary resolved a
further 199 that names could not. The 21 that neither method resolved turned
out to be national parks and wildlife reserves — not local units at all.

No geometry dependency. Ray casting is exact for this question, and adding
shapely/GEOS to the project for one crosswalk would cost more than it earns.
The boundary files are the same ones the website draws
(`web/public/maps/*.json`, OCHA P-codes), so a point placed here lands in the
polygon a reader sees on the map — one source of truth, not two.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MAPS_DIR = _PROJECT_ROOT / "web" / "public" / "maps"

# Which GeoJSON, and which property in it carries the P-code, per level.
BOUNDARY_FILES: dict[str, tuple[str, str]] = {
    "province": ("nepal-provinces.json", "ADM1_PCODE"),
    "district": ("nepal-districts.json", "DIST_PCODE"),
    "local_unit": ("nepal-local-units.json", "ADM3_PCODE"),
}

Ring = list[list[float]]


@dataclass(frozen=True)
class Boundary:
    """One geography's outline, with its bounding box precomputed."""

    code: str
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    polygons: tuple[tuple[Ring, ...], ...]  # each polygon: outer ring, then holes

    def contains(self, lon: float, lat: float) -> bool:
        if not (self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat):
            return False
        for rings in self.polygons:
            outer, holes = rings[0], rings[1:]
            if _in_ring(lon, lat, outer) and not any(_in_ring(lon, lat, h) for h in holes):
                return True
        return False


def _in_ring(lon: float, lat: float, ring: Ring) -> bool:
    """Ray casting: cross the ring's edges due west and count the crossings.

    An odd count means the point is inside. Points exactly on an edge are not
    guaranteed either way — a coordinate that lands on a district line is
    genuinely ambiguous, and the caller sees it as a miss rather than as a
    confident wrong answer.
    """
    inside = False
    count = len(ring)
    for index in range(count):
        lon1, lat1 = ring[index][0], ring[index][1]
        lon2, lat2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        if (lat1 > lat) != (lat2 > lat):
            crossing_lon = lon1 + (lat - lat1) * (lon2 - lon1) / (lat2 - lat1)
            if lon < crossing_lon:
                inside = not inside
    return inside


def _rings_of(geometry: dict[str, Any]) -> Iterator[tuple[Ring, ...]]:
    kind = geometry.get("type")
    if kind == "Polygon":
        yield tuple(geometry["coordinates"])
    elif kind == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            yield tuple(polygon)
    else:
        raise ValueError(f"Unsupported geometry type: {kind!r}")


class BoundaryIndex:
    """Every boundary at one level, searchable by point."""

    def __init__(self, boundaries: list[Boundary]) -> None:
        self.boundaries = boundaries

    @classmethod
    def for_level(cls, level: str, maps_dir: Path | None = None) -> BoundaryIndex:
        try:
            filename, code_property = BOUNDARY_FILES[level]
        except KeyError:
            raise ValueError(
                f"No boundary file for level {level!r}; have {sorted(BOUNDARY_FILES)}"
            ) from None
        return cls.from_geojson((maps_dir or MAPS_DIR) / filename, code_property)

    @classmethod
    def from_geojson(cls, path: Path, code_property: str) -> BoundaryIndex:
        data = json.loads(path.read_text(encoding="utf-8"))
        boundaries: list[Boundary] = []
        for feature in data["features"]:
            code = feature["properties"].get(code_property)
            if not code:
                raise ValueError(f"{path.name}: a feature has no {code_property}")
            polygons = tuple(_rings_of(feature["geometry"]))
            lons = [point[0] for rings in polygons for point in rings[0]]
            lats = [point[1] for rings in polygons for point in rings[0]]
            boundaries.append(
                Boundary(
                    code=code,
                    min_lon=min(lons),
                    min_lat=min(lats),
                    max_lon=max(lons),
                    max_lat=max(lats),
                    polygons=polygons,
                )
            )
        return cls(boundaries)

    def locate(self, lon: float, lat: float) -> str | None:
        """The P-code of the geography containing this point, or None.

        None is a real answer, not a failure to try: a coordinate can fall
        outside Nepal, land in the sliver between two simplified boundaries, or
        be a placeholder zero. The caller must count those and refuse to guess,
        rather than attach the record to whichever polygon happens to be near.
        """
        for boundary in self.boundaries:
            if boundary.contains(lon, lat):
                return boundary.code
        return None

    def __len__(self) -> int:
        return len(self.boundaries)
