import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { LiveBoard } from "@/components/live-board";

export const metadata: Metadata = {
  title: "Live · DeployLens",
  description: "Workflow runs and deployments currently in flight across every project.",
};

export default function LivePage() {
  return (
    <AppShell>
      <LiveBoard />
    </AppShell>
  );
}
