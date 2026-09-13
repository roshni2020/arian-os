"use client";

import { useId } from "react";
import type { Experiment } from "@/lib/api";
import {
  formatComparisonDifference, formatComparisonValue, formatConfigurationValue,
  getComparisonContext, getComparisonMetrics, getConfigurationDifferences, getPrecisionRecallPoints,
  type ComparisonMetric, type PrecisionRecallPoint,
} from "@/lib/experiment-comparison";

export type ExperimentComparisonProps = {
  baseline: Experiment | null;
  candidate: Experiment | null;
  onInspect?: (id: string) => void;
};

function ExperimentHeading({ experiment, label, candidate = false, onInspect }: { experiment: Experiment | null; label: string; candidate?: boolean; onInspect?: (id: string) => void }) {
  return <div className="min-w-0 p-5">
    <p className={`mb-2 flex items-center gap-2 text-xs font-medium ${candidate ? "text-teal" : "text-ink-2"}`}><span aria-hidden="true" className={`h-2 w-2 rounded-full ${candidate ? "bg-teal" : "bg-ink-2"}`} />{label}</p>
    {experiment ? <>
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="break-words text-sm font-medium">{experiment.experiment?.model || "Model not recorded"}</h3>{onInspect && <button type="button" className="btn" onClick={() => onInspect(experiment.id)} aria-label={`Inspect ${label.toLowerCase()} ${experiment.id}`}>Inspect</button>}</div>
      <p className="mono mt-2 break-all text-xs text-ink-2">{experiment.id}</p>
      <p className="mt-2 text-xs text-ink-2">Entry {experiment.iteration} · {experiment.status.replaceAll("_", " ")}</p>
    </> : <p className="text-sm text-ink-2">{candidate ? "Choose an experiment to compare." : "Pin an experiment as the baseline."}</p>}
  </div>;
}

function PrecisionRecallChart({ baseline, candidate, baselinePoints, candidatePoints }: { baseline: Experiment; candidate: Experiment; baselinePoints: PrecisionRecallPoint[]; candidatePoints: PrecisionRecallPoint[] }) {
  const chartId = useId();
  const x = (recall: number) => 52 + recall * 530;
  const y = (precision: number) => 244 - precision * 212;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return <svg viewBox="0 0 610 292" role="img" aria-labelledby={`${chartId}-title ${chartId}-description`} className="block h-auto w-full">
    <title id={`${chartId}-title`}>Precision–recall curves for the baseline and candidate</title>
    <desc id={`${chartId}-description`}>Dashed gray is baseline {baseline.id}. Solid teal is candidate {candidate.id}. Recall is the horizontal axis and precision is the vertical axis, both from zero to one. Recorded points are available in the data tables below.</desc>
    {ticks.map(tick => <g key={tick}>
      <line x1={52} x2={582} y1={y(tick)} y2={y(tick)} stroke="var(--rule)" />
      <text x={42} y={y(tick) + 4} textAnchor="end" fill="var(--ink-2)" fontSize="11">{tick}</text>
      <line x1={x(tick)} x2={x(tick)} y1={244} y2={249} stroke="var(--rule)" />
      <text x={x(tick)} y={264} textAnchor="middle" fill="var(--ink-2)" fontSize="11">{tick}</text>
    </g>)}
    <text x={52} y={17} fill="var(--ink-2)" fontSize="11">Precision</text>
    <text x={317} y={285} fill="var(--ink-2)" textAnchor="middle" fontSize="11">Recall</text>
    <polyline points={baselinePoints.map(point => `${x(point.recall)},${y(point.precision)}`).join(" ")} fill="none" stroke="var(--ink-2)" strokeWidth={2} strokeDasharray="6 4" strokeLinejoin="round" />
    <polyline points={candidatePoints.map(point => `${x(point.recall)},${y(point.precision)}`).join(" ")} fill="none" stroke="var(--teal)" strokeWidth={2.5} strokeLinejoin="round" />
    {baselinePoints.length === 1 && <circle cx={x(baselinePoints[0].recall)} cy={y(baselinePoints[0].precision)} r={4} fill="var(--ink-2)" />}
    {candidatePoints.length === 1 && <circle cx={x(candidatePoints[0].recall)} cy={y(candidatePoints[0].precision)} r={4} fill="var(--teal)" />}
  </svg>;
}

