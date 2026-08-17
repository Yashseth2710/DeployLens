import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { ReviewBoard } from "@/components/review-board";

export const metadata: Metadata = {
  title: "Pull requests · DeployLens",
  description: "What was opened, merged and abandoned across every connected project.",
};

export default function PullRequestsPage() {
  return (
    <AppShell>
      <ReviewBoard />
    </AppShell>
  );
}
