import Link from "next/link";
import type { ReactNode } from "react";

import { AccountBar } from "@/components/account-bar";
import { Wordmark } from "@/components/brand";
import { MainNav } from "@/components/main-nav";
import { ThemeToggle } from "@/components/theme-toggle";

/**
 * The page is a sheet on a bench: a job-ticket strip at the head, the plates
 * below, and the imprint line at the foot. The strip stays the same width as
 * the work so nothing floats free of the registration.
 */
export function AppShell({ children, nav }: { children: ReactNode; nav?: ReactNode }) {
  return (
    <div className="relative isolate flex min-h-dvh flex-col">
      <header className="border-rule border-b">
        <div className="mx-auto flex w-full max-w-[76rem] flex-wrap items-center gap-x-4 gap-y-3 px-5 py-4 sm:flex-nowrap sm:gap-x-6 sm:px-6">
          <Link href="/" className="rounded-sheet text-rank-c">
            <Wordmark />
          </Link>
          <nav className="order-3 w-full sm:order-none sm:w-auto sm:flex-1">
            {nav ?? <MainNav />}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-4 sm:ml-0">
            <AccountBar />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[76rem] flex-1 px-5 py-10 sm:px-6">{children}</main>

      <footer className="border-rule border-t">
        <div className="mx-auto flex w-full max-w-[76rem] flex-wrap items-center justify-between gap-4 px-5 py-5 sm:px-6">
          <p className="label">
            Deployment and uptime tracking · GitHub Actions · Runs on free tiers
          </p>
          <a
            href="https://github.com/Yashseth2710/DeployLens"
            className="label hover:!text-ink transition-colors"
          >
            Source
          </a>
        </div>
      </footer>
    </div>
  );
}
