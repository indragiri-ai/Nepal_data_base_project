"""ECN.S1 — map the Election Commission's results portal, and prove it parses.

WHAT THIS IS
------------
A reconnaissance run, not a load. Nothing here writes to the warehouse. It
answers the three questions the step file asks before any modelling begins:

  1. WHICH elections does the portal actually serve?
  2. At WHAT granularity, and through which exact file paths?
  3. Does the data survive arithmetic — do the parts add up to the published
     whole?

It archives every payload it reads into the raw lake first (house rule 3), then
writes the inventory to `reference/ecn/inventory.json` and prints a report.

HOW THE PATHS WERE FOUND
------------------------
Not guessed. The portal's own scripts build them, and the templates below are
copied from those scripts:

  `/Scripts/MapElectionResult.js`   -> Election{cycle}/HOR/FPTP/HOR-{d}-{c}.json
  `/Scripts/PRMapElectionResult.js` -> Election{cycle}/HOR/PR/District/{d}.json
  the landing page + PRVoteChartResult -> Election{cycle}/Common/*.txt
  ElectionResultCentral{cycle}.aspx -> ElectionResultCentral{cycle}.txt

WHAT THE CROSS-CHECKS ARE FOR
-----------------------------
The step's acceptance gate asks for "plausible totals". Comparing against a
number from a press release we have not verified would be guessing, so the
checks here are internal and self-proving — the source is asked to agree with
itself:

  * the 77 district PR files must sum, party by party, to the national PR total;
  * the candidate-level results table must yield exactly the seat counts the
    portal's own party chart shows;
  * the seats must add up to the size of the house.

A check that fails is REPORTED, never silently absorbed: this is a spike, and a
disagreement in the source is the single most valuable thing it can find.

Run with `make ecn-probe` (add `--no-raw` to skip the archive write).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ingestion.common.io_utf8 import configure_stdout_utf8  # noqa: E402
from ingestion.common.raw_lake import RawLake, RawLakeError  # noqa: E402
from ingestion.election.ecn_client import EcnClient, EcnError, decode_json  # noqa: E402

DATASET_CODE = "ecn/results"
INVENTORY_PATH = Path("reference/ecn/inventory.json")

# The two general elections the portal serves in full. Both are House of
# Representatives elections; 2079 also carries the provincial assemblies, which
# were elected the same day. Nepali years (BS) are how the portal names them and
# how we name them back — the Gregorian date belongs in the indicator
# definition, not in a path.
CYCLES = ("2082", "2079")

# The size of the House of Representatives elected under FPTP. Constitutional,
# not derived: 165 constituencies plus 110 proportional seats = 275 members.
HOR_FPTP_SEATS = 165

# Files whose ABSENCE is a finding worth recording, so a later session does not
# repeat this search. Each was probed; each 404s. See PROVENANCE.md.
EXPECTED_ABSENT = (
    "JSONFiles/Election2074/Common/PRHoRPartyTop5.txt",
    "JSONFiles/Election2081/Common/PRHoRPartyTop5.txt",
    "JSONFiles/Election2082/Common/VoteCountHORPA.txt",
    "JSONFiles/Election2082/HOR/VoteCount/HOR-1-1.json",
    "JSONFiles/Election2079/Common/VoteCountHORPA.txt",
)


def common(cycle: str, name: str) -> str:
    return f"JSONFiles/Election{cycle}/Common/{name}"


def lookup(cycle: str, name: str) -> str:
    return f"JSONFiles/Election{cycle}/Local/Lookup/{name}"


@dataclass
class ProbeResult:
    """One probed path and what came back — the unit of the inventory."""

    label: str
    file_path: str
    status_code: int
    content_type: str
    size_bytes: int
    rows: int | None = None
    note: str = ""

    @property
    def served(self) -> bool:
        return self.status_code == 200 and "json" in self.content_type.lower()


@dataclass
class CycleData:
    cycle: str
    districts: list[dict[str, Any]] = field(default_factory=list)
    constituencies: list[dict[str, Any]] = field(default_factory=list)
    pr_national: list[dict[str, Any]] = field(default_factory=list)
    pr_by_district: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    fptp_party_chart: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)


def real_districts(districts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The portal's district lookup carries two placeholder rows (id 98 and 99,
    name "NA", no province). They are not districts and are dropped here rather
    than silently surviving into a join."""
    return [d for d in districts if d.get("parentId") is not None and d.get("name") != "NA"]


