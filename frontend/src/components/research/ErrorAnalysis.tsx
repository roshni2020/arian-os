"use client";

import { useState } from "react";
import type { Experiment } from "@/lib/api";
import { getComparisonContext } from "@/lib/experiment-comparison";
import { alignErrorGroups, errorDimensions, errorSummary, filterErrorGroups, sortErrorGroups, type ErrorGroup, type ErrorGroupRow, type ErrorSort } from "@/lib/error-analysis";

export type ErrorAnalysisProps = {
  baseline: Experiment | null;
  candidate: Experiment | null;
  onInspect?: (id: string) => void;
  onPropose?: (dimension: string, group: string) => void;
};

function number(value: number | null) { return value === null ? "—" : value.toLocaleString("en-US"); }
function percent(value: number | null) { return value === null ? "—" : `${(value * 100).toFixed(1)}%`; }
function dimensionLabel(value: string) { return value.replace(/^by_/, "").replaceAll("_", " "); }

function Change({ value, recall = false }: { value: number | null; recall?: boolean }) {
  if (value === null) return <span className="text-ink-2" aria-label="Change unavailable">—</span>;
  const improvement = recall ? value > 0 : value < 0;
  const text = recall ? `${Math.abs(value * 100).toFixed(1)} pp` : number(Math.abs(value));
  return <span className={value === 0 ? "text-ink-2" : improvement ? "text-teal" : "text-rust"}>{value > 0 ? "+" : value < 0 ? "−" : ""}{text}</span>;
}

