import Link from "next/link";
import BenchmarkShell from "@/components/benchmarks/BenchmarkShell";

export const metadata = { title: "About · ARIA Researcher" };

const loop = [
  ["Observe", "ARIA reads the full research state: every score, error count, confusion matrix, feature importance and where the model fails (by state, month, fuel type, fire danger, satellite detection)."],
  ["Hypothesize", "It writes one falsifiable hypothesis grounded in the measured numbers, with an expected result."],
  ["Design", "It proposes exactly one experiment from an allowed menu, usually changing one variable against the current best."],
  ["Validate", "The worker checks the proposal against a strict schema. Anything out of bounds or repeated is rejected with structured feedback, and ARIA must try again. The code never substitutes its own idea."],
  ["Train & evaluate", "The worker trains the model on 2016–2018 fires and scores it on the 2019 validation year, logging the run, metrics and artifacts to Weights & Biases."],
  ["Decide", "ARIA marks the experiment KEEP or REJECT with a reason and what it learned, then asks the next question."],
  ["Freeze", "When the budget is spent, ARIA recommends one configuration. It is scored once on the sealed 2020 test year."],
] as const;

const parts = [
  ["ARIA (the AI agent)", "W&B's research agent. The only decision-maker: hypotheses, experiments, KEEP/REJECT and the final recommendation. Each cycle is a fresh conversation, so it receives the complete state every time."],
  ["Worker (not AI)", "Python code that enforces the rules: validates proposals, trains models, measures results and publishes the next state. If ARIA is silent, it waits."],
  ["W&B Automations + Artifacts", "When an experiment run finishes, an Automation wakes ARIA. State goes out and proposals come back as versioned artifacts, so every exchange has provenance."],
  ["Weave", "Traces each step of the loop (receive proposal, validate, train, evaluate, record decision) for inspection."],
] as const;

const menu = [
  ["Models", "Logistic regression, XGBoost"],
  ["Feature sets", "Incident metadata, FIRMS satellite detections, weather, fuel, vegetation, topography, access, human factors, all, or all-but-one"],
  ["Weather window", "1–5 days before discovery"],
  ["Hyperparameters", "Bounded ranges, e.g. XGBoost trees 50–2000, depth 2–10, learning rate 0.005–0.3, regularisation, class weighting"],
] as const;

export default function Page() {
  return <BenchmarkShell>
    <div className="page-header"><div>
      <h1 className="page-heading">How it works</h1>
      <p className="page-subtitle">An autonomous research loop in which W&amp;B&apos;s ARIA agent acts as the scientist, and the code makes sure it does science honestly.</p>
    </div></div>

    <div className="space-y-6 max-w-4xl">
      <section className="surface p-6">
        <h2 className="section-title">The question</h2>
        <p className="mt-2 text-sm text-ink-2 leading-6">Can an AI agent beat the published <strong>WildfireIA</strong> benchmark for predicting <em>initial-attack failure</em>: which US wildfires escape the first firefighting response? The prediction may only use information available at discovery time. Published reference: <strong>0.533 test AUPRC</strong>.</p>
        <p className="mt-2 text-sm text-ink-2 leading-6">Data: 38,128 fires. Train on 2016–2018, select on 2019, and test exactly once on 2020.</p>
      </section>

      <section className="surface p-6">
        <h2 className="section-title">The research loop</h2>
        <ol className="mt-4 space-y-3">
          {loop.map(([step, text], i) => <li key={step} className="flex gap-3 text-sm">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-teal text-xs font-semibold text-white">{i + 1}</span>
            <div><span className="font-semibold">{step}.</span> <span className="text-ink-2">{text}</span></div>
          </li>)}
        </ol>
      </section>

      <section className="surface p-6">
        <h2 className="section-title">Who does what</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {parts.map(([name, text]) => <div key={name} className="rounded-lg border border-rule p-4">
            <p className="text-sm font-semibold">{name}</p>
            <p className="mt-1 text-sm text-ink-2 leading-6">{text}</p>
          </div>)}
        </div>
      </section>

      <section className="surface p-6">
        <h2 className="section-title">What ARIA can change</h2>
        <dl className="mt-4 space-y-2 text-sm">
          {menu.map(([k, v]) => <div key={k} className="grid gap-1 sm:grid-cols-[160px_1fr]"><dt className="font-semibold">{k}</dt><dd className="text-ink-2">{v}</dd></div>)}
        </dl>
        <p className="mt-4 text-sm text-ink-2 leading-6">Every experiment reports validation AUPRC (the selection metric), AUROC, precision, recall, F1, missed fires, false alarms, the train–validation gap and per-group error breakdowns.</p>
      </section>

      <section className="surface p-6">
        <h2 className="section-title">Guardrails</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2 leading-6">
          <li>ARIA can only choose from a closed, bounded menu. Its output is data and is never executed.</li>
          <li>The 2020 test year is sealed until ARIA freezes its final choice.</li>
          <li>Validation scores are never presented as comparable to the published test score.</li>
          <li>A scripted fallback exists for offline tests only, and every session it drives is labelled &ldquo;NOT ARIA&rdquo;.</li>
        </ul>
      </section>

      <section className="surface p-6">
        <h2 className="section-title">Results so far</h2>
        <p className="mt-2 text-sm text-ink-2 leading-6">Two of ARIA&apos;s final recommendations were scored on the sealed 2020 test year over five seeds: <strong>0.5413 ± 0.0024</strong> and <strong>0.5437 ± 0.0017</strong> test AUPRC, both above the published 0.533. These are recorded results, not a certified benchmark claim.</p>
        <p className="mt-2 text-sm text-ink-2 leading-6">This deployment replays the five recorded sessions read-only. Open the <Link href="/" className="link">Research journal</Link> to step through ARIA&apos;s reasoning experiment by experiment.</p>
      </section>
    </div>
  </BenchmarkShell>;
}
