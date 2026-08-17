"use client";

import { Button, ButtonLink } from "@/components/button";
import { useSession } from "@/lib/queries";

/**
 * The landing page has one action, and which one depends on whether the visitor
 * has an account yet. Offering "sign in" to someone already signed in is the
 * page telling them it has not noticed them.
 */
export function EntryAction() {
  const session = useSession();

  if (session.isPending) {
    return (
      <Button variant="primary" disabled>
        Checking sheet…
      </Button>
    );
  }

  if (session.data) {
    return (
      <div className="flex flex-col items-start gap-3">
        <ButtonLink href="/repositories" variant="primary">
          Open your repositories
        </ButtonLink>
        <span className="label !tracking-[0.1em]">
          Signed in as {session.data.username} · connect a project to start collecting runs
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <ButtonLink href="/api/auth/github" variant="primary">
        Sign in with GitHub
      </ButtonLink>
      <span className="label !tracking-[0.1em]">
        Reads your runs · registers one webhook per connected repository
      </span>
    </div>
  );
}
