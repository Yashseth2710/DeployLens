"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";

import { Button, ButtonLink } from "@/components/button";
import { ApiError } from "@/lib/api";
import { useSession, useSignOut } from "@/lib/queries";

/**
 * Who signed this sheet. Signing out is reachable from every page — an
 * endpoint nobody can press is not a capability. Switching account is its own
 * control rather than a sentence, with the revoke caveat kept underneath it:
 * GitHub re-authorizes the same account silently, so a user who skips the
 * revoke lands back where they started.
 */
export function AccountBar() {
  const session = useSession();
  const signOut = useSignOut();
  const router = useRouter();

  if (session.isPending) {
    return <span className="label">checking sheet…</span>;
  }

  const signedOut = session.error instanceof ApiError && session.error.status === 401;
  if (signedOut || !session.data) {
    return (
      <a href="/api/auth/github" className="label hover:!text-ink transition-colors">
        Sign in
      </a>
    );
  }

  const user = session.data;

  return (
    <details className="group relative">
      <summary className="rounded-sheet flex cursor-pointer list-none items-center gap-2.5 py-1 outline-offset-4 [&::-webkit-details-marker]:hidden">
        {user.avatar_url ? (
          <Image
            src={user.avatar_url}
            alt=""
            width={20}
            height={20}
            className="rounded-sheet border-rule border"
            unoptimized
          />
        ) : null}
        <span className="label !text-ink-quiet hidden sm:inline">{user.username}</span>
      </summary>

      <div className="sheet absolute right-0 z-20 mt-2 flex w-64 flex-col gap-3 p-4">
        <div className="flex flex-col gap-1">
          <span className="label">Signed in as</span>
          <span className="text-ink">{user.username}</span>
          {user.email ? <span className="label !tracking-[0.08em]">{user.email}</span> : null}
        </div>

        <div className="border-rule flex flex-col gap-2 border-t pt-3">
          <Button
            variant="primary"
            size="compact"
            disabled={signOut.isPending}
            onClick={() =>
              signOut.mutate(undefined, {
                onSuccess: () => {
                  router.push("/");
                  router.refresh();
                },
              })
            }
          >
            {signOut.isPending ? "Signing out…" : "Sign out"}
          </Button>
          <ButtonLink
            href="https://github.com/settings/applications"
            target="_blank"
            rel="noreferrer"
            variant="secondary"
            size="compact"
          >
            Switch account
          </ButtonLink>
          <p className="label !text-ink-faint leading-[1.5] !tracking-[0.08em]">
            Revoke DeployLens on GitHub first, or it signs you straight back into this account.
          </p>
        </div>
        <span className="crop-foot" aria-hidden="true" />
      </div>
    </details>
  );
}
