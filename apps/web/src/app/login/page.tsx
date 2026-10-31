import { LoginForm } from "@/components/auth/LoginForm";
import { LanguageSwitch } from "@/components/ui";
import { LoginHeading } from "@/components/auth/LoginHeading";
import { safeNext } from "@/lib/auth/routing";

/** `/login`: demo-friendly sign-in. The proxy sends signed-in users to their role's home. */
export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  const { next } = await searchParams;
  const raw = Array.isArray(next) ? next[0] : next;
  const safe = safeNext(raw, "");
  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 p-6">
      <div className="flex justify-end">
        <LanguageSwitch />
      </div>
      <LoginHeading />
      <LoginForm next={safe || null} />
    </main>
  );
}