function CurveData({ label, points }: { label: string; points: PrecisionRecallPoint[] }) {
  return <div className="min-w-0">
    <h4 className="mb-2 text-xs font-medium">{label} · {points.length} recorded points</h4>
    {points.length ? <div className="max-h-64 overflow-auto rounded-md border border-rule"><table className="w-full text-right text-xs tabular-nums"><caption className="sr-only">Recorded precision and recall values for the {label.toLowerCase()}</caption><thead className="sticky top-0 bg-paper text-ink-2"><tr><th scope="col" className="px-3 py-2 font-normal">Point</th><th scope="col" className="px-3 py-2 font-normal">Recall</th><th scope="col" className="px-3 py-2 font-normal">Precision</th></tr></thead><tbody className="divide-y divide-rule">{points.map((point, i) => <tr key={i}><th scope="row" className="px-3 py-2 font-normal text-ink-2">{i + 1}</th><td className="px-3 py-2">{point.recall.toFixed(6)}</td><td className="px-3 py-2">{point.precision.toFixed(6)}</td></tr>)}</tbody></table></div> : <p className="text-sm text-ink-2">No precision–recall curve was recorded.</p>}
  </div>;
}

function MetricBars({ metric }: { metric: ComparisonMetric }) {
  const scoreScale = metric.unit === "score";
  const values = [{ label: "Baseline", value: metric.baseline, candidate: false }, { label: "Candidate", value: metric.candidate, candidate: true }];
  const max = scoreScale ? 1 : Math.max(metric.baseline ?? 0, metric.candidate ?? 0);
  const valid = values.every(({ value }) => value !== null && value >= 0 && (!scoreScale || value <= 1));
  return <div className="min-w-0">
    <h4 className="mb-4 text-sm font-medium">{scoreScale ? "Average precision" : "Observed runtime"}<span className="ml-2 text-xs font-normal text-ink-2">{scoreScale ? "0–1 scale" : "seconds"}</span></h4>
    {valid ? <div className="space-y-3">{values.map(({ label, value, candidate }) => <div key={label}>
      <div className="mb-1.5 flex items-center justify-between gap-3 text-xs"><span className="text-ink-2">{label}</span><span className="tabular-nums">{formatComparisonValue(value, metric.unit)}</span></div>
      <div className="h-2 overflow-hidden rounded-sm bg-paper" aria-hidden="true"><div className={`h-full rounded-sm ${candidate ? "bg-teal" : "bg-ink-2"}`} style={{ width: `${max > 0 ? ((value ?? 0) / max) * 100 : 0}%` }} /></div>
    </div>)}</div> : <p className="text-sm text-ink-2">Both recorded values are needed for this view.</p>}
  </div>;
}

