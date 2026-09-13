import type { EventRow, Experiment, ResearchState, Session, SessionView } from './api';

export type ReplayRecord = { replay_format: number; session: Session; state: ResearchState; experiments: Experiment[]; events: EventRow[]; dataset: SessionView['dataset'] };

export function parseReplay(text: string): ReplayRecord {
  const r = JSON.parse(text) as ReplayRecord;
  if (r.replay_format !== 1 || !r.session?.id || r.state?.session_id !== r.session.id || !r.dataset || !Array.isArray(r.experiments) || !Array.isArray(r.events) || !Array.isArray(r.state.history)) throw new Error('Invalid replay record');
  for (const h of r.state.history) {
    const e = r.experiments.find(x => x.id === h.experiment_id);
    if (!e || e.session_id !== r.session.id || !Number.isFinite(h.score) || e.score !== h.score || e.result?.validation_auprc !== h.score) throw new Error('Replay metrics do not match saved experiments');
  }
  return r;
}

export function replayView(record: ReplayRecord): SessionView {
  const session = structuredClone(record.session);
  if (session.final_evaluation) {
    session.final_evaluation.benchmark_beaten = !!(session.final_evaluation.claim_eligible && session.final_evaluation.benchmark_beaten);
    session.final_evaluation.claim_note ??= 'Historical result: strict freeze/integrity gates were not enforced. Paper seeds are unavailable; session 2 followed session 1 test disclosure.';
  }
  return { session, state: record.state, experiments: record.experiments, worker_alive: false,
    mode_label:'REPLAYING STORED RUN', benchmark:{published_test_auprc:0.533,published_model:'XGBoost',beaten:!!session.final_evaluation?.benchmark_beaten}, dataset:record.dataset };
}
