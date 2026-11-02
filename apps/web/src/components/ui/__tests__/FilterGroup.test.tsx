import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { FilterGroup } from "../FilterGroup";

describe("FilterGroup", () => {
  it("is a fieldset named by the default legend, with children and a Search button", () => {
    render(
      <FilterGroup onSubmit={() => {}}>
        <input aria-label="Status" />
      </FilterGroup>,
    );
    expect(screen.getByRole("group", { name: "Filtering criteria" })).toBeInTheDocument();
    expect(screen.getByLabelText("Status")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Search" })).toHaveAttribute("type", "submit");
    expect(screen.queryByRole("button", { name: "Reset" })).toBeNull();
  });

  it("submits on the Search button and on Enter in a field, and resets without submitting", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const onReset = vi.fn();
    render(
      <FilterGroup legend="Tickets" onSubmit={onSubmit} onReset={onReset}>
        <input aria-label="Text" />
      </FilterGroup>,
    );
    expect(screen.getByRole("group", { name: "Tickets" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    await user.type(screen.getByLabelText("Text"), "x{Enter}");
    expect(onSubmit).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(onReset).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledTimes(2);
  });

  it("is translated in Arabic", () => {
    render(
      <LangScope lang="ar">
        <FilterGroup onSubmit={() => {}} onReset={() => {}}>
          <input aria-label="x" />
        </FilterGroup>
      </LangScope>,
    );
    expect(screen.getByRole("group", { name: "معايير التصفية" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "بحث" })).toBeInTheDocument();
  });
});
