# Decision 0004 — The portal renders Nepal's official 2020 political map

**Date:** 2026-07-22
**Status:** accepted (founder priority; P2B.S1)
**Context:** The portal's boundary files (`web/public/maps/nepal-districts.json`,
`nepal-provinces.json`) were a 2017-vintage set (MIT `mesaugat/geoJSON-Nepal`).
Recon (2026-07-19, PROJECT_LOG) proved they are **pre-2020**: Darchula's
geometry topped out at 30.247°N and failed a Kalapani point-in-polygon test.
On 18 May 2020 the Government of Nepal issued a new official political map
adding the **Limpiyadhura–Lipulekh–Kalapani** territory (in Byas Rural
Municipality, Darchula, Sudurpaschim) — extending Darchula's northwest and the
national area from 147,181 → 147,516 km². A Nepal data portal showing the
pre-2020 border is arguably the single most visible correctness/credibility
failure a Nepali visitor could find.

## Decision

1. **The portal renders the Survey Department's official 2020 political map.**
   Every boundary file the portal ships must verify against it — specifically:
   Darchula extends to ≈(80.52°E, 30.44°N); national area within 1% of
   **147,516 km²**; 77 districts / 7 provinces present and joinable by P-code.

2. **Source (this revision):** the Survey Department's own *"New political and
   administrative boundaries"* shapefile, obtained via Open Data Nepal
   (organization = Survey Department), **CC-BY-SA**. Full provenance and the
   reproducible derivation are in
   `reference/geo/official-2020/PROVENANCE.md`. The outgoing pre-2020 files are
   archived, not deleted, under `reference/geo/pre-2020-archive/`.

3. **Boundaries are never traced or hand-drawn.** A boundary is only ever
   swapped in from an authoritative, openly-licensed source that passes the
   four checks above. If no such source can be found for a future change, we
   STOP and present options rather than approximate a border (report,
   never guess — this is a politically sensitive line).

4. **Attribution.** Map credit is *"Boundaries: Survey Department, Government of
   Nepal (official 2020 political map), via Open Data Nepal, CC-BY-SA."* The
   share-alike term travels with any redistribution of the boundary data.

## Consequences

- Only Darchula's geometry and the national outline change; **all P-code data
  joins are untouched** — `/population` still colours all 77 districts and 7
  provinces with no no-data regions (verified).
- The map now carries a local-datum origin (Everest 1937), reprojected to
  WGS84 for the portal; the residual sub-kilometre datum offset is documented
  and immaterial to attribute-based choropleths.
- Future boundary needs (e.g. the 753 local units in P2B.S8) should prefer this
  same Survey-Department source, since it already carries the correct 2020
  line and local-unit geometry.

## Note on OCHA/HDX COD-AB and the National Geoportal

Both were considered and **not** used as the boundary source for this revision:
the National Geoportal WFS still serves the pre-2020 international line in its
national layers (its "new" layers are the 2015 federal restructure, not the
2020 political map — see `docs/steps/onboard-nationalgeoportal.md`), and OCHA
COD-AB has historically tracked a pre-2020 line for the disputed sector. The
Survey Department's own published shapefile is both the highest authority and
carries the correct 2020 geometry.
