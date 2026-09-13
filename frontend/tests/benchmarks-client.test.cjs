const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
function client(fetch) {
  const exports = {};
  const js = ts.transpileModule(fs.readFileSync('src/lib/benchmarks.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(js, { exports, fetch, URL, URLSearchParams });
  return exports;
}
test('public access requires explicit evidence, never a nonempty source URL', () => {
  const { displayAccess } = client(() => { throw new Error('No network expected'); });
  assert.equal(displayAccess(true), 'Public access confirmed');
  assert.equal(displayAccess(false), 'Restricted access');
  assert.equal(displayAccess(null), 'Access not confirmed');
  assert.equal(displayAccess(undefined), 'Access not confirmed');
});
test('catalog preserves search syntax and zero offset using backend cache only', async () => {
  const calls = []; const { benchmarkApi } = client(async (...args) => { calls.push(args); return { ok: true, json: async () => ({ items: [], total: 0, stale: true }) }; });
  const result = await benchmarkApi.catalog({ q: 'a&b / task', offset: 0, source: '' });
  assert.equal(result.stale, true); assert.equal(calls[0][0], '/api/benchmarks?q=a%26b+%2F+task&offset=0'); assert.equal(calls[0][1].cache, 'no-store');
});
test('saving a project does not call start and preserves selected result and corrections', async () => {
  const calls = []; const { benchmarkApi } = client(async (...args) => { calls.push(args); return { ok: true, json: async () => ({ id: 'saved', session_id: null }) }; });
  const body = { benchmark_id: 'b', name: 'Review', experiment_budget: 2, selected_result_id: 'r2', overrides: { published_score: 0 }, idempotency_key: 'stable' };
  await benchmarkApi.createProject(body);
  assert.equal(calls.length, 1); assert.equal(calls[0][0], '/api/projects'); assert.deepEqual(JSON.parse(calls[0][1].body), body);
  await benchmarkApi.start('id/with slash'); assert.equal(calls[1][0], '/api/projects/id%2Fwith%20slash/start'); assert.equal(calls[1][1].body, '{}');
});
test('partial imports remain successful and source URL is sent only to backend', async () => {
  const calls = []; const { benchmarkApi } = client(async (...args) => { calls.push(args); return { ok: true, json: async () => ({ id: 'i', status: 'partial', benchmark: null, warnings: ['Missing metric'] }) }; });
  assert.equal((await benchmarkApi.importUrl('https://huggingface.co/datasets/x/y')).status, 'partial'); assert.equal(calls[0][0], '/api/benchmarks/import');
});
test('backend errors and non-JSON failures are actionable', async () => {
  const { benchmarkApi } = client(async () => ({ ok: false, status: 409, json: async () => ({ detail: 'Unsupported protocol' }) }));
  await assert.rejects(benchmarkApi.start('p'), /Unsupported protocol/);
  const other = client(async () => ({ ok: false, status: 502, json: async () => { throw new Error('raw provider secret'); } }));
  await assert.rejects(other.benchmarkApi.projects(), /Request failed \(502\)/);
});
test('journal navigation accepts local paths and rejects external or malformed URLs', () => {
  const { safeJournalUrl, displayValue } = client();
  assert.equal(safeJournalUrl('/?session=wf-1'), '/?session=wf-1');
  for (const value of ['https://evil.example', '//evil.example', '/\\evil.example', 'javascript:alert(1)', '/\n/evil.example']) assert.equal(safeJournalUrl(value), null);
  assert.equal(displayValue(0), '0'); assert.equal(displayValue(null), 'Not available');
});

test('saved project rendering preserves corrections and provenance and links an existing session without start', () => {
  const React = require('react');
  const { renderToStaticMarkup } = require('react-dom/server');
  const snapshot = { title: 'Saved benchmark', results: [{ id: 'r', metric_name: 'Original metric', score: .533, model: 'Original model' }], metric_name: 'Reviewed metric', published_score: .4, published_model: 'Reviewed model', readiness: { score: 2, total: 6, status: 'partial', missing: ['split'] }, provenance: { metric_name: { value: 'Reviewed metric', status: 'user_edited', source_url: null, confidence: null }, dataset_identifier: { value: 'saved/dataset', status: 'verified', source_url: 'https://huggingface.co/datasets/saved/dataset', source_provider: 'huggingface', confidence: 'high' } } };
  const project = { id: 'p', name: 'Saved project', benchmark_id: 'b', snapshot, experiment_budget: 2, selected_result_id: 'r', session_id: 'session&1', compatibility: { executable: false, reasons: ['Unsupported'], comparability: 'Not comparable' } };
  const exports = {}; let stateIndex = 0;
  const js = ts.transpileModule(fs.readFileSync('src/components/benchmarks/ProjectOverview.tsx', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  vm.runInNewContext(js, { exports, require: name => {
    if (name === 'react') return { ...React, useState: initial => [stateIndex++ === 0 ? project : initial, () => {}], useEffect: () => {} };
    if (name === 'next/link') return { __esModule: true, default: ({ children, ...props }) => React.createElement('a', props, children) };
    if (name === '@/lib/benchmarks') return client(() => { throw new Error('Rendering must not start research'); });
    if (name === './BenchmarkShell') return { __esModule: true, default: ({ children }) => React.createElement('main', null, children), ExternalLink: ({ url, children }) => React.createElement('a', { href: url }, children) };
    return require(name);
  } });
  const html = renderToStaticMarkup(React.createElement(exports.default, { id: 'p' }));
  assert.match(html, /href="\/\?session=session%261"/);
  assert.doesNotMatch(html, /<button/);
  assert.match(html, /Reviewed metric/); assert.match(html, /Reviewed model/); assert.doesNotMatch(html, /Original metric|Original model|0\.533/);
  assert.match(html, /Saved field provenance/); assert.match(html, /Status: user edited/); assert.match(html, /https:\/\/huggingface.co\/datasets\/saved\/dataset/);
});
