import ImportStatus from "@/components/benchmarks/ImportStatus";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <ImportStatus key={id} id={id} />; }
