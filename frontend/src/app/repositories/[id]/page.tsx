import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { ProjectDetail } from "@/components/project-detail";

export const metadata: Metadata = {
  title: "Project · DeployLens",
  description: "Runs, workflows, branches, deploys and uptime for one repository.",
};

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <AppShell>
      <ProjectDetail repositoryId={id} />
    </AppShell>
  );
}
