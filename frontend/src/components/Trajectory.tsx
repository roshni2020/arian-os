"use client";
import { HistoryRow } from "@/lib/api";

type Props = { history: HistoryRow[]; target: number; selected?: string | null; onSelect?: (id: string) => void; finalTest?: number | null; visibleCount?: number };

function shortChange(r: HistoryRow): string {
  if (r.iteration === 0) return "baseline";
  const s = (r.change_summary ?? "").split(" (vs")[0];
  return s.replace(/^features /, "").replace(/^model /, "").replace("logistic_regression", "logreg").replace(" -> ", " → ").slice(0, 26);
}

export default function Trajectory({ history, target, selected, onSelect, finalTest, visibleCount }: Props) {
  const rows = visibleCount == null ? history : history.slice(0, visibleCount);
  const W = 1200, H = 360, padL = 44, padR = 24, padT = 36, padB = 56, plotB = H - padB;
  const n = rows.length;
  const inner = W - padL - padR - 80;
  const xs = (i: number) => padL + 40 + (n <= 1 ? inner / 2 : (i * inner) / (n - 1));
  const maxY = Math.max(target + 0.08, ...rows.map((r) => r.score), finalTest ?? 0);
  const ys = (v: number) => padT + (1 - v / maxY) * (plotB - padT);
  const points = rows.map((r, i) => ({ x: xs(i), y: ys(r.score), r, isBest: r.score > rows.slice(0, i).reduce((m, q) => Math.max(m, q.score), -1) }));
  const path = points.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = points.length > 1 ? `${path} L${points[points.length - 1].x.toFixed(1)},${plotB} L${points[0].x.toFixed(1)},${plotB} Z` : "";
  const grid = [0, 0.2, 0.4, 0.6].filter((v) => v <= maxY);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full block" role="img" aria-label="Validation AUPRC per experiment with the published test benchmark as a reference line">
      {grid.map((v) => (
        <g key={v}>
          <line x1={padL} x2={W - padR} y1={ys(v)} y2={ys(v)} stroke="var(--rule)" strokeDasharray={v === 0 ? undefined : "2 6"} />
          <text x={padL - 10} y={ys(v) + 4} textAnchor="end" fontSize="12" fill="var(--ink-2)" className="mono">{(v * 100).toFixed(0)}</text>
        </g>
      ))}
      <line x1={padL} x2={W - padR} y1={ys(target)} y2={ys(target)} stroke="var(--rust)" strokeWidth="1.5" strokeDasharray="6 5" />
      <text x={W - padR} y={ys(target) - 8} textAnchor="end" fontSize="13" fill="var(--rust)" className="ui" fontWeight={500}>{(target * 100).toFixed(1)}% published · test</text>
      {finalTest != null && (
        <g>
          <line x1={padL} x2={W - padR} y1={ys(finalTest)} y2={ys(finalTest)} stroke="var(--teal)" strokeWidth="1.5" />
          <text x={padL + 4} y={ys(finalTest) - 8} textAnchor="start" fontSize="13" fill="var(--teal)" className="ui" fontWeight={500}>{(finalTest * 100).toFixed(1)}% ours · test</text>
        </g>
      )}
      {area && <path d={area} fill="var(--ink)" opacity="0.04" />}
      {points.length > 1 && <path d={path} fill="none" stroke="var(--ink)" strokeWidth="2" />}
      {points.map((p) => {
        const isSel = selected === p.r.experiment_id;
        const rejected = p.r.decision === "REJECT";
        return (
          <g key={p.r.experiment_id} className="cursor-pointer" role="button" tabIndex={0} aria-label={`Experiment ${p.r.iteration} details`} onClick={() => onSelect?.(p.r.experiment_id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect?.(p.r.experiment_id); }}>
            <circle cx={p.x} cy={p.y} r={isSel ? 9 : 7} fill={rejected ? "var(--paper)" : p.isBest ? "var(--teal)" : "var(--ink)"} stroke={rejected ? "var(--rust)" : p.isBest ? "var(--teal)" : "var(--ink)"} strokeWidth="2" />
            <text x={p.x} y={p.y - 16} textAnchor="middle" fontSize="15" fill="var(--ink)" className="mono" fontWeight={500}>{(p.r.score * 100).toFixed(1)}</text>
            <text x={p.x} y={H - 30} textAnchor="middle" fontSize="12" fill="var(--ink)" className="ui" fontWeight={500}>{p.r.iteration}</text>
            <text x={p.x} y={H - 12} textAnchor="middle" fontSize="12" fill="var(--ink-2)" className="ui">{shortChange(p.r)}</text>
          </g>
        );
      })}
    </svg>
  );
}
