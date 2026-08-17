"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";
import { useLiveCount, useSession } from "@/lib/queries";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/live", label: "Live" },
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

  return (
    <ul className="flex items-center gap-5">
      {LINKS.map((link) => {
        const current = pathname.startsWith(link.href);
        return (
          <li key={link.href}>
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