function ConfusionSummary({ experiment, label, onInspect }: { experiment: Experiment; label: string; onInspect?: (id: string) => void }) {
  const summary = errorSummary(experiment);
  return <section className="surface min-w-0 p-5" aria-label={`${label} confusion matrix`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h3 className="section-title">{label}</h3><p className="mt-1 text-xs text-ink-2">{experiment.id} · {experiment.result?.split || "Split not recorded"}</p></div>
      {onInspect && <button type="button" className="text-xs font-medium text-teal hover:underline" onClick={() => onInspect(experiment.id)}>Inspect run</button>}
    </div>
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[280px] border-separate border-spacing-1 text-sm">
        <caption className="sr-only">{label}: actual classes in rows and predicted classes in columns.</caption>
        <thead><tr><th scope="col"><span className="sr-only">Actual class</span></th><th scope="col" className="pb-2 text-center text-xs font-normal text-ink-2">Predicted positive</th><th scope="col" className="pb-2 text-center text-xs font-normal text-ink-2">Predicted negative</th></tr></thead>
        <tbody>
          <tr><th scope="row" className="pr-3 text-left text-xs font-normal text-ink-2">Actual positive</th><td className="rounded bg-teal/5 px-3 py-3 text-center"><span className="block text-base font-medium tabular-nums">{number(summary.tp)}</span><span className="text-[11px] text-ink-2">True positives</span></td><td className="rounded bg-paper-2 px-3 py-3 text-center"><span className="block text-base font-medium tabular-nums">{number(summary.fn)}</span><span className="text-[11px] text-ink-2">False negatives</span></td></tr>
          <tr><th scope="row" className="pr-3 text-left text-xs font-normal text-ink-2">Actual negative</th><td className="rounded bg-paper-2 px-3 py-3 text-center"><span className="block text-base font-medium tabular-nums">{number(summary.fp)}</span><span className="text-[11px] text-ink-2">False positives</span></td><td className="rounded bg-teal/5 px-3 py-3 text-center"><span className="block text-base font-medium tabular-nums">{number(summary.tn)}</span><span className="text-[11px] text-ink-2">True negatives</span></td></tr>
        </tbody>
      </table>
    </div>
    <dl className="mt-4 flex flex-wrap justify-between gap-3 border-t border-rule pt-4 text-xs">
      <div><dt className="text-ink-2">Best-F1 threshold</dt><dd className="mt-1 font-medium tabular-nums">{summary.threshold === null ? "Not recorded" : summary.threshold.toFixed(4)}</dd></div>
      <div className="text-right"><dt className="text-ink-2">Evaluation samples</dt><dd className="mt-1 font-medium tabular-nums">{number(summary.observations)}</dd></div>
    </dl>
    {summary.countMismatch && <p className="mt-3 text-xs text-rust">Confusion counts do not sum to the recorded evaluation sample count.</p>}
    {!experiment.result && <p className="mt-3 text-xs text-ink-2">This experiment has no recorded result yet.</p>}
  </section>;
}

function GroupLabel({ row, paired, onPropose }: { row: ErrorGroupRow; paired: boolean; onPropose?: () => void }) {
  return <th scope="row" className="max-w-[220px] min-w-[160px] px-4 py-3 text-left font-normal">
    <span className="break-words font-medium">{row.group || "(empty label)"}</span>
    {onPropose && <button className="mt-2 block text-xs text-teal hover:underline" onClick={onPropose}>Investigate with ARIA</button>}
    {(row.baseline?.smallGroup || row.candidate?.smallGroup) && <span className="mt-1 block text-[11px] text-rust">Small group</span>}
    {paired && !row.comparable && <span className="mt-1 block text-[11px] leading-4 text-ink-2" title={row.reasons.join(" ")}>{!row.baseline ? "Not recorded in baseline" : !row.candidate ? "Not recorded in candidate" : "Not comparable"}</span>}
  </th>;
}

function GroupCells({ group, paired = false }: { group: ErrorGroup | null; paired?: boolean }) {
  return <>
    <td className="px-3 py-3 text-right tabular-nums">{paired ? <><span>{number(group?.count ?? null)}</span><span className="mt-0.5 block text-[11px] text-ink-2">{number(group?.positives ?? null)} positive</span></> : number(group?.count ?? null)}</td>
    {!paired && <td className="px-3 py-3 text-right tabular-nums">{number(group?.positives ?? null)}</td>}
    <td className="px-3 py-3 text-right tabular-nums">{number(group?.falseNegatives ?? null)}</td>
    <td className="px-3 py-3 text-right tabular-nums">{number(group?.falsePositives ?? null)}</td>
    <td className="px-3 py-3 text-right tabular-nums">{percent(group?.recall ?? null)}</td>
  </>;
}

const sorts: { value: ErrorSort; label: string; pairOnly?: boolean }[] = [
  { value: "falseNegatives", label: "False negatives (FN)" },
  { value: "falsePositives", label: "False positives (FP)" },
  { value: "recall", label: "Recall" },
  { value: "count", label: "Sample count" },
  { value: "falseNegativesChange", label: "Change in FN", pairOnly: true },
  { value: "falsePositivesChange", label: "Change in FP", pairOnly: true },
  { value: "recallChange", label: "Change in recall", pairOnly: true },
  { value: "group", label: "Group name" },
];

export default function ErrorAnalysis({ baseline, candidate, onInspect, onPropose }: ErrorAnalysisProps) {
  const [dimension, setDimension] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<ErrorSort>("falseNegatives");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const paired = Boolean(baseline && candidate);
  const dimensions = errorDimensions(baseline, candidate);
  const selectedDimension = dimensions.includes(dimension) ? dimension : dimensions[0] ?? "";
  const activeSort = !paired && sort.endsWith("Change") ? "falseNegatives" : sort;
  const context = getComparisonContext(baseline, candidate);
  const allRows = alignErrorGroups(baseline, candidate, selectedDimension);
  const rows = sortErrorGroups(filterErrorGroups(allRows, query), activeSort, direction, candidate ? "candidate" : "baseline");
  const baseSummary = errorSummary(baseline);
  const candidateSummary = errorSummary(candidate);
  const thresholdsDiffer = paired && baseSummary.threshold !== null && candidateSummary.threshold !== null && baseSummary.threshold !== candidateSummary.threshold;
  const unmatched = allRows.filter(row => !row.comparable).length;

  if (!baseline && !candidate) return <div className="surface px-6 py-12 text-center"><h2 className="section-title">Explore where a model makes mistakes</h2><p className="mt-2 text-sm text-ink-2">Select an experiment above to inspect its errors, or select two to compare recorded groups.</p></div>;

  return <div className="space-y-5">
    <div className={`grid gap-5 ${paired ? "xl:grid-cols-2" : "max-w-2xl"}`}>
      {baseline && <ConfusionSummary experiment={baseline} label={paired ? "Baseline" : "Selected experiment"} onInspect={onInspect} />}
      {candidate && <ConfusionSummary experiment={candidate} label={paired ? "Candidate" : "Selected experiment"} onInspect={onInspect} />}
    </div>

    <div className="text-xs leading-5 text-ink-2">
      <p><span className="font-medium text-ink">{thresholdsDiffer ? "Different thresholds. " : "Thresholded errors. "}</span>FN and FP counts use each run’s own best-F1 validation threshold. Changes reflect both the model and its threshold, not performance at a common threshold. AUPRC is threshold-free.</p>
      {paired && !context.comparable && <div className="mt-3 rounded-lg border border-rule bg-paper-2 p-4" role="status"><p className="font-medium text-ink">These runs cannot be compared directly.</p><ul className="mt-1 list-disc pl-4">{context.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul><p className="mt-2">Recorded values remain visible; group changes are unavailable.</p></div>}
    </div>

    <section className="surface min-w-0 overflow-hidden" aria-labelledby="error-groups-heading">
      <div className="border-b border-rule p-5">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="error-groups-heading" className="section-title">Errors by group</h2>{allRows.length > 0 && <span className="text-xs text-ink-2">{rows.length} of {allRows.length} recorded groups</span>}</div>
        <p className="mt-2 text-xs leading-5 text-ink-2">Every recorded group is available here. Source summaries may omit groups; missing entries are unknown, not zero.</p>
        {dimensions.length > 0 && <div className="mt-5 flex flex-wrap items-end gap-3">
          <label className="flex min-w-[180px] flex-col gap-1.5 text-xs text-ink-2">Dimension<select className="form-control capitalize" value={selectedDimension} onChange={event => { setDimension(event.target.value); setQuery(""); }}>{dimensions.map(name => <option key={name} value={name}>{dimensionLabel(name)}</option>)}</select></label>
          <label className="flex min-w-[180px] flex-1 flex-col gap-1.5 text-xs text-ink-2">Find a group<input type="search" className="form-control" placeholder="Search group names" value={query} onChange={event => setQuery(event.target.value)} /></label>
          <label className="flex flex-col gap-1.5 text-xs text-ink-2">Sort by<select className="form-control" value={activeSort} onChange={event => setSort(event.target.value as ErrorSort)}>{sorts.filter(option => paired || !option.pairOnly).map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          <label className="flex flex-col gap-1.5 text-xs text-ink-2">Order<select className="form-control" value={direction} onChange={event => setDirection(event.target.value as "asc" | "desc")}><option value="desc">{activeSort === "group" ? "Z to A" : "Highest first"}</option><option value="asc">{activeSort === "group" ? "A to Z" : "Lowest first"}</option></select></label>
        </div>}
      </div>

      {allRows.length === 0 ? <p className="px-5 py-10 text-sm text-ink-2">No group-level error data was recorded for the selected experiment{paired ? "s" : ""}.</p>
        : rows.length === 0 ? <p className="px-5 py-10 text-sm text-ink-2">No groups match “{query}”. Clear the search to show all recorded groups.</p>
        : <div className="overflow-x-auto" role="region" aria-label="Group error data, horizontally scrollable" tabIndex={0}>
          <table className={`w-full border-collapse text-xs ${paired ? "min-w-[1120px]" : "min-w-[640px]"}`}>
            <caption className="sr-only">Errors by {dimensionLabel(selectedDimension)}. {paired ? "Baseline and candidate are aligned by group label. Changes are candidate minus baseline." : "Counts and recall for the selected experiment."} A dash means unavailable.</caption>
            <thead className="bg-paper-2 text-ink-2">
              {paired ? <>
                <tr className="border-b border-rule"><th scope="col" rowSpan={2} className="px-4 py-3 text-left font-medium">Group</th><th scope="colgroup" colSpan={4} className="border-l border-rule px-3 py-3 text-center font-medium">Baseline</th><th scope="colgroup" colSpan={4} className="border-l border-rule px-3 py-3 text-center font-medium">Candidate</th><th scope="colgroup" colSpan={3} className="border-l border-rule px-3 py-3 text-center font-medium">Change · candidate − baseline</th></tr>
                <tr>{["baseline", "candidate"].map(run => ["Samples / positive", "FN", "FP", "Recall"].map(label => <th key={`${run}-${label}`} scope="col" className="px-3 py-3 text-right font-normal">{label}</th>))}<th scope="col" className="px-3 py-3 text-right font-normal">Δ FN</th><th scope="col" className="px-3 py-3 text-right font-normal">Δ FP</th><th scope="col" className="px-3 py-3 text-right font-normal">Δ Recall</th></tr>
              </> : <tr>{["Group", "Samples", "Positive", "FN", "FP", "Recall"].map((label, index) => <th key={label} scope="col" className={`px-4 py-3 font-normal ${index === 0 ? "text-left" : "text-right"}`}>{label}</th>)}</tr>}
            </thead>
            <tbody className="divide-y divide-rule">{rows.map(row => <tr key={row.group} className="hover:bg-paper-2/60"><GroupLabel row={row} paired={paired} onPropose={onPropose ? () => onPropose(selectedDimension, row.group) : undefined} />{paired ? <><GroupCells group={row.baseline} paired /><GroupCells group={row.candidate} paired /><td className="px-3 py-3 text-right tabular-nums"><Change value={row.changes.falseNegatives} /></td><td className="px-3 py-3 text-right tabular-nums"><Change value={row.changes.falsePositives} /></td><td className="px-3 py-3 text-right tabular-nums"><Change value={row.changes.recall} recall /></td></> : <GroupCells group={candidate ? row.candidate : row.baseline} />}</tr>)}</tbody>
          </table>
        </div>}

      {allRows.length > 0 && <div className="space-y-1 border-t border-rule bg-paper-2 px-5 py-4 text-xs leading-5 text-ink-2">
        <p>FN = missed positives. FP = false alarms. Recall is unavailable when there are no positive samples.</p>
        <p>Small groups have fewer than 30 samples or were flagged by the source; their rates can be unstable.</p>
        {paired && <><p>Sorting uses candidate values unless you select a change. Negative FN/FP changes mean fewer errors; positive recall changes mean higher recall.</p>{unmatched > 0 && <p>{unmatched} group{unmatched === 1 ? " has" : "s have"} no comparable change. Missing groups, different sample or positive counts, and unmatched run protocols are not compared.</p>}</>}
      </div>}
    </section>
  </div>;
}
