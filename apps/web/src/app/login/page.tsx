import { LoginForm } from "@/components/auth/LoginForm";
import { AppShell } from "@/components/shell/AppShell";
import { LoginHeading } from "@/components/auth/LoginHeading";
import { safeNext } from "@/lib/auth/routing";

/** `/login`: demo-friendly sign-in. The proxy sends signed-in users to their role's home. */
export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  const { next } = await searchParams;
  const raw = Array.isArray(next) ? next[0] : next;
  const safe = safeNext(raw, "");
  return (
    <AppShell role={null} width="narrow">
      <LoginHeading />
      <LoginForm next={safe || null} />
    </AppShell>
  );
}