def harvest_cycle(
    client: EcnClient,
    cycle: str,
    probes: list[ProbeResult],
    raw_payloads: list[tuple[str, bytes, str]],
) -> CycleData:
    """Read one election cycle end to end, recording every probe and keeping
    every byte for the raw archive."""
    data = CycleData(cycle=cycle)

    def grab(label: str, path: str, note: str = "") -> Any:
        """Fetch one path: record the probe, keep the raw bytes, return the rows
        (or None if the portal did not serve JSON — a probe, not a failure)."""
        got = client.fetch(path)
        parsed: Any = None
        rows: int | None = None
        if got.is_json:
            parsed = decode_json(got.content)
            rows = len(parsed) if isinstance(parsed, list) else None
            raw_payloads.append((path, got.content, got.url))
        probes.append(
            ProbeResult(
                label=label,
                file_path=path,
                status_code=got.status_code,
                content_type=got.content_type,
                size_bytes=len(got.content),
                rows=rows,
                note=note,
            )
        )
        return parsed

    grab("province lookup", lookup(cycle, "states.json"), "7 provinces; not yet used downstream")
    data.districts = grab("district lookup", lookup(cycle, "districts.json")) or []
    data.constituencies = (
        grab("HoR constituency lookup", f"JSONFiles/Election{cycle}/HOR/Lookup/constituencies.json")
        or []
    )
    data.pr_national = (
        grab("PR party votes, national", common(cycle, "PRHoRPartyTop5.txt"), "the headline result")
        or []
    )
    data.fptp_party_chart = (
        grab("FPTP seats by party", common(cycle, "HoRPartyTop5.txt"), "the portal's seat chart")
        or []
    )
    data.candidates = (
        grab(
            "candidate-level FPTP results",
            f"JSONFiles/ElectionResultCentral{cycle}.txt",
            "every candidate in every constituency, in one file",
        )
        or []
    )

    # District-level PR: one file per district. This is the choropleth material,
    # and fetching every one of them is also the completeness test.
    for district_id in sorted(d["id"] for d in real_districts(data.districts)):
        rows = grab(
            f"PR votes, district {district_id}",
            f"JSONFiles/Election{cycle}/HOR/PR/District/{district_id}.json",
        )
        if rows is not None:
            data.pr_by_district[district_id] = rows

    return data


def cross_check(data: CycleData) -> list[tuple[str, bool, str]]:
    """Ask the source to agree with itself. Returns (name, passed, detail)."""
    checks: list[tuple[str, bool, str]] = []
    cycle = data.cycle

    # 0. Did we actually GET every district? This has to come first. The first
    # run of this spike was throttled part-way through, harvested 62 of 77
    # districts, and the totals check below duly "failed" — blaming the source
    # for our own incomplete read. A reconciliation over a partial harvest is
    # not evidence of anything, so coverage is asserted before arithmetic.
    expected = len(real_districts(data.districts))
    got = len(data.pr_by_district)
    checks.append(
        (
            f"{cycle}: a PR file was read for every district",
            expected > 0 and got == expected,
            f"{got} of {expected} districts read"
            + ("" if got == expected else " — the totals below are NOT meaningful"),
        )
    )

    # 1. Do the district PR files reconstruct the national PR total, exactly?
    national = {r["PoliticalPartyName"]: r["TotalVoteReceived"] for r in data.pr_national}
    summed: dict[str, int] = defaultdict(int)
    for rows in data.pr_by_district.values():
        for r in rows:
            summed[r["PoliticalPartyName"]] += r["TotalVoteReceived"]
    nat_total = sum(national.values())
    dist_total = sum(summed.values())
    checks.append(
        (
            f"{cycle}: district PR votes sum to the national total",
            nat_total == dist_total,
            f"national {nat_total:,} vs sum of {len(data.pr_by_district)} districts {dist_total:,}"
            f" (difference {dist_total - nat_total:+,})",
        )
    )
    mismatched = [p for p in national if national[p] != summed.get(p, 0)]
    checks.append(
        (
            f"{cycle}: every party's district votes sum to its national figure",
            not mismatched,
            "all parties agree"
            if not mismatched
            else f"{len(mismatched)} parties disagree, e.g. {mismatched[:3]}",
        )
    )

    # 2. Do the candidate rows reproduce the portal's own seat chart?
    elected = [c for c in data.candidates if c.get("Remarks") == "Elected"]
    seats_from_candidates: dict[str, int] = defaultdict(int)
    for c in elected:
        seats_from_candidates[c["PoliticalPartyName"]] += 1
    chart = {r["PoliticalPartyName"]: r["TotWin"] for r in data.fptp_party_chart}
    chart_total = sum(chart.values())
    checks.append(
        (
            f"{cycle}: elected candidates match the seat chart's total",
            len(elected) == chart_total,
            f"{len(elected)} candidates marked Elected vs {chart_total} seats in the chart",
        )
    )

    # 3. Does the house come out the right size?
    checks.append(
        (
            f"{cycle}: FPTP seats total {HOR_FPTP_SEATS}",
            chart_total == HOR_FPTP_SEATS,
            f"chart totals {chart_total}",
        )
    )

    # 4. Is the constituency lookup internally sound? (77 districts, 165 seats)
    by_district: dict[int, int] = {}
    duplicates = []
    for row in data.constituencies:
        did = row["distId"]
        if did in by_district:
            duplicates.append(did)
        by_district[did] = row["consts"]
    checks.append(
        (
            f"{cycle}: constituency lookup has one row per district",
            not duplicates,
            "no duplicate districts"
            if not duplicates
            else f"district code(s) {duplicates} appear twice — seats would be double-counted",
        )
    )
    checks.append(
        (
            f"{cycle}: constituency lookup sums to {HOR_FPTP_SEATS} seats over unique districts",
            sum(by_district.values()) == HOR_FPTP_SEATS,
            f"{len(by_district)} districts, {sum(by_district.values())} seats",
        )
    )
    return checks


