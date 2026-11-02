"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { signIn, signOut, type LoginAs } from "@/lib/auth/signin";
import { createBrowserSupabase } from "@/lib/supabase/browser";

export type SignInError = "invalid" | "no_profile" | "network" | "wrong_role";

/**
 * Sign-in state for the login page: `submit` signs in (optionally as "student" or "staff", which must match the role), then navigates to the role's home
 * (or the safe `next` path) and refreshes so Server Components see the new session.
 */
export function useSignIn(next?: string | null) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<SignInError | null>(null);

  const submit = useCallback(
    async (email: string, password: string, as?: LoginAs) => {
      setPending(true);
      setError(null);
      const result = await signIn(createBrowserSupabase(), email, password, next, as);
      if (result.ok) {
        router.replace(result.destination);
        router.refresh();
        return;
      }
      setError(result.reason);
      setPending(false);
    },
    [next, router],
  );

  return { submit, pending, error };
}

/** Signs out and returns to the login page. */
export function useSignOut() {
  const router = useRouter();
  return useCallback(async () => {
    await signOut(createBrowserSupabase());
    router.replace("/login");
    router.refresh();
  }, [router]);
}
