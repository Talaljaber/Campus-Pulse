"use client";

import { useRef, useState, type FormEvent } from "react";
import { useSignIn, type SignInError } from "@/hooks/useSignIn";
import { useT, type DictKey } from "@/i18n";
import { DEMO_ACCOUNTS, toLoginEmail } from "@/lib/auth/demo";
import type { LoginAs } from "@/lib/auth/signin";
import { Button } from "../ui/Button";
import { InfoPanel } from "../ui/InfoPanel";
import { LanguageSwitch } from "../ui/LanguageSwitch";
import { TextField } from "../ui/TextField";

const ERROR_KEY: Record<SignInError, DictKey> = {
  invalid: "auth.errorInvalid",
  no_profile: "auth.errorNoProfile",
  network: "auth.errorNetwork",
  wrong_role: "login.wrongRole",
};

/** Props for {@link LoginForm}. */
export interface LoginFormProps {
  /** Where to go after signing in (`?next=`), already known to be a same-origin path or null. */
  next?: string | null;
}

/**
 * The portal login card: username and password, then "Log in as student" or "Log in as staff". A bare
 * username becomes `<username>@demo.local`; the role must fit the button that was pressed, otherwise
 * the session is dropped and `login.wrongRole` is shown. Enter in a field presses the first button
 * (student). The demo chips only fill the username and move focus to the password: the shared demo
 * password is typed by the presenter and is never in code. `NEXT_PUBLIC_DEMO_LOGIN_HINT` may show a
 * reminder, never the password itself.
 */
export function LoginForm({ next }: LoginFormProps) {
  const t = useT();
  const { submit, pending, error } = useSignIn(next);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const passwordRef = useRef<HTMLInputElement>(null);
  const [pressed, setPressed] = useState<LoginAs>("student");
  const pressedRef = useRef<LoginAs>("student");
  const hint = process.env.NEXT_PUBLIC_DEMO_LOGIN_HINT;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submit(toLoginEmail(username), password, pressedRef.current);
  };
  const ready = username.trim() !== "" && password !== "";

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-4">
      <LanguageSwitch className="self-end" />
      <form onSubmit={onSubmit} className="flex flex-col gap-4 border border-line-strong bg-surface-0 p-5 shadow-1" noValidate>
        <TextField
          label={t("login.username")}
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          dir="ltr"
        />
        <TextField
          ref={passwordRef}
          label={t("login.password")}
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
        <div className="flex flex-col gap-2 sm:flex-row">
          {(["student", "staff"] as const).map((as) => (
            <Button
              key={as}
              type="submit"
              loading={pending && pressed === as}
              disabled={!ready || pending}
              onClick={() => {
                pressedRef.current = as;
                setPressed(as);
              }}
              className="flex-1"
            >
              {t(as === "student" ? "login.asStudent" : "login.asStaff")}
            </Button>
          ))}
        </div>
        <p className="text-sm font-medium text-orange-ink">{t("login.note")}</p>
      </form>

      <InfoPanel title={t("login.demoTitle")}>
        <p className="text-sm text-fg-2">{t("login.demoHelp")}</p>
        {hint && <p className="text-sm text-fg-3">{t("auth.hint", { hint })}</p>}
        <ul className="flex flex-wrap gap-2">
          {DEMO_ACCOUNTS.map((a) => (
            <li key={a.username}>
              <button
                type="button"
                data-demo-user={a.username}
                onClick={() => {
                  setUsername(a.username);
                  passwordRef.current?.focus();
                }}
                className="inline-flex min-h-9 items-center rounded-md border border-line-strong bg-surface-0 px-3 text-sm font-semibold text-accent hover:border-accent hover:bg-surface-1"
              >
                {a.username}
              </button>
            </li>
          ))}
        </ul>
      </InfoPanel>
    </div>
  );
}
