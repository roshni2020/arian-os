const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const source = fs.readFileSync('src/lib/benchmark-review.ts', 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const exportsObject = {};
vm.runInNewContext(js, { exports: exportsObject });
const { reviewValues, reviewOverrides } = exportsObject;
test('explicit result selection prefills source values without fabricating user corrections', () => {
  const benchmark = { metric_name: 'AP', published_score: 0.5, provenance: {}, results: [{ id: 'result-b', metric_name: 'AUROC', metric_direction: 'maximize', score: 0.8, model: 'Model B', source_url: 'https://example.org/paper' }] };
  const selected = exportsObject.selectedReviewBenchmark(benchmark, 'result-b');
  assert.equal(selected.published_score, 0.8);
  assert.equal(selected.provenance.published_score.status, 'inferred');
  assert.deepEqual(JSON.parse(JSON.stringify(reviewOverrides(selected, reviewValues(selected)))), {});
  const values = reviewValues(selected); values.published_score = '0.9';
  assert.equal(reviewOverrides(selected, values).published_score, 0.9);
  assert.equal(benchmark.published_score, 0.5);
});
test('untouched missing values and protocol do not generate user overrides', () => {
  const benchmark = { published_score: null, evaluation_protocol: { split: 'official' } };
  assert.deepEqual(JSON.parse(JSON.stringify(reviewOverrides(benchmark, reviewValues(benchmark)))), {});
});
test('only changed fields become corrections and zero remains a numeric target', () => {
  const benchmark = { published_score: 0.533, dataset_revision: 'pinned', metric_name: 'AP' };
  const values = reviewValues(benchmark); values.published_score = '0'; values.dataset_revision = '';
  assert.deepEqual(JSON.parse(JSON.stringify(reviewOverrides(benchmark, values))), { dataset_revision: null, published_score: 0 });
});
test('reject malformed numeric targets and non-object protocols', () => {
  const values = reviewValues({}); values.published_score = 'Infinity';
  assert.throws(() => reviewOverrides({}, values), /finite number/);
  values.published_score = ''; values.evaluation_protocol = '[]';
  assert.throws(() => reviewOverrides({}, values), /JSON object/);
  values.evaluation_protocol = '{'; assert.throws(() => reviewOverrides({}, values), /valid JSON/);
});
