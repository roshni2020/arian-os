import { reportBlocks } from "@/lib/report-preview";
function Inline({text}:{text:string}) {
  return <>{text.split(/(`[^`]+`)/g).map((part,index) => part.startsWith("`") && part.endsWith("`") ? <code key={index} className="rounded bg-paper px-1 text-xs">{part.slice(1,-1)}</code> : part)}</>;
}
export default function ReportPreview({markdown}:{markdown:string}) {
  return <div className="mt-4 max-h-[36rem] space-y-4 overflow-auto rounded border border-line p-4 text-sm leading-6">{reportBlocks(markdown).map((block,index) => {
    if(block.kind==="heading") return block.level===1 ? <h3 key={index} className="text-lg font-semibold"><Inline text={block.text}/></h3> : <h4 key={index} className="border-t border-line pt-4 font-semibold"><Inline text={block.text}/></h4>;
    if(block.kind==="list") return <ul key={index} className="list-disc space-y-1 pl-5">{block.items.map((item,i)=><li key={i}><Inline text={item}/></li>)}</ul>;
    if(block.kind==="table") return <div key={index} className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr>{block.headers.map((header,i)=><th key={i} scope="col" className="border-b border-line p-2 font-semibold"><Inline text={header}/></th>)}</tr></thead><tbody>{block.rows.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j} className="border-b border-line p-2"><Inline text={cell}/></td>)}</tr>)}</tbody></table></div>;
    return <p key={index} className="break-words"><Inline text={block.text}/></p>;
  })}</div>;
}
