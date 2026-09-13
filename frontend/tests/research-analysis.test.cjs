const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const source = fs.readFileSync('src/lib/research-analysis.ts', 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const api = {};
vm.runInNewContext(js, { exports: api });

function experiment(id, iteration, score, overrides = {}) {
  return { id, session_id: 'session-a', iteration, score, result: { validation_auprc: score }, updated_at: '2026-09-13T20:00:00Z', ...overrides };
}

test('default baseline is the earliest recorded result and candidate is the best finite alternative', () => {
  const input = [experiment('exp-002', 2, 0.4), experiment('exp-001', 1, 0.3), experiment('exp-000', 0, 0.2), experiment('exp-003', 3, Infinity), experiment('other-session', -1, 0.9, { session_id: 'session-b' }), experiment('unfinished', -1, null, { result: null })];
  const selected = api.resolveAnalysisSelection(input, 'session-a', '', '');
  assert.equal(selected.baseline.id, 'exp-000');
  assert.equal(selected.candidate.id, 'exp-002');
  assert.equal(selected.available.length, 4);
  assert.equal(input[0].id, 'exp-002', 'selection does not reorder the input');
});

test('explicit baseline and candidate remain selected when a newer best experiment arrives', () => {
  const input = [experiment('exp-000', 0, 0.2), experiment('exp-001', 1, 0.3), experiment('exp-002', 2, 0.4)];
  const selected = api.resolveAnalysisSelection(input, 'session-a', 'exp-001', 'exp-000');
  assert.equal(selected.baseline.id, 'exp-001');
  assert.equal(selected.candidate.id, 'exp-000');
  const afterUpdate = api.resolveAnalysisSelection([...input, experiment('exp-003', 3, 0.9)], 'session-a', 'exp-001', 'exp-000');
  assert.equal(afterUpdate.baseline.id, 'exp-001');
  assert.equal(afterUpdate.candidate.id, 'exp-000');
});

test('replay rewinding does not silently replace a pinned selection and advancing restores it', () => {
  const early = experiment('exp-000', 0, 0.2);
  const later = experiment('exp-001', 1, 0.5);
  const rewound = api.resolveAnalysisSelection([early], 'session-a', 'exp-001', 'exp-000');
  assert.equal(rewound.baseline, null);
  assert.equal(rewound.candidate.id, 'exp-000');
  const restored = api.resolveAnalysisSelection([early, later], 'session-a', 'exp-001', 'exp-000');
  assert.equal(restored.baseline.id, 'exp-001');
  const missingCandidate = api.resolveAnalysisSelection([early], 'session-a', 'exp-000', 'exp-001');
  assert.equal(missingCandidate.candidate, null);
});

test('no candidate is substituted for an unavailable explicit choice or a baseline collision', () => {
  const input = [experiment('exp-000', 0, 0.2), experiment('exp-001', 1, 0.4)];
  assert.equal(api.resolveAnalysisSelection(input, 'session-a', 'exp-000', 'missing').candidate, null);
  assert.equal(api.resolveAnalysisSelection(input, 'session-a', 'exp-000', 'exp-000').candidate, null);
  assert.equal(api.resolveAnalysisSelection([experiment('zero', 0, 0), experiment('missing-score', 1, null)], 'session-a', 'missing-score', '').candidate.id, 'zero');
});

test('full response newer than polling summary is usable, but stale responses are rejected', () => {
  const summary = experiment('exp-000', 0, 0.2);
  const newer = { ...summary, updated_at: '2026-09-13T20:01:00Z', result: { ...summary.result, pr_curve: [{ recall: 0, precision: 1 }] } };
  const cache = { [api.analysisCacheKey(summary.session_id, summary.id)]: newer };
  assert.equal(api.acceptAnalysisRecord(newer, summary), true);
  assert.equal(api.cachedAnalysisRecord(summary, 'session-a', cache), newer);
  assert.equal(api.acceptAnalysisRecord({ ...summary, updated_at: '2026-09-13T19:59:00Z' }, summary), false);
  assert.equal(api.cachedAnalysisRecord({ ...summary, updated_at: '2026-09-13T20:02:00Z' }, 'session-a', cache), null);
});

test('same experiment ID and timestamp cannot hydrate from a different session or response ID', () => {
  const summary = experiment('exp-000', 0, 0.2);
  const otherSession = { ...summary, session_id: 'session-b' };
  assert.equal(api.acceptAnalysisRecord(otherSession, summary), false);
  assert.equal(api.acceptAnalysisRecord({ ...summary, id: 'exp-001' }, summary), false);
  assert.notEqual(api.analysisCacheKey('session-a', summary.id), api.analysisCacheKey('session-b', summary.id));
  const deliberatelyWrongEntry = { [api.analysisCacheKey('session-a', summary.id)]: otherSession };
  assert.equal(api.cachedAnalysisRecord(summary, 'session-a', deliberatelyWrongEntry), null);
  assert.equal(api.analysisRecordForView(summary, 'session-b', {}, false), null);
});

test('replay always uses the supplied stored record and never borrows cached live PR data', () => {
  const stored = experiment('exp-000', 0, 0.2);
  const live = { ...stored, result: { ...stored.result, pr_curve: [{ recall: 0, precision: 1 }] } };
  const cache = { [api.analysisCacheKey(stored.session_id, stored.id)]: live };
  assert.equal(api.analysisRecordForView(stored, 'session-a', cache, true), stored);
  assert.equal(api.analysisRecordForView(stored, 'session-a', cache, true).result.pr_curve, undefined);
  assert.equal(api.analysisRecordForView(stored, 'session-a', cache, false), live);
});

test('missing or unorderable changed revisions leave the available summary intact', () => {
  const summary = experiment('exp-000', 0, 0.2);
  assert.equal(api.acceptAnalysisRecord({ ...summary, updated_at: '' }, summary), false);
  assert.equal(api.acceptAnalysisRecord({ ...summary, updated_at: 'unknown' }, summary), false);
  assert.equal(api.analysisRecordForView(summary, 'session-a', {}, false), summary);
  assert.equal(api.analysisRecordForView(null, 'session-a', {}, true), null);
});
