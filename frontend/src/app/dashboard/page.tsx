import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { Dashboard } from "@/components/dashboard";

export const metadata: Metadata = {
  title: "Dashboard · DeployLens",
  description: "Delivery reliability and uptime across every connected project.",
};

export default function DashboardPage() {
  return (
    <AppShell>
      <Dashboard />
    </AppShell>
  );
}
