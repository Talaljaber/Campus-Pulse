"use client";

import { useRef, useState, type FormEvent } from "react";
import { useSignIn, type SignInError } from "@/hooks/useSignIn";
import { useT, type DictKey } from "@/i18n";
import { DEMO_ACCOUNTS } from "@/lib/auth/demo";
import { Button } from "../ui/Button";
import type { IconName } from "../ui/Icon";
import { IconTile } from "../ui/IconTile";
import { InfoPanel } from "../ui/InfoPanel";
import { TextField } from "../ui/TextField";

const ROLE_ICON: Record<string, IconName> = { student: "graduation", staff: "briefcase", advisor: "user", admin: "shield" };

const ERROR_KEY: Record<SignInError, DictKey> = {
  invalid: "auth.errorInvalid",
  no_profile: "auth.errorNoProfile",
  network: "auth.errorNetwork",
};

/** Props for {@link LoginForm}. */
export interface LoginFormProps {
  /** Where to go after signing in (`?next=`), already known to be a same-origin path or null. */
  next?: string | null;
}

/**
 * Email and password form plus the "Sign in as" demo buttons. A demo button only fills in
 * the email and moves focus to the password field: the shared demo password is typed by
 * the presenter and is never in code. `NEXT_PUBLIC_DEMO_LOGIN_HINT` may show a reminder,
 * never the password itself.
 */
export function LoginForm({ next }: LoginFormProps) {
  const t = useT();
  const { submit, pending, error } = useSignIn(next);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const passwordRef = useRef<HTMLInputElement>(null);
  const hint = process.env.NEXT_PUBLIC_DEMO_LOGIN_HINT;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submit(email, password);
  };

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <TextField
          label={t("auth.email")}
          type="email"
          name="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          dir="ltr"
        />
        <TextField
          ref={passwordRef}
          label={t("auth.password")}
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          dir="ltr"
        />
        {error && (
          <p role="alert" className="text-sm font-medium text-danger">
            {t(ERROR_KEY[error])}
          </p>
        )}
        <Button type="submit" loading={pending} disabled={!email || !password}>
          {t(pending ? "auth.submitting" : "auth.submit")}
        </Button>
      </form>

      <InfoPanel title={t("auth.demoTitle")}>
        <p className="text-sm text-fg-2">{t("auth.demoHelp")}</p>
        {hint && <p className="text-sm text-fg-3">{t("auth.hint", { hint })}</p>}
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {DEMO_ACCOUNTS.map((a) => (
            <li key={a.id}>
              <IconTile
                icon={ROLE_ICON[a.id] ?? "user"}
                tone={a.role === "student" ? "orange" : "grey"}
                data-demo-role={a.id}
                label={t("auth.signInAs", { name: t(a.labelKey) })}
                onClick={() => {
                  setEmail(a.email);
                  passwordRef.current?.focus();
                }}
              />
            </li>
          ))}
        </ul>
      </InfoPanel>
    </div>
  );
}
