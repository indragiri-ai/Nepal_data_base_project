"use client";

// Election results (ECN.S4) — the Governance sector's centrepiece.
//
// Data: Election Commission of Nepal, via ECN.S1–S3. Two House of
// Representatives elections, 2082 BS (polled 5 March 2026) and 2079 BS
// (polled 20 November 2022).
//
// NEUTRALITY — the rules this panel is built to, not decorations on top of it:
//  * Parties are ordered by VOTES, descending. Never by our judgement.
//  * NO party brand colours. Each chart here is a SINGLE series — one measure
//    across named categories — so it takes ONE hue, and the party names on the
//    axis carry identity. Colouring 57 bars would both burn the palette and
//    invite brand association the portal has no business making.
//  * Party names appear EXACTLY as the Commission publishes them, in
//    Devanagari. We do not transliterate: an invented English name for a real
//    political party looks official and is not.
//  * Every figure cites the Commission and the election it belongs to.
//
// TWO THINGS THE PANEL MUST NOT IMPLY, and says out loud instead:
//  1. The map shows VOTES CAST, not turnout. The Commission publishes no
//     registered-voter figure for these elections through this channel, so the
//     denominator turnout needs simply does not exist in our data.
//  2. The seat chart is CONSTITUENCY seats only (165 of the 275). The 110
//     proportional seats are allocated in a separate Commission notice we have
//     not loaded, so these numbers are not a party's strength in the house.
//
// Dataviz method, applied:
//  * Form: magnitude across named categories at one point in time -> horizontal
//    bars, so party names read at full length instead of rotated.
//  * The long tail folds into one "All other parties" bar; the full list lives
//    in the table below, so nothing is hidden, only summarised.
//  * The map is SEQUENTIAL (one hue, light->dark) because share is magnitude.
//  * Table view + CSV: identity and value never depend on colour alone.

import { useEffect, useMemo, useState } from "react";
import EChart, { CHART_INK, TOOLTIP_STYLE, type ChartOption } from "@/components/EChart";
import ChoroplethMap, { type RegionDatum } from "@/components/ChoroplethMap";
import {
  ApiError,
  fetchGeoBreakdown,
  fetchSeries,
  type DataResponse,
  type GeoBreakdownResponse,
} from "@/lib/api";
import { downloadCsv } from "@/lib/csv";

/** The elections loaded, newest first. Polling dates come from the Commission's
 *  own documents (see reference/ecn/PROVENANCE.md) — the results portal itself
 *  publishes only the Bikram Sambat year. */
const ELECTIONS = [
  { period: "2026", bs: "२०८२", label: "2082 BS · 5 March 2026" },
  { period: "2022", bs: "२०७९", label: "2079 BS · 20 November 2022" },
] as const;

type Period = (typeof ELECTIONS)[number]["period"];

/** How many parties get their own bar before the tail is summarised. */
const BAR_CAP = 8;

const VOTES_HUE = "#2a78d6"; // --series-2, blue: the votes measure
const SEATS_HUE = "#4a3aa7"; // --series-4, violet: the seats measure

const nf = new Intl.NumberFormat("en-US");
const pct = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

interface PartyValue {
  party: string;
  value: number;
}

/** Top `cap` by value, with everything else summed into one labelled bar.
 *  Returns them ascending, which is the order a horizontal ECharts bar chart
 *  needs for the largest to sit at the top. */
function foldTail(rows: PartyValue[], cap: number): PartyValue[] {
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const head = sorted.slice(0, cap);
  const tail = sorted.slice(cap);
  const out = [...head];
  if (tail.length > 0) {
    out.push({
      party: `All other parties (${tail.length})`,
      value: tail.reduce((sum, r) => sum + r.value, 0),
    });
  }
  return out.reverse();
}

function partiesFor(series: DataResponse | null, period: Period): PartyValue[] {
  if (!series) return [];
  return series.observations
    .filter((o) => o.period === period && o.breakdowns?.party)
    .map((o) => ({ party: o.breakdowns!.party, value: o.value }));
}

