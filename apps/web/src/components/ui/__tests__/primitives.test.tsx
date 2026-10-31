import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { Badge } from "../Badge";
import { Button } from "../Button";
import { Card } from "../Card";
import { ChipGroup } from "../Chip";
import { Dialog } from "../Dialog";
import { EmptyState } from "../EmptyState";
import { Skeleton } from "../Skeleton";
import { Table } from "../Table";
import { TabPanel, Tabs } from "../Tabs";
import { ToastProvider, useToast } from "../Toast";

describe("Button", () => {
  it("defaults to type=button, forwards ref and fires onClick", async () => {
    const ref = createRef<HTMLButtonElement>();
    const onClick = vi.fn();
    render(<Button ref={ref} onClick={onClick}>Go</Button>);
    const btn = screen.getByRole("button", { name: "Go" });
    expect(btn).toHaveAttribute("type", "button");
    expect(ref.current).toBe(btn);
    await userEvent.click(btn);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("loading disables, sets aria-busy and blocks clicks", async () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Save</Button>);
    const btn = screen.getByRole("button", { name: "Save" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
    await userEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("is activated by keyboard", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Key</Button>);
    await userEvent.tab();
    await userEvent.keyboard("{Enter}");
    await userEvent.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});

describe("Badge", () => {
  it("shows a priority icon by default and keeps the text", () => {
    const { container } = render(<Badge tone="pri-high">High</Badge>);
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
  it("allows removing the icon", () => {
    const { container } = render(<Badge tone="pri-high" icon={null}>High</Badge>);
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("ChipGroup", () => {
  const items = [
    { id: "a", label: "Alpha" },
    { id: "b", label: "Beta" },
    { id: "c", label: "Gamma" },
  ];
  function Harness({ initial = null as string | null, dir = "ltr" as "ltr" | "rtl" }) {
    const [v, setV] = useState<string | null>(initial);
    return (
      <div dir={dir}>
        <ChipGroup label="Pick" items={items} value={v} onChange={setV} />
      </div>
    );
  }

  it("is a labelled radiogroup with a single tab stop", () => {
    render(<Harness initial="b" />);
    const group = screen.getByRole("radiogroup", { name: "Pick" });
    const radios = within(group).getAllByRole("radio");
    expect(radios.map((r) => r.getAttribute("tabindex"))).toEqual(["-1", "0", "-1"]);
    expect(screen.getByRole("radio", { name: "Beta" })).toBeChecked();
  });

  it("arrow keys move selection and focus (LTR)", async () => {
    render(<Harness initial="a" />);
    screen.getByRole("radio", { name: "Alpha" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Beta" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Beta" })).toHaveFocus();
  });

  it("arrow keys are mirrored in RTL", async () => {
    render(<Harness initial="b" dir="rtl" />);
    screen.getByRole("radio", { name: "Beta" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Alpha" })).toBeChecked();
  });
});

describe("Tabs", () => {
  function Harness() {
    const [v, setV] = useState("one");
    return (
      <>
        <Tabs idBase="t" label="Sections" value={v} onChange={setV} items={[{ id: "one", label: "One" }, { id: "two", label: "Two" }]} />
        <TabPanel idBase="t" id="one" value={v}>first</TabPanel>
        <TabPanel idBase="t" id="two" value={v}>second</TabPanel>
      </>
    );
  }
  it("links tabs to panels and switches with the keyboard", async () => {
    render(<Harness />);
    const one = screen.getByRole("tab", { name: "One" });
    expect(one).toHaveAttribute("aria-selected", "true");
    expect(one).toHaveAttribute("aria-controls", "t-panel-one");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("first");
    one.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Two" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("second");
  });
});

describe("Table", () => {
  type Row = { id: string; name: string };
  const cols = [{ key: "name", header: "Name" }, { key: "x", header: "X", align: "end" as const, render: (r: Row) => r.id }];
  it("renders headers with scope and rows", () => {
    render(<Table columns={cols} rows={[{ id: "1", name: "Ada" }]} rowKey={(r) => r.id} caption="People" />);
    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute("scope", "col");
    expect(screen.getByRole("cell", { name: "Ada" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "People" })).toBeInTheDocument();
  });
  it("shows a translated empty message in Arabic", () => {
    render(
      <LangScope lang="ar">
        <Table columns={cols} rows={[]} rowKey={(r: Row) => r.id} />
      </LangScope>,
    );
    expect(screen.getByText("ما في صفوف للعرض")).toBeInTheDocument();
  });
});

describe("Toast", () => {
  function Trigger({ ms }: { ms?: number }) {
    const { show } = useToast();
    return <button onClick={() => show("Saved", "ok", ms)}>fire</button>;
  }
  it("announces via a polite live region and dismisses on demand", async () => {
    render(<ToastProvider><Trigger /></ToastProvider>);
    await userEvent.click(screen.getByText("fire"));
    const msg = screen.getByText("Saved");
    expect(msg.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(screen.queryByText("Saved")).toBeNull();
  });
  it("auto-dismisses after the delay", () => {
    vi.useFakeTimers();
    try {
      render(<ToastProvider><Trigger ms={1000} /></ToastProvider>);
      act(() => screen.getByText("fire").click());
      expect(screen.getByText("Saved")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(1100));
      expect(screen.queryByText("Saved")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("Dialog", () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>open</button>
        <Dialog open={open} onClose={() => setOpen(false)} title="Sure?">
          <button>inner</button>
        </Dialog>
      </>
    );
  }
  it("is named by its title, traps focus, closes on Escape and restores focus", async () => {
    render(<Harness />);
    const opener = screen.getByText("open");
    await userEvent.click(opener);
    const dlg = screen.getByRole("dialog", { name: "Sure?" });
    expect(dlg).toHaveAttribute("aria-modal", "true");
    const close = within(dlg).getByRole("button", { name: "Close dialog" });
    const inner = within(dlg).getByText("inner");
    expect(close).toHaveFocus();
    inner.focus();
    await userEvent.tab();
    expect(dlg.contains(document.activeElement)).toBe(true);
    await userEvent.tab({ shift: true });
    expect(dlg.contains(document.activeElement)).toBe(true);
    close.focus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });
});

describe("Skeleton, EmptyState and Card", () => {
  it("Skeleton exposes one status and hides bars", () => {
    const { container } = render(<Skeleton lines={4} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading content");
    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(4);
  });
  it("EmptyState renders title, hint and action", () => {
    render(<EmptyState title="Empty" hint="Soon" action={<button>Go</button>} />);
    expect(screen.getByText("Empty")).toBeInTheDocument();
    expect(screen.getByText("Soon")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });
  it("Card with a title is a labelled region", () => {
    render(<Card title="Stats">body</Card>);
    expect(screen.getByRole("region", { name: "Stats" })).toHaveTextContent("body");
  });
});
