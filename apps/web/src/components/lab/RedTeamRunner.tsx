"use client";

import { useState, type FormEvent } from "react";
import { useT, type DictKey } from "@/i18n";
import type { RedTeamRunRequest } from "@/lib/ai/types";
import {
  RED_TEAM_DEFAULT_N,
  RED_TEAM_DEFAULT_SEED,
  RED_TEAM_MAX_N,
  RED_TEAM_STYLES,
  redTeamRequest,
  validRedTeamN,
} from "@/lib/lab/redteam";
import { Button } from "../ui/Button";
import { TextField } from "../ui/TextField";

/** Props for {@link RedTeamRunner}. */
export interface RedTeamRunnerProps {
  /** True while a run is in flight; the button is busy and further submits are ignored. */
  running: boolean;
  /** Called with a validated request. The parent runs it and shows the scorecard. */
  onRun: (req: RedTeamRunRequest) => void;
}

const WHOLE = /^-?\d+$/;

/**
 * The red-team form: which attack styles, how many attacks (1 to 200) and the seed. It checks the
 * inputs itself and tells the admin what is wrong in words next to the field, then hands a valid
 * request to the parent. Choosing every style sends no style list, which the service reads as "all".
 */
export function RedTeamRunner({ running, onRun }: RedTeamRunnerProps) {
  const t = useT();
  const [styles, setStyles] = useState<ReadonlySet<string>>(new Set(RED_TEAM_STYLES));
  const [nText, setNText] = useState(String(RED_TEAM_DEFAULT_N));
  const [seedText, setSeedText] = useState(String(RED_TEAM_DEFAULT_SEED));
  const [tried, setTried] = useState(false);

  const n = WHOLE.test(nText.trim()) ? Number(nText.trim()) : Number.NaN;
  const seed = WHOLE.test(seedText.trim()) ? Number(seedText.trim()) : Number.NaN;
  const nOk = validRedTeamN(n);
  const seedOk = Number.isSafeInteger(seed);
  const stylesOk = styles.size > 0;

  const toggle = (style: string) =>
    setStyles((cur) => {
      const next = new Set(cur);
      if (next.has(style)) next.delete(style);
      else next.add(style);
      return next;
    });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (running || !stylesOk || !nOk || !seedOk) return;
    onRun(redTeamRequest({ styles, n, seed }));
  };

  return (
    <section aria-label={t("lab.redteam.title")} className="flex flex-col gap-3">
      <h3 className="text-lg font-semibold">{t("lab.redteam.title")}</h3>
      <p className="text-fg-2">{t("lab.redteam.intro")}</p>
      <form onSubmit={submit} noValidate className="flex flex-col gap-4 rounded-lg border border-line bg-surface-1 p-4">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium text-fg-1">{t("lab.redteam.styles")}</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {RED_TEAM_STYLES.map((s) => (
              <label key={s} className="inline-flex min-h-11 items-center gap-2 text-fg-1">
                <input type="checkbox" className="size-5 accent-accent" checked={styles.has(s)} onChange={() => toggle(s)} />
                {t(`lab.redteam.style.${s}` as DictKey)}
              </label>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => setStyles(new Set(RED_TEAM_STYLES))}>
              {t("lab.redteam.selectAll")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setStyles(new Set())}>
              {t("lab.redteam.clearAll")}
            </Button>
          </div>
          {tried && !stylesOk && (
            <p role="alert" className="text-sm font-medium text-danger">
              {t("lab.redteam.needStyle")}
            </p>
          )}
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label={t("lab.redteam.n")}
            inputMode="numeric"
            autoComplete="off"
            value={nText}
            onChange={(e) => setNText(e.target.value)}
            aria-invalid={tried && !nOk ? true : undefined}
            description={tried && !nOk ? t("lab.redteam.invalidN", { max: RED_TEAM_MAX_N }) : t("lab.redteam.nHint", { max: RED_TEAM_MAX_N })}
          />
          <TextField
            label={t("lab.redteam.seed")}
            inputMode="numeric"
            autoComplete="off"
            value={seedText}
            onChange={(e) => setSeedText(e.target.value)}
            aria-invalid={tried && !seedOk ? true : undefined}
            description={tried && !seedOk ? t("lab.redteam.invalidSeed") : t("lab.redteam.seedHint")}
          />
        </div>

        <div>
          <Button type="submit" loading={running}>
            {running ? t("lab.redteam.running") : t("lab.redteam.run")}
          </Button>
        </div>
      </form>
    </section>
  );
}
