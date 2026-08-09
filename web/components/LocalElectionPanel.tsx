"use client";

// The 2079 local election (ECN.S4 extension) — the layer of government closest
// to people, and the one hardest to find results for anywhere.
//
// Nepal's local election of 13 May 2022 filled **35,221 seats** across 753 local
// governments: mayors and rural-municipality chairs, their deputies, and four
// kinds of ward-level member. This panel shows who won them.
//
// WHAT THE SOURCE WITHHOLDS, said plainly rather than hidden:
// The Commission publishes only the **four largest parties per office plus one
// combined "अन्य" (Other) row**. The totals are complete — they reconcile to the
// seat counts — but individual small parties and independents cannot be
// separated at this level. There is no fuller file; it was searched for.
//
// SEATS WON IS NOT SEATS AVAILABLE. 123 Dalit woman member seats and 1 woman
// member seat were never filled. That is a real published outcome about Nepali
// local democracy, so the panel surfaces it instead of quietly showing a
// smaller total.
//
// Dataviz method: one office at a time, so this is a SINGLE series across named
// parties -> one hue, no party ever coloured, ordered by seats won. Stacked
// "share of the office" would invite reading coalition arithmetic the source
// does not support. Table + CSV below.

import { useEffect, useMemo, useState } from "react";
import EChart, { CHART_INK, TOOLTIP_STYLE, type ChartOption } from "@/components/EChart";
import { ApiError, fetchSeries, type DataResponse } from "@/lib/api";
import { downloadCsv } from "@/lib/csv";

const LOCAL_HUE = "#008300"; // --series-1 green: the local-government measure

/** The offices, in the order the Commission's own summary page lists them, with
 *  the seat count each office has (also from that page). English labels come
 *  from the Commission's own file names, not from a translation of ours. */
const OFFICES: { ne: string; en: string; seats: number }[] = [
  { ne: "प्रमुख", en: "Mayor (municipality)", seats: 293 },
  { ne: "अध्यक्ष", en: "Chair (rural municipality)", seats: 460 },
  { ne: "उपप्रमुख", en: "Deputy mayor", seats: 293 },
  { ne: "उपाध्यक्ष", en: "Deputy chair", seats: 460 },
  { ne: "वडा अध्यक्ष", en: "Ward chair", seats: 6743 },
  { ne: "महिला सदस्य", en: "Woman member", seats: 6743 },
  { ne: "दलित महिला सदस्य", en: "Dalit woman member", seats: 6743 },
  { ne: "सदस्य", en: "Member", seats: 13486 },
];

const TOTAL_SEATS = OFFICES.reduce((sum, o) => sum + o.seats, 0);

const nf = new Intl.NumberFormat("en-US");
const pct = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

interface Row {
  party: string;
  seats: number;
}

