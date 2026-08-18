import type { Metadata } from "next";

import { AlertBoard } from "@/components/alert-board";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: "Alerts · DeployLens",
  description: "Which pipelines broke, what was filed about them, and what has recovered.",
};

export default function AlertsPage() {
  return (
    <AppShell>
      <AlertBoard />
    </AppShell>
  );
}
