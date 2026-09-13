const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
function load(fetch) {
  const exports = {};
  const js = ts.transpileModule(fs.readFileSync('src/lib/execution-status.ts', 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(js, {exports,URL,fetch});
  return exports;
}
test('elapsed duration preserves zero and rejects missing or invalid timestamps', () => {
  const {elapsedLabel} = load();
  assert.equal(elapsedLabel(0), '0s');
  assert.equal(elapsedLabel(3661), '1h 1m');
  assert.equal(elapsedLabel(90000), '1d 1h');
  for (const value of [null, undefined, NaN, Infinity, -1]) assert.equal(elapsedLabel(value), 'Not recorded');
});
test('execution links only permit credential-free W&B HTTPS destinations', () => {
  const {safeWandbLink} = load();
  assert.equal(safeWandbLink('https://wandb.ai/team/project/weave/traces'), 'https://wandb.ai/team/project/weave/traces');
  for (const value of [null, '', '/relative', 'javascript:alert(1)', 'http://wandb.ai/team', 'https://wandb.ai.evil.test/team', 'https://evil.test/wandb.ai', 'https://user:secret@wandb.ai/team']) assert.equal(safeWandbLink(value), null);
});
test('execution status uses only a no-store GET with an encoded session identifier', async () => {
  const calls = [];
  const expected = {session_id:'a/b'};
  const {fetchExecutionStatus} = load(async (...args) => {calls.push(args);return {ok:true,json:async()=>expected};});
  assert.equal(await fetchExecutionStatus('a/b'), expected);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], '/api/sessions/a%2Fb/execution-status');
  assert.equal(calls[0][1].cache, 'no-store');
  assert.equal(calls[0][1].method, undefined);
});
test('old API and unavailable status fail explicitly without a recovery request', async () => {
  for (const [status, message] of [[404,/API may need to be updated/],[503,/could not be refreshed/]]) {
    let calls = 0;
    const {fetchExecutionStatus} = load(async () => {calls++;return {ok:false,status};});
    await assert.rejects(fetchExecutionStatus('saved'), message);
    assert.equal(calls, 1);
  }
});