export default function LocalElectionPanel() {
  const [data, setData] = useState<DataResponse | null>(null);
  const [office, setOffice] = useState<string>(OFFICES[0].ne);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    let live = true;
    fetchSeries("ELECTION_LOCAL_SEATS", "NP")
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e: unknown) => {
        if (live) {
          setError(
            e instanceof ApiError ? e.message : "Could not load the local election results.",
          );
        }
      });
    return () => {
      live = false;
    };
  }, []);

  /** Every office's rows, keyed by the Nepali office name. */
  const byOffice = useMemo(() => {
    const out = new Map<string, Row[]>();
    for (const o of data?.observations ?? []) {
      const party = o.breakdowns?.party;
      const post = o.breakdowns?.post;
      if (!party || !post) continue;
      const rows = out.get(post) ?? [];
      rows.push({ party, seats: o.value });
      out.set(post, rows);
    }
    return out;
  }, [data]);

  const spec = OFFICES.find((o) => o.ne === office) ?? OFFICES[0];
  const rows = useMemo(
    () => [...(byOffice.get(office) ?? [])].sort((a, b) => b.seats - a.seats),
    [byOffice, office],
  );
  const won = rows.reduce((sum, r) => sum + r.seats, 0);
  const unfilled = spec.seats - won;

  /** Seats across all eight offices — but ONLY for parties the Commission
   *  itemises in every one of them.
   *
   *  This is the trap in the "top four plus Other" format. A party listed for
   *  mayors but not for members has its member seats folded into अन्य, so
   *  adding up the rows it does appear in produces a total that is far too
   *  small and looks authoritative. In 2022 one party is itemised for a single
   *  office: summing its rows would report 12 seats nationally for a party that
   *  in fact won more. So a cross-office total is offered only where every
   *  office itemises the party, and the rest are named as uncountable. */
  const { overall, partial } = useMemo(() => {
    const totals = new Map<string, number>();
    const offices = new Map<string, number>();
    for (const rowset of byOffice.values()) {
      for (const r of rowset) {
        totals.set(r.party, (totals.get(r.party) ?? 0) + r.seats);
        offices.set(r.party, (offices.get(r.party) ?? 0) + 1);
      }
    }
    const complete: Row[] = [];
    const incomplete: string[] = [];
    for (const [party, seats] of totals) {
      if (offices.get(party) === byOffice.size && byOffice.size === OFFICES.length) {
        complete.push({ party, seats });
      } else {
        incomplete.push(party);
      }
    }
    complete.sort((a, b) => b.seats - a.seats);
    return { overall: complete, partial: incomplete };
  }, [byOffice]);

  const totalWon = overall.reduce((sum, r) => sum + r.seats, 0);

  const option = useMemo<ChartOption | null>(() => {
    if (rows.length === 0) return null;
    const ordered = [...rows].reverse(); // largest at the top
    return {
      grid: { left: 8, right: 96, top: 8, bottom: 8, containLabel: true },
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
        data: ordered.map((r) => r.party),
        axisLabel: {
          color: CHART_INK.text,
          fontSize: 12,
          width: 300,
          overflow: "break",
          lineHeight: 14,
        },
        axisLine: { lineStyle: { color: CHART_INK.axisLine } },
        axisTick: { show: false },
      },
      series: [
        {
          type: "bar",
          name: "Seats",
          data: ordered.map((r) => r.seats),
          barMaxWidth: 18,
          barCategoryGap: "40%",
          itemStyle: { color: LOCAL_HUE, borderRadius: [0, 4, 4, 0] },
          label: {
            show: true,
            position: "right",
            color: CHART_INK.secondary,
            fontSize: 11,
            formatter: (p) =>
              `${nf.format(p.value as number)}  (${pct.format(((p.value as number) / spec.seats) * 100)}%)`,
          },
        },
      ],
    };
  }, [rows, spec.seats]);

  return (
    <section className="fiscal-panel" aria-labelledby="local-election">
      <div className="band-head">
        <h2 id="local-election">Who runs local government</h2>
        {data && (
          <button
            type="button"
            className="btn ghost small"
            onClick={() =>
              downloadCsv("nepal-local-election-2022-seats.csv", [
                ["Office (as published)", "Office (English)", "Party", "Seats won", "Seats in office"],
                ...OFFICES.flatMap((o) =>
                  [...(byOffice.get(o.ne) ?? [])]
                    .sort((a, b) => b.seats - a.seats)
                    .map((r) => [o.ne, o.en, r.party, String(r.seats), String(o.seats)]),
                ),
              ])
            }
          >
            Download CSV
          </button>
        )}
      </div>

      <p className="sub">
        Nepal&rsquo;s local election of <strong>13 May 2022</strong> filled{" "}
        <strong>{nf.format(TOTAL_SEATS)} seats</strong> across 753 local governments — the
        tier of government closest to daily life. Pick an office to see who won it.
      </p>

      {error && (
        <div className="state error" role="status">
          {error}
        </div>
      )}
      {!error && !data && <p className="state">Loading local results…</p>}

      {data && (
        <>
          <div className="controls">
            <label className="field">
              <span>Office</span>
              <select value={office} onChange={(e) => setOffice(e.target.value)}>
                {OFFICES.map((o) => (
                  <option key={o.ne} value={o.ne}>
                    {o.en} — {o.ne}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {option && (
            <figure className="panel">
              <figcaption>
                <h3>
                  {spec.en} · {spec.ne}
                </h3>
                <p>
                  {nf.format(spec.seats)} of these seats were contested across Nepal.{" "}
                  {unfilled > 0 ? (
                    <>
                      <strong>{nf.format(unfilled)} were never filled</strong> — no one was
                      elected to them — so the bars below add up to {nf.format(won)}, not{" "}
                      {nf.format(spec.seats)}.
                    </>
                  ) : (
                    <>All {nf.format(won)} were filled.</>
                  )}{" "}
                  Percentages are of the seats the office has.
                </p>
              </figcaption>
              <EChart
                option={option}
                height={280}
                ariaLabel={`Horizontal bar chart of ${spec.en} seats won by party in Nepal's 2022 local election. ${rows
                  .map((r) => `${r.party} ${nf.format(r.seats)}`)
                  .join("; ")}.`}
              />
            </figure>
          )}

          {overall.length > 0 && (
            <p className="fiscal-provenance">
              <strong>Across all eight offices:</strong>{" "}
              {overall
                .map(
                  (r) =>
                    `${r.party} ${nf.format(r.seats)} (${pct.format((r.seats / totalWon) * 100)}%)`,
                )
                .join(" · ")}
              .{" "}
              {partial.length > 0 && (
                <>
                  These are the only parties the Commission itemises for{" "}
                  <em>every</em> office, so they are the only ones that can honestly be
                  totalled. {partial.length === 1 ? "One other party" : `${partial.length} other parties`}{" "}
                  appear for some offices and not others — their remaining seats sit
                  inside <span lang="ne">अन्य</span>, so no national total is shown for
                  them. Use the office picker above to see them where they are listed.
                </>
              )}
            </p>
          )}

          <button
            type="button"
            className="btn ghost small"
            aria-expanded={showTable}
            onClick={() => setShowTable((v) => !v)}
          >
            {showTable ? "Hide the table" : "Show every office as a table"}
          </button>

          {showTable && (
            <div className="table-wrap">
              <table className="data">
                <caption>
                  Local government seats won, by office and party, Nepal 2022. Source:
                  Election Commission of Nepal.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Office</th>
                    <th scope="col">Party</th>
                    <th scope="col">Seats won</th>
                    <th scope="col">Seats in office</th>
                  </tr>
                </thead>
                <tbody>
                  {OFFICES.flatMap((o) =>
                    [...(byOffice.get(o.ne) ?? [])]
                      .sort((a, b) => b.seats - a.seats)
                      .map((r) => (
                        <tr key={`${o.ne}-${r.party}`}>
                          <td>
                            {o.en}
                            <br />
                            <span className="muted">{o.ne}</span>
                          </td>
                          <td>{r.party}</td>
                          <td>{nf.format(r.seats)}</td>
                          <td>{nf.format(o.seats)}</td>
                        </tr>
                      )),
                  )}
                </tbody>
              </table>
            </div>
          )}

          <p className="fiscal-provenance">
            <strong>What this can and cannot tell you.</strong> The Commission publishes
            local results as the <strong>four largest parties per office plus one combined{" "}
            <span lang="ne">अन्य</span> (&ldquo;Other&rdquo;) row</strong>. So the totals here
            are complete, but individual smaller parties and independents cannot be
            separated out — they are inside &ldquo;Other&rdquo;. There is no fuller file;
            it was searched for. <strong>Source:</strong> Election Commission of Nepal —{" "}
            <a
              href="https://result.election.gov.np"
              rel="noreferrer noopener"
              target="_blank"
            >
              result.election.gov.np
            </a>
            . Local election of 2079 BS, polled 2079-01-30 BS = 13 May 2022; the date is
            from the Commission&rsquo;s own sealed election programme. Party and office
            names appear exactly as published, in Nepali. No party is given a colour.
          </p>
        </>
      )}
    </section>
  );
}
