import ReviewImport from "@/components/benchmarks/ReviewImport";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <ReviewImport key={id} id={id} />; }
