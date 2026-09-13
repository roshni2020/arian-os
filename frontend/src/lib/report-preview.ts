export type ReportBlock = { kind:"heading"; level:number; text:string } | {kind:"paragraph";text:string} | {kind:"list";items:string[]} | {kind:"table";headers:string[];rows:string[][]};
function cells(line:string) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map(cell => cell.trim().replaceAll("\\|", "|"));
}
/** A deliberately small text-only parser for generated research reports. */
export function reportBlocks(markdown:string):ReportBlock[] {
  const lines=markdown.replaceAll("\r\n", "\n").split("\n");
  const output:ReportBlock[]=[];
  for(let i=0;i<lines.length;i++) {
    const line=lines[i].trim();
    if(!line) continue;
    const heading=/^(#{1,6})\s+(.+)$/.exec(line);
    if(heading) { output.push({kind:"heading",level:heading[1].length,text:heading[2]}); continue; }
    if(line.startsWith("|") && i+1<lines.length && cells(lines[i+1]).every(cell => /^:?-{3,}:?$/.test(cell))) {
      const headers=cells(line); const rows:string[][]=[]; i++;
      while(i+1<lines.length && lines[i+1].trim().startsWith("|")) { rows.push(cells(lines[++i])); }
      output.push({kind:"table",headers,rows}); continue;
    }
    if(line.startsWith("- ")) {
      const items=[line.slice(2)];
      while(i+1<lines.length && lines[i+1].trim().startsWith("- ")) items.push(lines[++i].trim().slice(2));
      output.push({kind:"list",items}); continue;
    }
    output.push({kind:"paragraph",text:line});
  }
  return output;
}
export function publishedReportUrl(value:unknown) {
  if(typeof value!=="string") return null;
  try { const url=new URL(value); return url.protocol==="https:" && url.hostname==="wandb.ai" && !url.username && !url.password ? url.href : null; }
  catch { return null; }
}
