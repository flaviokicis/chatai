import FlowManagementClient from "./FlowManagementClient";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function FlowManagementPage({ params }: PageProps): Promise<JSX.Element> {
  const { id } = await params;
  
  return <FlowManagementClient tenantId={id} />;
}