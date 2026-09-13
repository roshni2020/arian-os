const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

const source = fs.readFileSync('src/lib/experiment-comparison.ts', 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const api = {};
vm.runInNewContext(js, { exports: api });

function experiment(overrides = {}) {
  return {
    id: 'exp-000', session_id: 'session-a', iteration: 0, runtime_seconds: 12,
    experiment: { model: 'logistic_regression', feature_protocol: 'metadata', weather_days: 0, hyperparameters: { C: 1, class_weight: 'balanced', nested: { depth: 3, enabled: false } } },
    result: {
      score_kind: 'VALIDATION_SCORE', split: 'validation', seed: 553371, train_size: 22576, val_size: 7047,
      benchmark_comparable: false, validation_auprc: 0.2, validation_auroc: 0.7, train_auprc: 0.4,
      validation_metrics: { precision: 0.3, recall: 0.6, f1: 0.4 }, threshold_best_f1: 0.35,
      runtime_seconds: 12, n_features: 7,
    },
    ...overrides,
  };
}

const plain = value => JSON.parse(JSON.stringify(value));

test('matching recorded validation contexts permit descriptive deltas without benchmark eligibility', () => {
  const before = experiment();
  const after = experiment({ id: 'exp-001', result: { ...before.result, validation_auprc: 0.4, threshold_best_f1: 0.65 } });
  const context = api.getComparisonContext(before, after);
  assert.equal(context.comparable, true);
  assert.equal(context.status, 'matched');
  assert.equal(context.checks.length, 6);
  assert.equal(context.reasons.length, 0);
  assert.equal(api.getComparisonMetrics(before, after).find(row => row.id === 'ap').difference, 0.2);
});

test('every required context mismatch independently suppresses all computed differences', () => {
  const before = experiment();
  for (const [field, value] of Object.entries({ session_id: 'session-b', score_kind: 'DEV_SCORE', split: 'test', seed: 7, train_size: 100, val_size: 50 })) {
    const after = field === 'session_id' ? experiment({ session_id: value }) : experiment({ result: { ...before.result, [field]: value } });
    const context = api.getComparisonContext(before, after);
    assert.equal(context.comparable, false, field);
    assert.equal(context.status, 'mismatch', field);
    assert.ok(context.reasons.some(reason => reason.includes('differs')), field);
    assert.ok(api.getComparisonMetrics(before, after).every(row => row.difference === null), field);
    assert.equal(api.getComparisonMetrics(before, after).find(row => row.id === 'ap').candidate, 0.2);
  }
});

test('unknown metadata and invalid numeric context never become a matching context', () => {
  const before = experiment();
  for (const [field, value] of [['seed', undefined], ['seed', NaN], ['seed', '553371'], ['train_size', Infinity], ['train_size', -1], ['val_size', 2.5], ['split', ''], ['score_kind', null]]) {
    const context = api.getComparisonContext(before, experiment({ result: { ...before.result, [field]: value } }));
    assert.equal(context.status, 'unknown', field);
    assert.equal(context.comparable, false, field);
    assert.ok(context.reasons.length > 0, field);
  }
  assert.equal(api.getComparisonContext(null, before).comparable, false);
  assert.equal(api.getComparisonContext(before, experiment({ result: null })).status, 'unknown');
});

test('zero metrics are preserved, null and non-finite values stay unavailable without coercion', () => {
  const before = experiment();
  const after = experiment({ runtime_seconds: 0, result: { ...before.result, validation_auprc: 0, validation_auroc: NaN, train_auprc: Infinity, validation_metrics: { precision: null, recall: 0, f1: '0.8' }, runtime_seconds: 0, n_features: 0 } });
  const rows = Object.fromEntries(api.getComparisonMetrics(before, after).map(row => [row.id, row]));
  assert.equal(rows.ap.candidate, 0);
  assert.equal(rows.ap.difference, -0.2);
  assert.equal(rows.recall.candidate, 0);
  assert.equal(rows.runtime.candidate, 0);
  assert.equal(rows.features.candidate, 0);
  for (const field of ['auroc', 'train_ap', 'precision', 'f1']) {
    assert.equal(rows[field].candidate, null, field);
    assert.equal(rows[field].difference, null, field);
  }
});

test('directions distinguish predictive scores, observed runtime and descriptive training/features', () => {
  const before = experiment();
  const after = experiment({ result: { ...before.result, runtime_seconds: 9, n_features: 40 } });
  const rows = Object.fromEntries(api.getComparisonMetrics(before, after).map(row => [row.id, row]));
  assert.equal(rows.ap.direction, 'higher');
  assert.equal(rows.auroc.direction, 'higher');
  assert.equal(rows.runtime.direction, 'lower');
  assert.equal(rows.runtime.difference, -3);
  assert.equal(rows.train_ap.direction, 'neutral');
  assert.equal(rows.features.direction, 'neutral');
  assert.equal(rows.features.difference, 33);
  assert.equal(rows.f1.thresholded, true);
  assert.equal(rows.ap.thresholded, undefined);
  assert.equal(api.formatComparisonDifference(-3, 'seconds'), '−3.0 s');
  assert.equal(api.formatComparisonDifference(0.2, 'score'), '+0.2000');
  assert.equal(api.formatComparisonDifference(0, 'score'), '0.0000');
  assert.ok(api.formatComparisonDifference(0.000001, 'score').startsWith('+'));
  assert.equal(api.formatComparisonValue(0, 'score'), '0.0000');
  assert.equal(api.formatComparisonValue(null, 'score'), 'Not available');
});

test('configuration changes preserve nested leaf paths, additions, deletions and type differences', () => {
  const before = experiment();
  const after = experiment({ experiment: { ...before.experiment, feature_protocol: 'all', hyperparameters: { C: 0, nested: { depth: 8, enabled: false }, options: [1, 2], optional: null } } });
  const changes = api.getConfigurationDifferences(before, after);
  assert.deepEqual(plain(changes.map(change => change.path)), ['feature_protocol', 'hyperparameters.C', 'hyperparameters.class_weight', 'hyperparameters.nested.depth', 'hyperparameters.optional', 'hyperparameters.options']);
  assert.equal(changes.find(change => change.path === 'hyperparameters.C').candidate, 0);
  assert.equal(changes.find(change => change.path === 'hyperparameters.class_weight').candidate, undefined);
  assert.equal(changes.find(change => change.path === 'hyperparameters.optional').candidate, null);
  assert.equal(api.formatConfigurationValue(undefined), 'Not set');
  assert.equal(api.formatConfigurationValue(null), 'null');
  assert.equal(before.experiment.hyperparameters.nested.depth, 3);
});

test('equivalent object key ordering is ignored but array ordering and missing empty objects are changes', () => {
  const before = experiment({ experiment: { hyperparameters: { settings: { a: 1, b: 2 }, list: [1, 2] } } });
  const reordered = experiment({ experiment: { hyperparameters: { list: [1, 2], settings: { b: 2, a: 1 } } } });
  assert.equal(api.getConfigurationDifferences(before, reordered).length, 0);
  const after = experiment({ experiment: { hyperparameters: { settings: { a: 1, b: 2 }, list: [2, 1], empty: {} } } });
  assert.deepEqual(plain(api.getConfigurationDifferences(before, after).map(change => change.path)), ['hyperparameters.empty', 'hyperparameters.list']);
  assert.equal(api.getConfigurationDifferences(null, before).length, 0);
});

test('PR data retains endpoints and recorded order while rejecting invalid points without fabricating a curve', () => {
  const before = experiment();
  assert.deepEqual(plain(api.getPrecisionRecallPoints(before)), { points: [], rejected: 0 });
  const withCurve = experiment({ result: { ...before.result, pr_curve: [{ recall: 1, precision: 0 }, { recall: 0, precision: 1 }, { recall: '0.5', precision: 0.8 }, { recall: 0.5, precision: Infinity }, { recall: -0.1, precision: 0.8 }, null] } });
  assert.deepEqual(plain(api.getPrecisionRecallPoints(withCurve)), { points: [{ recall: 1, precision: 0 }, { recall: 0, precision: 1 }], rejected: 4 });
});