export default function ExperimentComparison({ baseline, candidate, onInspect }: ExperimentComparisonProps) {
  const context = getComparisonContext(baseline, candidate);
  const metrics = getComparisonMetrics(baseline, candidate);
  const differences = getConfigurationDifferences(baseline, candidate);
  const baselineCurve = getPrecisionRecallPoints(baseline);
  const candidateCurve = getPrecisionRecallPoints(candidate);
  const threshold = metrics.find(metric => metric.id === "threshold")!;
  const ap = metrics.find(metric => metric.id === "ap")!;
  const runtime = metrics.find(metric => metric.id === "runtime")!;

  return <div className="space-y-5">
    <section className="surface overflow-hidden" aria-label="Selected experiments">
      <div className="grid divide-y divide-rule sm:grid-cols-2 sm:divide-x sm:divide-y-0"><ExperimentHeading experiment={baseline} label="Pinned baseline" onInspect={onInspect} /><ExperimentHeading experiment={candidate} label="Candidate" candidate onInspect={onInspect} /></div>
    </section>

    {!baseline || !candidate ? <div className="surface p-6 text-sm text-ink-2" role="status">Select a baseline and a candidate to inspect their metrics, configuration changes and precision–recall curves.</div> : <>
      <section className="surface p-5" aria-label="Comparison context">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="section-title">Evaluation context</h2><span className={`status-badge ${context.comparable ? "success" : "warning"}`}>{context.comparable ? "Matching context" : context.status === "mismatch" ? "Contexts differ" : "Context incomplete"}</span></div>
        <p className="mt-3 text-sm leading-6 text-ink-2">{context.comparable ? "These runs share a session, score kind, split, seed and sample counts. Differences describe the recorded runs; they do not establish a benchmark claim or statistical significance." : "Recorded values are shown side by side. Differences and chart overlays are unavailable until the evaluation contexts are known and match."}</p>
        {context.reasons.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs leading-5 text-ink-2">{context.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
        <details className="mt-4"><summary className="cursor-pointer text-xs font-medium">Context fields</summary><div className="mt-3 overflow-x-auto"><table className="w-full min-w-[480px] text-left text-xs"><caption className="sr-only">Evaluation context for both experiments</caption><thead className="text-ink-2"><tr><th scope="col" className="py-2 pr-4 font-normal">Field</th><th scope="col" className="py-2 pr-4 font-normal">Baseline</th><th scope="col" className="py-2 pr-4 font-normal">Candidate</th><th scope="col" className="py-2 font-normal">Match</th></tr></thead><tbody className="divide-y divide-rule">{context.checks.map(check => <tr key={check.key}><th scope="row" className="py-2 pr-4 font-medium">{check.label}</th><td className="max-w-56 break-all py-2 pr-4">{check.baseline ?? "Not recorded"}</td><td className="max-w-56 break-all py-2 pr-4">{check.candidate ?? "Not recorded"}</td><td className="py-2 text-ink-2">{check.status === "match" ? "Yes" : check.status === "mismatch" ? "No" : "Unknown"}</td></tr>)}</tbody></table></div></details>
      </section>

      <section className="surface overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-5 py-4"><h2 className="section-title">Metrics</h2><p className="text-xs text-ink-2">Difference = candidate − baseline</p></div>
        {(!baseline.result || !candidate.result) && <p className="border-b border-rule px-5 py-3 text-sm text-ink-2" role="status">{!baseline.result && !candidate.result ? "Neither experiment has a recorded result yet." : !baseline.result ? "The baseline has no recorded result yet." : "The candidate has no recorded result yet."}</p>}
        <div className="overflow-x-auto"><table className="w-full min-w-[570px] text-right text-sm tabular-nums"><caption className="sr-only">Baseline and candidate recorded metrics with candidate minus baseline differences where evaluation context matches</caption><thead className="bg-paper text-xs text-ink-2"><tr><th scope="col" className="px-5 py-3 text-left font-normal">Metric</th><th scope="col" className="px-4 py-3 font-normal">Baseline</th><th scope="col" className="px-4 py-3 font-normal">Candidate</th><th scope="col" className="px-5 py-3 font-normal">Difference</th></tr></thead><tbody className="divide-y divide-rule">{metrics.map(metric => <tr key={metric.id} className={metric.id === "ap" ? "bg-teal/5" : ""}><th scope="row" className="px-5 py-3 text-left font-medium">{metric.label}{metric.thresholded && <span className="ml-1 text-ink-2" aria-label="at each experiment's own threshold">*</span>}</th><td className="px-4 py-3">{formatComparisonValue(metric.baseline, metric.unit)}</td><td className="px-4 py-3">{formatComparisonValue(metric.candidate, metric.unit)}</td><td className="px-5 py-3"><span>{formatComparisonDifference(metric.difference, metric.unit)}</span>{metric.difference !== null && metric.difference !== 0 && <span className="ml-2 text-xs text-ink-2">{metric.id === "runtime" ? metric.difference < 0 ? "less time" : "more time" : metric.difference > 0 ? "higher" : "lower"}</span>}</td></tr>)}</tbody></table></div>
        <div className="space-y-2 border-t border-rule px-5 py-4 text-xs leading-5 text-ink-2"><p>* Precision, recall and F1 use each experiment’s own best-F1 threshold: baseline {formatComparisonValue(threshold.baseline, "score")}; candidate {formatComparisonValue(threshold.candidate, "score")}. These are not comparisons at a shared threshold.</p><p>AP and AUROC are threshold-free. Higher training AP or more features is not automatically better; runtime is an observed duration, without a verified hardware match.</p></div>
      </section>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <section className="surface min-w-0 overflow-hidden">
          <div className="border-b border-rule px-5 py-4"><h2 className="section-title">Precision–recall</h2></div>
          <div className="p-5">
            <div className="mb-4 flex flex-wrap gap-5 text-xs text-ink-2"><span className="flex items-center gap-2"><span aria-hidden="true" className="w-5 border-t-2 border-dashed border-ink-2" />Baseline</span><span className="flex items-center gap-2"><span aria-hidden="true" className="w-5 border-t-2 border-teal" />Candidate</span></div>
            {context.comparable && baselineCurve.points.length && candidateCurve.points.length ? <PrecisionRecallChart baseline={baseline} candidate={candidate} baselinePoints={baselineCurve.points} candidatePoints={candidateCurve.points} /> : <p className="py-8 text-sm leading-6 text-ink-2">{!context.comparable ? "The curve overlay requires matching evaluation contexts." : "A recorded precision–recall curve is needed for both experiments. No curve is inferred from the AP score."}</p>}
            {(baselineCurve.rejected > 0 || candidateCurve.rejected > 0) && <p className="mt-3 text-xs text-ink-2">Invalid or out-of-range curve points excluded: {baselineCurve.rejected} baseline; {candidateCurve.rejected} candidate.</p>}
            <details className="mt-4 border-t border-rule pt-4"><summary className="cursor-pointer text-sm font-medium">Recorded curve data</summary><div className="mt-4 grid gap-4 sm:grid-cols-2"><CurveData label="Baseline" points={baselineCurve.points} /><CurveData label="Candidate" points={candidateCurve.points} /></div></details>
          </div>
        </section>

        <section className="surface min-w-0 overflow-hidden">
          <div className="border-b border-rule px-5 py-4"><h2 className="section-title">AP & runtime</h2></div>
          {context.comparable ? <div className="space-y-7 p-5"><MetricBars metric={ap} /><MetricBars metric={runtime} /><p className="text-xs leading-5 text-ink-2">AP bars share the 0–1 scale. Runtime bars share a scale ending at the longer recorded duration. Scores and durations use different units.</p></div> : <p className="p-5 text-sm leading-6 text-ink-2">This view becomes available when the evaluation contexts match. Recorded AP and runtime remain in the metrics table.</p>}
        </section>
      </div>

      <section className="surface overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-5 py-4"><h2 className="section-title">Configuration changes</h2><span className="text-xs text-ink-2">{differences.length} changed {differences.length === 1 ? "field" : "fields"}</span></div>
        {!differences.length ? <p className="p-5 text-sm text-ink-2">The recorded experiment configurations are identical.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[530px] text-left text-sm"><caption className="sr-only">Only configuration fields that changed between the baseline and candidate, including nested hyperparameters</caption><thead className="bg-paper text-xs text-ink-2"><tr><th scope="col" className="px-5 py-3 font-normal">Field</th><th scope="col" className="px-5 py-3 font-normal">Baseline</th><th scope="col" className="px-5 py-3 font-normal">Candidate</th></tr></thead><tbody className="divide-y divide-rule">{differences.map(difference => <tr key={difference.path}><th scope="row" className="mono max-w-64 break-words px-5 py-3 text-xs font-normal">{difference.path}</th><td className="mono max-w-80 break-words px-5 py-3 text-xs">{formatConfigurationValue(difference.baseline)}</td><td className="mono max-w-80 break-words px-5 py-3 text-xs">{formatConfigurationValue(difference.candidate)}</td></tr>)}</tbody></table></div>}
      </section>
    </>}
  </div>;
}
