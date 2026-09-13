const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const source = fs.readFileSync('src/lib/replay.ts','utf8');
const js = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const exportsObject = {};
vm.runInNewContext(js,{exports:exportsObject,structuredClone});
const { parseReplay, replayView } = exportsObject;
const fixture = () => ({replay_format:1,session:{id:'wf',final_evaluation:{mean_test_auprc:.54,benchmark_beaten:true}},
 state:{session_id:'wf',history:[{experiment_id:'exp-0',score:.4}]},dataset:{},events:[],
 experiments:[{id:'exp-0',session_id:'wf',score:.4,result:{validation_auprc:.4}}]});
test('replay preserves scores without a network call',()=>{
 const record=parseReplay(JSON.stringify(fixture())); const view=replayView(record);
 assert.equal(view.experiments[0].score,.4); assert.equal(view.worker_alive,false);
 assert.equal(view.session.final_evaluation.benchmark_beaten,false);
 assert.equal(record.session.final_evaluation.benchmark_beaten,true);
});
test('rejects inconsistent metric and session records',()=>{
 const f=fixture(); f.experiments[0].score=.9;
 assert.throws(()=>parseReplay(JSON.stringify(f)),/metrics/);
 f.state.session_id='wrong';assert.throws(()=>parseReplay(JSON.stringify(f)),/Invalid/);
});
test('rejects wrong format',()=>assert.throws(()=>parseReplay('{}'),/Invalid/));
