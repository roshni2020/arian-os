const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
const vm=require('node:vm');
const api={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/lib/report-preview.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:api,URL});
test('generated report headings, tables and lists become readable blocks without losing escaped table data',()=>{
  const blocks=api.reportBlocks('# Research report\n\n| Model | AP |\n| --- | ---: |\n| A\\|B | 0.0 |\n\n## Limits\n- First\n- Second');
  assert.equal(blocks[0].kind,'heading');
  assert.equal(blocks[1].kind,'table');
  assert.equal(blocks[1].rows[0][0],'A|B');
  assert.equal(blocks[1].rows[0][1],'0.0');
  assert.equal(blocks[3].items.length,2);
});
test('HTML and markdown links remain inert text without URL interpretation',()=>{
  const text='<img src=x onerror=alert(1)> [click](javascript:alert(1))';
  const blocks=api.reportBlocks(text);
  assert.equal(blocks[0].kind,'paragraph'); assert.equal(blocks[0].text,text);
});
test('publication links allow only credential-free W&B HTTPS URLs',()=>{
  assert.equal(api.publishedReportUrl('https://wandb.ai/team/project/reports/a'),'https://wandb.ai/team/project/reports/a');
  for(const value of ['javascript:alert(1)','https://wandb.ai.evil.test','https://user:secret@wandb.ai/r','http://wandb.ai/r',null]) assert.equal(api.publishedReportUrl(value),null);
});
