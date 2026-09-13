const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function load(path) {
  const exports = {};
  const js = ts.transpileModule(fs.readFileSync(path, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  vm.runInNewContext(js, { exports, require: name => {
    if (name === './experiment-comparison' || name === '@/lib/experiment-comparison') return load('src/lib/experiment-comparison.ts');
    if (name === '@/lib/error-analysis') return load('src/lib/error-analysis.ts');
    return require(name);
  } });
  return exports;
}

const analysis = load('src/lib/error-analysis.ts');
function group(name, overrides = {}) {
  return { group: name, count: 100, positives: 20, false_negatives: 5, false_positives: 10, recall: .75, small_group: false, ...overrides };
}
function experiment(id, groups, overrides = {}) {
  return {
    id, session_id: 'session-1', result: {
      score_kind: 'VALIDATION_AUPRC', split: 'val (2019)', seed: 123,
      train_size: 500, val_size: 200, val_positives: 40, threshold_best_f1: .5,
      confusion_matrix: { tp: 30, fn: 10, fp: 20, tn: 140 },
      error_breakdowns: { by_state: groups }, ...overrides,
    },
  };
}

test('error groups join by label even when error ranks and order change', () => {
  const baseline = experiment('a', [group('North', { false_negatives: 8, recall: .6 }), group('South', { false_negatives: 2, recall: .9 })]);
  const candidate = experiment('b', [group('South', { false_negatives: 6, recall: .7 }), group('North', { false_negatives: 3, recall: .85 })]);
  const rows = analysis.alignErrorGroups(baseline, candidate, 'by_state');
  const north = rows.find(row => row.group === 'North');
  const south = rows.find(row => row.group === 'South');
  assert.equal(north.baseline.falseNegatives, 8);
  assert.equal(north.candidate.falseNegatives, 3);
  assert.equal(north.changes.falseNegatives, -5);
  assert.equal(south.changes.falseNegatives, 4);
  assert.equal(north.comparable, true);
});

test('missing groups stay unknown and never acquire zero errors or deltas', () => {
  const rows = analysis.alignErrorGroups(experiment('a', [group('A')]), experiment('b', [group('B')]), 'by_state');
  assert.equal(rows.length, 2);
  for (const row of rows) {
    assert.equal(row.comparable, false);
    assert.equal(row.changes.falseNegatives, null);
    assert.equal(row.changes.recall, null);
  }
  assert.equal(rows.find(row => row.group === 'A').candidate, null);
  assert.equal(rows.find(row => row.group === 'B').baseline, null);
});

test('different sample counts, positive membership, and duplicate labels block group deltas', () => {
  const baseline = experiment('a', [group('sample'), group('positive'), group('duplicate'), group('duplicate')]);
  const candidate = experiment('b', [group('sample', { count: 90 }), group('positive', { positives: 15 }), group('duplicate')]);
  const rows = analysis.alignErrorGroups(baseline, candidate, 'by_state');
  assert.equal(rows.length, 3);
  for (const row of rows) {
    assert.equal(row.comparable, false);
    assert.equal(row.changes.falsePositives, null);
  }
  assert.match(rows.find(row => row.group === 'sample').reasons.join(' '), /counts differ/);
  assert.match(rows.find(row => row.group === 'duplicate').reasons.join(' '), /Duplicate/);
});

test('different sessions, splits, score kinds, seeds, and train/evaluation counts block deltas', () => {
  const baseline = experiment('a', [group('A')]);
  const candidates = [
    { ...experiment('b', [group('A')]), session_id: 'another-session' },
    ...[{ split: 'test' }, { score_kind: 'DEV_SCORE' }, { seed: 124 }, { train_size: 499 }, { val_size: 199 }, { seed: null }].map(change => experiment('b', [group('A')], change)),
  ];
  for (const candidate of candidates) {
    const row = analysis.alignErrorGroups(baseline, candidate, 'by_state')[0];
    assert.equal(row.comparable, false);
    assert.equal(row.changes.falseNegatives, null);
  }
});

test('threshold differences are retained rather than treated as common-threshold improvements', () => {
  const baseline = experiment('a', [group('A')], { threshold_best_f1: 0 });
  const candidate = experiment('b', [group('A', { false_negatives: 2 })], { threshold_best_f1: .75 });
  assert.equal(analysis.errorSummary(baseline).threshold, 0);
  assert.equal(analysis.errorSummary(candidate).threshold, .75);
  assert.equal(analysis.alignErrorGroups(baseline, candidate, 'by_state')[0].changes.falseNegatives, -3);
  for (const invalid of [null, undefined, NaN, Infinity, '0.5', -1, 2]) {
    assert.equal(analysis.errorSummary(experiment('x', [], { threshold_best_f1: invalid })).threshold, null);
  }
});

test('small groups and zero-positive recall stay explicit; malformed numbers are unknown', () => {
  const baseline = experiment('a', [
    group('small', { count: 29, positives: 10, false_negatives: 0, false_positives: 0, recall: 1 }),
    group('flagged', { small_group: true }),
    group('no positives', { positives: 0, false_negatives: 0, recall: 0 }),
    group('unknown', { count: null, positives: null, false_negatives: null, false_positives: NaN, recall: null }),
  ]);
  const rows = analysis.alignErrorGroups(baseline, null, 'by_state');
  assert.equal(rows.find(row => row.group === 'small').baseline.smallGroup, true);
  assert.equal(rows.find(row => row.group === 'flagged').baseline.smallGroup, true);
  assert.equal(rows.find(row => row.group === 'small').baseline.falseNegatives, 0);
  assert.equal(rows.find(row => row.group === 'no positives').baseline.recall, null);
  assert.equal(rows.find(row => row.group === 'unknown').baseline.falsePositives, null);
  assert.equal(rows.find(row => row.group === 'unknown').baseline.count, null);
});

test('sorting supports FN, FP, recall, sample count and changes without replacing candidate gaps', () => {
  const baseline = experiment('a', [group('low'), group('high'), group('missing')]);
  const candidate = experiment('b', [group('low', { false_negatives: 1, false_positives: 2, recall: .95 }), group('high', { false_negatives: 9, false_positives: 20, recall: .55 })]);
  const rows = analysis.alignErrorGroups(baseline, candidate, 'by_state');
  for (const sort of ['falseNegatives', 'falsePositives', 'falseNegativesChange', 'falsePositivesChange']) {
    assert.equal(analysis.sortErrorGroups(rows, sort, 'desc', 'candidate')[0].group, 'high');
    assert.equal(analysis.sortErrorGroups(rows, sort, 'asc', 'candidate')[0].group, 'low');
    assert.equal(analysis.sortErrorGroups(rows, sort, 'asc', 'candidate').at(-1).group, 'missing');
  }
  assert.equal(analysis.sortErrorGroups(rows, 'recall', 'desc', 'candidate')[0].group, 'low');
  assert.equal(analysis.sortErrorGroups(rows, 'recallChange', 'asc', 'candidate')[0].group, 'high');
  assert.equal(analysis.sortErrorGroups(rows, 'count', 'asc', 'candidate').at(-1).group, 'missing');
  assert.equal(analysis.filterErrorGroups(rows, '  LOW ')[0].group, 'low');
  assert.equal(analysis.filterErrorGroups(rows, 'no such group').length, 0);
});

test('dimension union and rendering preserve every returned group beyond the previous six-row cutoff', () => {
  const baseline = experiment('a', Array.from({ length: 11 }, (_, index) => group(`Region ${index + 1}`)));
  const candidate = experiment('b', [], { error_breakdowns: { by_month: [group('January')] } });
  assert.equal(analysis.errorDimensions(baseline, candidate).join(','), 'by_month,by_state');
  assert.equal(analysis.alignErrorGroups(baseline, null, 'by_state').length, 11);
  const React = require('react');
  const { renderToStaticMarkup } = require('react-dom/server');
  const Component = load('src/components/research/ErrorAnalysis.tsx').default;
  const html = renderToStaticMarkup(React.createElement(Component, { baseline, candidate: null }));
  assert.match(html, /Region 11/);
  assert.match(html, /11 of 11 recorded groups/);
  assert.match(html, /scope="row"/);
  assert.match(html, /role="region"/);
  assert.doesNotMatch(html, /NaN|Infinity/);
});

test('confusion summaries retain unknown cells and flag totals inconsistent with evaluation size', () => {
  assert.equal(analysis.errorSummary(experiment('a', [])).countMismatch, false);
  assert.equal(analysis.errorSummary(experiment('a', [], { val_size: 100 })).countMismatch, true);
  const summary = analysis.errorSummary(experiment('a', [], { confusion_matrix: { tp: null, fn: 10, fp: 20, tn: 140 } }));
  assert.equal(summary.tp, null);
  assert.equal(summary.total, null);
});
