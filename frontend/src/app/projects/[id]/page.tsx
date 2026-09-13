import ProjectOverview from "@/components/benchmarks/ProjectOverview";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectOverview key={id} id={id} />;
}
