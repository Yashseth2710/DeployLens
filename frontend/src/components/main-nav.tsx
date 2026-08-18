"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import { useLiveCount, useSession } from "@/lib/queries";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/live", label: "Live" },
  { href: "/pull-requests", label: "Pull requests" },
  { href: "/repositories", label: "Repositories" },
];

/**
 * Navigation only appears once there is somewhere to go. A signed-out visitor
 * has one action, and it is not hidden behind a menu.
 */
export function MainNav() {
  const session = useSession();
  const pathname = usePathname();
  const live = useLiveCount();

  if (!session.data) {
    return null;
  }

  // Four labels do not fit a phone in one row, and letting them wrap breaks "Pull
  // requests" across two lines mid-phrase. The row keeps its labels whole and the
  // header scrolls it, which keeps every destination one gesture away.
  return (
    <ul className="flex w-max items-center gap-5">
      {LINKS.map((link) => {
        const current = pathname.startsWith(link.href);
        return (
          <li key={link.href} className="shrink-0">
            <Link
              href={link.href}
              aria-current={current ? "page" : undefined}
              className={cn(
                "label border-b py-1 transition-colors",
                current ? "border-accent !text-ink" : "hover:!text-ink border-transparent",
              )}
            >
              {link.label}
              {link.href === "/live" && live > 0 ? (
                <span className="bg-wait ml-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle">
                  <span className="sr-only">{live} running</span>
                </span>
              ) : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
