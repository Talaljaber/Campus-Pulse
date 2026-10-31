import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { useT } from "@/i18n";
import { LanguageSwitch } from "../LanguageSwitch";
import { RtlProvider } from "../RtlProvider";

function Probe() {
  const t = useT();
  return <p>{t("common.close")}</p>;
}

describe("RtlProvider + LanguageSwitch", () => {
  it("sets html lang/dir and translates after switching to Arabic", async () => {
    render(
      <RtlProvider lang="en">
        <LanguageSwitch />
        <Probe />
      </RtlProvider>,
    );
    expect(screen.getByText("Close")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /العربية/ }));
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(screen.getByText("إغلاق")).toBeInTheDocument();
    expect(document.cookie).toContain("cp_lang=ar");
    expect(screen.getByRole("button", { name: /العربية/ })).toHaveAttribute("aria-pressed", "true");
  });
});
