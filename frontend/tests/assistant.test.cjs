const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
function load(fetch) {
  const exports = {};
  const js = ts.transpileModule(fs.readFileSync('src/lib/assistant.ts', 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(js, {exports, fetch, URLSearchParams, crypto:{randomUUID:()=> 'stable-key'}});
  return exports;
}
test('read operations never issue a write or cache research results', async () => {
  const calls=[]; const api=load(async (...args)=>{calls.push(args);return {ok:true,json:async()=>({items:[]})};});
  await api.assistantApi('/requests?'+api.scopeQuery('a/b','p&x'));
  assert.equal(calls[0][0], '/api/assistant/requests?session_id=a%2Fb&project_id=p%26x');
  assert.equal(calls[0][1].method, undefined); assert.equal(calls[0][1].cache,'no-store');
});
test('explicit write preserves caller idempotency key and separate action URL', async () => {
  const calls=[]; const api=load(async (...args)=>{calls.push(args);return {ok:true,json:async()=>({id:'r'})};});
  const body={question:'Why?',idempotency_key:api.submissionKey(),excluded_finding_ids:['finding-previous']};
  await api.assistantApi('/requests',body); await api.assistantApi('/requests',body);
  assert.equal(calls[0][1].method,'POST'); assert.equal(calls[0][1].body,calls[1][1].body);
  assert.equal(JSON.parse(calls[0][1].body).idempotency_key,'stable-key');
  assert.deepEqual(JSON.parse(calls[0][1].body).excluded_finding_ids,['finding-previous']);
});
test('validation seed parser rejects duplicates, fractions, negatives and missing values', () => {
  const api=load(); assert.equal(JSON.stringify(api.seedList('17, 42,103')),'[17,42,103]');
  for(const value of ['', '1,1','-1,2','1.5,2','abc']) assert.throws(()=>api.seedList(value));
});
test('server capability and conflict failures are surfaced without automatic retry', async () => {
  let calls=0; const api=load(async ()=>{calls++;return {ok:false,status:409,json:async()=>({detail:'Snapshot changed; review again.'})};});
  await assert.rejects(api.assistantApi('/drafts/x/start',{version_hash:'old'}),/Snapshot changed/); assert.equal(calls,1);
});
test('only queued dispatched and waiting requests show cancellable pending state', () => {
  const api=load(); for(const s of ['queued','dispatched','waiting']) assert.equal(api.pendingRequest(s),true);
  for(const s of ['succeeded','cancelled','timed_out','failed']) assert.equal(api.pendingRequest(s),false);
});
