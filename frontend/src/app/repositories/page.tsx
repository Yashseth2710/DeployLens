import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { RepositoryPicker } from "@/components/repository-picker";

export const metadata: Metadata = {
  title: "Repositories · DeployLens",
  description: "Choose which GitHub repositories DeployLens tracks.",
};

export default function RepositoriesPage() {
  return (
    <AppShell>
      <RepositoryPicker />
    </AppShell>
  );
}
