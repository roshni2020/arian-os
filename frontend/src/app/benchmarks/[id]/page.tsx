import BenchmarkDetails from "@/components/benchmarks/BenchmarkDetails";
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <BenchmarkDetails key={id} id={id} />; }