def report_cycle(data: CycleData) -> None:
    cycle = data.cycle
    print(f"\n--- Election {cycle} BS " + "-" * 46)
    real = len(real_districts(data.districts))
    print(f"  districts in lookup   : {real} (real; placeholders dropped)")
    print(f"  PR parties (national) : {len(data.pr_national)}")
    print(f"  district PR files     : {len(data.pr_by_district)}")
    print(f"  candidate rows        : {len(data.candidates):,}")

    ordered = sorted(data.pr_national, key=lambda r: -r["TotalVoteReceived"])
    total = sum(r["TotalVoteReceived"] for r in ordered)
    print(f"\n  Proportional-representation votes — top 5 of {len(ordered)} parties")
    print(f"  (total valid PR votes counted: {total:,})")
    for row in ordered[:5]:
        votes = row["TotalVoteReceived"]
        share = votes / total * 100 if total else 0
        print(f"    {votes:>10,}  {share:5.2f}%  {row['PoliticalPartyName']}")

    seats = sorted(data.fptp_party_chart, key=lambda r: -r["TotWin"])
    print(f"\n  First-past-the-post seats — {sum(r['TotWin'] for r in seats)} constituencies")
    for row in seats[:5]:
        print(f"    {row['TotWin']:>10}         {row['PoliticalPartyName']}")


def probe_absences(client: EcnClient, probes: list[ProbeResult]) -> None:
    """Record the paths that are NOT served, so nobody searches for them twice."""
    for path in EXPECTED_ABSENT:
        got = client.fetch(path)
        probes.append(
            ProbeResult(
                label="absent (recorded so it is not re-searched)",
                file_path=path,
                status_code=got.status_code,
                content_type=got.content_type,
                size_bytes=len(got.content),
                note="not served by the portal",
            )
        )


def write_inventory(
    probes: list[ProbeResult],
    checks: list[tuple[str, bool, str]],
    raw_ref: str | None,
) -> None:
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "probed_at": datetime.now(UTC).isoformat(),
        "portal": "https://result.election.gov.np",
        "handler": "/Handlers/SecureJson.ashx?file=<path>",
        "cycles_served": list(CYCLES),
        "raw_archive": raw_ref,
        "checks": [{"check": n, "passed": p, "detail": d} for n, p, d in checks],
        "probes": [
            {
                "label": p.label,
                "file": p.file_path,
                "http": p.status_code,
                "content_type": p.content_type,
                "bytes": p.size_bytes,
                "rows": p.rows,
                "note": p.note,
            }
            for p in probes
        ],
    }
    INVENTORY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nInventory written to {INVENTORY_PATH} ({len(probes)} paths probed).")


def main(argv: list[str] | None = None) -> int:
    configure_stdout_utf8()
    parser = argparse.ArgumentParser(description="ECN.S1 — map the ECN results portal.")
    parser.add_argument(
        "--no-raw", action="store_true", help="skip the raw-lake archive (rehearsal only)"
    )
    parser.add_argument(
        "--cycle", action="append", help="limit to one election cycle (repeatable), e.g. 2082"
    )
    args = parser.parse_args(argv)
    cycles = tuple(args.cycle) if args.cycle else CYCLES

    print("ECN.S1 — Election Commission results portal reconnaissance")
    print("=" * 62)

    client = EcnClient()
    try:
        client.open_session()
    except EcnError as exc:
        print(f"FAILED to open a session: {exc}")
        return 1
    print("Session opened (CSRF cookie received).")

    probes: list[ProbeResult] = []
    all_checks: list[tuple[str, bool, str]] = []
    all_raw: list[tuple[str, bytes, str]] = []

    for cycle in cycles:
        print(f"\nHarvesting election {cycle} BS ...")
        data = harvest_cycle(client, cycle, probes, all_raw)
        report_cycle(data)
        all_checks.extend(cross_check(data))

    print("\nProbing the paths we expect to be absent ...")
    probe_absences(client, probes)

    print("\n--- Cross-checks " + "-" * 45)
    failed = 0
    for name, passed, detail in all_checks:
        mark = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"  [{mark}] {name}\n         {detail}")

    raw_ref: str | None = None
    if args.no_raw:
        print("\n--no-raw: nothing archived.")
    else:
        try:
            lake = RawLake.from_env()
            stored = lake.store_snapshot(DATASET_CODE, all_raw, snapshot_filename="probe.json")
            raw_ref = stored.payload_path
            print(
                f"\nArchived {len(all_raw)} payloads to the raw lake as one snapshot:"
                f"\n  {stored.payload_path} ({stored.size_bytes:,} bytes,"
                f" sha256 {stored.sha256[:16]}…)"
            )
        except RawLakeError as exc:
            print(f"\nRaw archive FAILED: {exc}")
            failed += 1

    write_inventory(probes, all_checks, raw_ref)

    served = sum(1 for p in probes if p.served)
    print(f"\nSummary: {served}/{len(probes)} probed paths served JSON; {failed} check(s) failed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