export default function GovernancePanel() {
  const [period, setPeriod] = useState<Period>("2026");
  const [votes, setVotes] = useState<DataResponse | null>(null);
  const [seats, setSeats] = useState<DataResponse | null>(null);
  const [geo, setGeo] = useState<GeoBreakdownResponse | null>(null);
  const [party, setParty] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);

  // National figures for BOTH elections in one request each — switching the
  // election picker then costs nothing.
  useEffect(() => {
    let live = true;
    Promise.all([
      fetchSeries("ELECTION_VOTES_PR", "NP"),
      fetchSeries("ELECTION_SEATS", "NP"),
    ])
      .then(([v, s]) => {
        if (!live) return;
        setVotes(v);
        setSeats(s);
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof ApiError ? e.message : "Could not load election results.");
      });
    return () => {
      live = false;
    };
  }, []);

  // District detail, one election at a time — 4,389 cells for 2026.
  useEffect(() => {
    let live = true;
    setGeo(null);
    fetchGeoBreakdown("ELECTION_VOTES_PR", "district", "party", period)
      .then((g) => {
        if (live) setGeo(g);
      })
      .catch((e: unknown) => {
        if (live) {
          setError(
            e instanceof ApiError ? e.message : "Could not load the district results.",
          );
        }
      });
    return () => {
      live = false;
    };
  }, [period]);

  const nationalVotes = useMemo(() => partiesFor(votes, period), [votes, period]);
  const nationalSeats = useMemo(() => partiesFor(seats, period), [seats, period]);
  const totalVotes = useMemo(
    () => nationalVotes.reduce((sum, r) => sum + r.value, 0),
    [nationalVotes],
  );

  // The map's party defaults to whoever won the most votes in this election,
  // and follows the election when it changes — never a party that did not stand.
  const leadParty = nationalVotes.length
    ? [...nationalVotes].sort((a, b) => b.value - a.value)[0].party
    : null;
  const selectedParty = party && nationalVotes.some((p) => p.party === party) ? party : leadParty;

  const votesOption = useMemo<ChartOption | null>(() => {
    if (nationalVotes.length === 0) return null;
    const rows = foldTail(nationalVotes, BAR_CAP);
    return {
      grid: { left: 8, right: 104, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "item",
        valueFormatter: (v) => (v == null ? "—" : `${nf.format(v as number)} votes`),
      },
      xAxis: {
        type: "value",
        axisLabel: { color: CHART_INK.axisLabel, fontSize: 11, formatter: (v: number) => nf.format(v) },
        splitLine: { lineStyle: { color: CHART_INK.grid } },
      },
      yAxis: {
        type: "category",
        data: rows.map((r) => r.party),
        axisLabel: { color: CHART_INK.text, fontSize: 12, width: 300, overflow: "break", lineHeight: 14 },
        axisLine: { lineStyle: { color: CHART_INK.axisLine } },
        axisTick: { show: false },
      },
      series: [
        {
          type: "bar",
          name: "Votes",
          data: rows.map((r) => r.value),
          barMaxWidth: 18,
          barCategoryGap: "40%",
          itemStyle: { color: VOTES_HUE, borderRadius: [0, 4, 4, 0] },
          label: {
            show: true,
            position: "right",
            color: CHART_INK.secondary,
            fontSize: 11,
            formatter: (p) =>
              totalVotes > 0
                ? `${pct.format(((p.value as number) / totalVotes) * 100)}%`
                : nf.format(p.value as number),
          },
        },
      ],
    };
  }, [nationalVotes, totalVotes]);

  const seatsOption = useMemo<ChartOption | null>(() => {
    if (nationalSeats.length === 0) return null;
    const rows = foldTail(nationalSeats, BAR_CAP);
    return {
      grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "item",
        valueFormatter: (v) => (v == null ? "—" : `${nf.format(v as number)} seats`),
      },
      xAxis: {
        type: "value",
        axisLabel: { color: CHART_INK.axisLabel, fontSize: 11 },
        splitLine: { lineStyle: { color: CHART_INK.grid } },
      },
      yAxis: {
        type: "category",
        data: rows.map((r) => r.party),
        axisLabel: { color: CHART_INK.text, fontSize: 12, width: 300, overflow: "break", lineHeight: 14 },
        axisLine: { lineStyle: { color: CHART_INK.axisLine } },
        axisTick: { show: false },
      },
      series: [
        {
          type: "bar",
          name: "Seats",
          data: rows.map((r) => r.value),
          barMaxWidth: 18,
          barCategoryGap: "40%",
          itemStyle: { color: SEATS_HUE, borderRadius: [0, 4, 4, 0] },
          label: {
            show: true,
            position: "right",
            color: CHART_INK.secondary,
            fontSize: 11,
            formatter: (p) => nf.format(p.value as number),
          },
        },
      ],
    };
  }, [nationalSeats]);

  /** The selected party's share of each district's proportional vote. A share,
   *  not a raw count: raw votes would draw a population map — Kathmandu is
   *  darkest for every party — and say nothing about support. */
  const mapData = useMemo<RegionDatum[]>(() => {
    if (!geo || !selectedParty) return [];
    const totals = new Map(geo.geographies.map((g) => [g.geo_code, g.value]));
    const names = new Map(geo.geographies.map((g) => [g.geo_code, g]));
    const out: RegionDatum[] = [];
    for (const cell of geo.cells) {
      if (cell.key !== selectedParty) continue;
      const total = totals.get(cell.geo) ?? 0;
      const place = names.get(cell.geo);
      if (!place || total <= 0) continue;
      out.push({
        code: cell.geo,
        name: place.name,
        nameNe: place.name_ne,
        value: (cell.value / total) * 100,
      });
    }
    return out;
  }, [geo, selectedParty]);

  const election = ELECTIONS.find((e) => e.period === period)!;
  const mapRanked = useMemo(() => [...mapData].sort((a, b) => b.value - a.value), [mapData]);

  // Votes and seats are listed SEPARATELY and never joined on the party name.
  //
  // The Commission names the same party differently in its two files: in the
  // 2079 results the seat table says "नेपाल कम्युनिष्ट पार्टी (एमाले)" while the
  // proportional table says "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी
  // लेनिनवादी)". A name join silently produced "0 seats" for a party that won
  // 44 — a wrong number, which is worse than an absent one. And it cannot be
  // repaired by tidying names: in 2079 two parties contested the proportional
  // ballot under one joint symbol and appear as a single row, with no single
  // seat figure to attach to it.
  const voteRows = useMemo(
    () =>
      [...nationalVotes]
        .sort((a, b) => b.value - a.value)
        .map((r) => [
          r.party,
          nf.format(r.value),
          totalVotes > 0 ? `${pct.format((r.value / totalVotes) * 100)}%` : "—",
        ]),
    [nationalVotes, totalVotes],
  );

  const seatRows = useMemo(
    () =>
      [...nationalSeats]
        .sort((a, b) => b.value - a.value)
        .map((r) => [r.party.trim(), nf.format(r.value)]),
    [nationalSeats],
  );

  return (
    <section className="fiscal-panel" aria-labelledby="election-results">
      <div className="band-head">
        <h2 id="election-results">How Nepal voted</h2>
        {nationalVotes.length > 0 && (
          <button
            type="button"
            className="btn ghost small"
            onClick={() =>
              downloadCsv(`nepal-election-${period}-party-results.csv`, [
                [
                  "Measure",
                  "Party (as published by the Election Commission)",
                  "Value",
                  "Share of proportional vote (%)",
                  "Election",
                ],
                // Two measures, one file, kept as separate rows — the
                // Commission's party names differ between them, so pairing
                // them into one row per party would invent a link the source
                // does not support.
                ...voteRows.map((r) => [
                  "Proportional votes",
                  r[0],
                  r[1],
                  r[2],
                  election.label,
                ]),
                ...seatRows.map((r) => [
                  "Constituency (FPTP) seats",
                  r[0],
                  r[1],
                  "",
                  election.label,
                ]),
              ])
            }
          >
            Download CSV
          </button>
        )}
      </div>

      <p className="sub">
        Results of Nepal&rsquo;s House of Representatives elections, as published by the
        Election Commission of Nepal. Party names appear exactly as the Commission
        publishes them, in Nepali. Parties are ordered by votes received.
      </p>

      <div className="controls">
        <div className="segmented" role="group" aria-label="Election">
          {ELECTIONS.map((e) => (
            <button
              key={e.period}
              type="button"
              aria-pressed={e.period === period}
              onClick={() => setPeriod(e.period)}
            >
              {e.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="state error" role="status">
          {error}
        </div>
      )}
      {!error && !votes && <p className="state">Loading election results…</p>}

      {votesOption && (
        <figure className="panel">
          <figcaption>
            <h3>Proportional-representation votes, {election.label}</h3>
            <p>
              {nf.format(totalVotes)} valid votes were counted on the proportional
              ballot. Bars show the {Math.min(BAR_CAP, nationalVotes.length)} parties with
              the most votes; the rest are summed into one bar and listed in full in the
              table below. Labels show each party&rsquo;s share of the proportional vote.
            </p>
          </figcaption>
          <EChart
            option={votesOption}
            height={340}
            ariaLabel={`Horizontal bar chart of proportional-representation votes by party in Nepal's ${election.label} House of Representatives election. ${foldTail(
              nationalVotes,
              BAR_CAP,
            )
              .slice()
              .reverse()
              .map((r) => `${r.party} ${nf.format(r.value)} votes`)
              .join("; ")}.`}
          />
        </figure>
      )}

      {seatsOption && (
        <figure className="panel">
          <figcaption>
            <h3>Constituency seats won, {election.label}</h3>
            <p>
              The 165 seats decided in individual constituencies (first past the post).
              <strong>
                {" "}
                These are not a party&rsquo;s total seats in the 275-member house
              </strong>{" "}
              — the other 110 are allocated proportionally in a separate Commission
              notice, which the portal has not loaded.
            </p>
          </figcaption>
          <EChart
            option={seatsOption}
            height={300}
            ariaLabel={`Horizontal bar chart of constituency seats won by party in Nepal's ${election.label} House of Representatives election. ${foldTail(
              nationalSeats,
              BAR_CAP,
            )
              .slice()
              .reverse()
              .map((r) => `${r.party} ${nf.format(r.value)} seats`)
              .join("; ")}.`}
          />
        </figure>
      )}

      {/* The map. Party picker sits above it, as a filter row. */}
      {geo && selectedParty && (
        <figure className="panel">
          <figcaption>
            <h3>Where each party&rsquo;s support is, {election.label}</h3>
            <p>
              Each district shaded by the selected party&rsquo;s share of that
              district&rsquo;s proportional vote. A share, not a vote count — a count
              would simply shade the biggest districts darkest for every party.{" "}
              <strong>This is not turnout</strong>: the Commission publishes no
              registered-voter figure for these elections, so the portal has no
              denominator to compute turnout from.
            </p>
          </figcaption>

          <div className="controls">
            <label className="field">
              <span>Party</span>
              <select
                value={selectedParty}
                onChange={(e) => setParty(e.target.value)}
                aria-label="Party to map"
              >
                {[...nationalVotes]
                  .sort((a, b) => b.value - a.value)
                  .map((p) => (
                    <option key={p.party} value={p.party}>
                      {p.party}
                    </option>
                  ))}
              </select>
            </label>
          </div>

          <ChoroplethMap
            level="district"
            data={mapData}
            unitCode="PCT"
            onError={(message) => setError(message)}
          />

          {mapRanked.length > 0 && (
            <p className="fiscal-provenance">
              Strongest in {mapRanked[0].name} ({pct.format(mapRanked[0].value)}% of that
              district&rsquo;s proportional vote); weakest in{" "}
              {mapRanked[mapRanked.length - 1].name} (
              {pct.format(mapRanked[mapRanked.length - 1].value)}%). Districts where the
              party received no votes are blank.
            </p>
          )}
        </figure>
      )}

      {nationalVotes.length > 0 && (
        <>
          <button
            type="button"
            className="btn ghost small"
            aria-expanded={showTable}
            onClick={() => setShowTable((v) => !v)}
          >
            {showTable ? "Hide the table" : "Show every party as a table"}
          </button>
          {showTable && (
            <>
              <div className="table-wrap">
                <table className="data">
                  <caption>
                    Every party on the proportional ballot, {election.label}. Source:
                    Election Commission of Nepal.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Party</th>
                      <th scope="col">Proportional votes</th>
                      <th scope="col">Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {voteRows.map((r) => (
                      <tr key={r[0]}>
                        <td>{r[0]}</td>
                        <td>{r[1]}</td>
                        <td>{r[2]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="table-wrap">
                <table className="data">
                  <caption>
                    Constituency seats won, {election.label}. Listed separately from the
                    votes above on purpose — see the note below. Source: Election
                    Commission of Nepal.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Party</th>
                      <th scope="col">Constituency seats</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seatRows.map((r) => (
                      <tr key={r[0]}>
                        <td>{r[0]}</td>
                        <td>{r[1]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p className="fiscal-provenance">
                <strong>Why votes and seats are two tables, not one:</strong> the
                Commission names the same party differently in its two result files.
                In 2079 the seat table says{" "}
                <span lang="ne">नेपाल कम्युनिष्ट पार्टी (एमाले)</span> while the
                proportional table says{" "}
                <span lang="ne">
                  नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)
                </span>
                . Matching them on name would have quietly reported 0 seats for a party
                that won 44. And it cannot be fixed by tidying the names: in 2079 two
                parties contested the proportional ballot under one joint symbol and are
                published as a single row, so there is no seat figure that belongs to it.
                The portal shows both as the Commission published them and joins neither.
              </p>
            </>
          )}
        </>
      )}

      <p className="fiscal-provenance">
        <strong>Source:</strong> Election Commission of Nepal —{" "}
        <a href="https://result.election.gov.np" rel="noreferrer noopener" target="_blank">
          result.election.gov.np
        </a>
        . House of Representatives elections of 2082 BS (polled 5 March 2026) and 2079 BS
        (polled 20 November 2022); polling dates from the Commission&rsquo;s own notices.
        The Commission describes these figures as its consolidated count from the counting
        centres; the certified record is held by the returning officers. No licence is
        stated by the publisher. The portal presents parties in vote order and uses no
        party colours.
      </p>
    </section>
  );
}
