import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import { FIXTURE_DOTS, FIXTURE_RINGS } from "@/lib/fixtures/map";
import { BuildingShape } from "../BuildingShape";
import { CampusMap } from "../CampusMap";
import { FIXTURE_BUILDINGS, dotPosition, footprintOf, tidyLabel } from "../campus";
import { IncidentRing } from "../IncidentRing";
import { MapLegend } from "../MapLegend";
import { RequestDot } from "../RequestDot";

function mockReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    (query: string) => ({
      matches: reduce && query.includes("reduce"),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("campus fixture", () => {
  it("has the buildings A to M without I and J, all on the 1000x600 grid inside the map", () => {
    expect(FIXTURE_BUILDINGS.map((b) => b.code)).toEqual(["A", "B", "C", "D", "E", "F", "G", "H", "K", "L", "M"]);
    for (const b of FIXTURE_BUILDINGS) {
      const { w, h } = footprintOf(b.code);
      expect(b.map_x! - w / 2).toBeGreaterThanOrEqual(0);
      expect(b.map_x! + w / 2).toBeLessThanOrEqual(1000);
      expect(b.map_y! - h / 2).toBeGreaterThanOrEqual(0);
      expect(b.map_y! + h / 2).toBeLessThanOrEqual(600);
    }
  });

  it("places no two footprints on top of each other", () => {
    const boxes = FIXTURE_BUILDINGS.map((b) => {
      const { w, h } = footprintOf(b.code);
      return { code: b.code, l: b.map_x! - w / 2, r: b.map_x! + w / 2, t: b.map_y! - h / 2, bt: b.map_y! + h / 2 };
    });
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i]!;
        const c = boxes[j]!;
        const overlap = a.l < c.r && c.l < a.r && a.t < c.bt && c.t < a.bt;
        expect(overlap, `${a.code} overlaps ${c.code}`).toBe(false);
      }
    }
  });
});

describe("dotPosition", () => {
  const m = FIXTURE_BUILDINGS.find((b) => b.code === "M")!;

  it("is deterministic and stays inside the footprint", () => {
    const a = dotPosition(m, "req-1")!;
    expect(dotPosition(m, "req-1")).toEqual(a);
    expect(dotPosition(m, "req-2")).not.toEqual(a);
    const { w, h } = footprintOf("M");
    for (let i = 0; i < 200; i++) {
      const p = dotPosition(m, `req-${i}`)!;
      expect(Math.abs(p.x - m.map_x!)).toBeLessThanOrEqual(w / 2);
      expect(Math.abs(p.y - m.map_y!)).toBeLessThanOrEqual(h / 2);
    }
  });

  it("returns null for a building without coordinates", () => {
    expect(dotPosition({ code: "Z", map_x: null, map_y: null }, "x")).toBeNull();
  });
});

describe("CampusMap", () => {
  it("is one named image with a description and the fixed 1000x600 viewBox", () => {
    render(<CampusMap buildings={FIXTURE_BUILDINGS} />);
    const map = screen.getByRole("img", { name: "Campus map" });
    expect(map.tagName.toLowerCase()).toBe("svg");
    expect(map).toHaveAttribute("viewBox", "0 0 1000 600");
    expect(map).toHaveAccessibleDescription(/11 buildings/);
    expect(within(map).getAllByRole("img")).toHaveLength(11);
  });

  it("skips buildings that have no coordinates", () => {
    render(<CampusMap buildings={[...FIXTURE_BUILDINGS, { id: "Z", code: "Z", name_en: "Zed", name_ar: "زد", map_x: null, map_y: null }]} />);
    expect(screen.queryByLabelText(/Building Z/)).not.toBeInTheDocument();
  });

  it("does not mirror the geometry in Arabic: same viewBox, dir=ltr and identical shapes", () => {
    const { container: en } = render(<CampusMap buildings={FIXTURE_BUILDINGS} />);
    const enRects = [...en.querySelectorAll("rect")].map((r) => [r.getAttribute("x"), r.getAttribute("y")].join());
    const { container: ar } = render(
      <LangScope lang="ar">
        <CampusMap buildings={FIXTURE_BUILDINGS} />
      </LangScope>,
    );
    const svg = ar.querySelector("svg")!;
    expect(svg).toHaveAttribute("dir", "ltr");
    expect(svg).toHaveAttribute("viewBox", "0 0 1000 600");
    expect([...ar.querySelectorAll("rect")].map((r) => [r.getAttribute("x"), r.getAttribute("y")].join())).toEqual(enRects);
    // ...while the labels are Arabic, in a right-to-left run.
    expect(within(svg as unknown as HTMLElement).getByLabelText("المبنى M")).toBeInTheDocument();
    expect(svg.querySelector('[data-building="M"] g')).toHaveStyle({ direction: "rtl" });
  });

  it("with onBuildingClick, buildings are keyboard buttons inside a named group", async () => {
    const onBuildingClick = vi.fn();
    const user = userEvent.setup();
    render(<CampusMap buildings={FIXTURE_BUILDINGS} onBuildingClick={onBuildingClick} selected="C" />);
    expect(screen.getByRole("group", { name: "Campus map" })).toBeInTheDocument();
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(11);

    await user.tab();
    expect(buttons[0]).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onBuildingClick).toHaveBeenLastCalledWith("A");
    await user.keyboard(" ");
    expect(onBuildingClick).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole("button", { name: "Building M" }));
    expect(onBuildingClick).toHaveBeenLastCalledWith("M");
    expect(onBuildingClick).toHaveBeenCalledTimes(3);

    const selected = screen.getByRole("button", { name: "Building C, selected" });
    expect(selected).toHaveAttribute("aria-pressed", "true");
    // only L, the library, has a name
    expect(screen.getByRole("button", { name: "Building L, Library" })).toBeInTheDocument();
    expect(screen.getByText("Library")).toBeInTheDocument();
  });

  it("tidyLabel drops the separator an empty name leaves, in both languages", () => {
    expect(tidyLabel("Building M, ")).toBe("Building M");
    expect(tidyLabel("Building M, , selected")).toBe("Building M, selected");
    expect(tidyLabel("المبنى M، ")).toBe("المبنى M");
    expect(tidyLabel("Building L, Library")).toBe("Building L, Library");
  });

  it("draws overlay children above the buildings: 20 fixture dots and the incident ring", () => {
    mockReducedMotion(false);
    render(
      <CampusMap buildings={FIXTURE_BUILDINGS}>
        {FIXTURE_DOTS.map((d) => (
          <RequestDot key={d.id} x={d.x} y={d.y} category={d.category} priority={d.priority} simulated={d.simulated} />
        ))}
        {FIXTURE_RINGS.map((r) => (
          <IncidentRing key={r.id} x={r.x} y={r.y} priority={r.priority} reportCount={r.reportCount} />
        ))}
      </CampusMap>,
    );
    expect(FIXTURE_DOTS).toHaveLength(20);
    expect(screen.getAllByRole("img", { name: /priority request/ })).toHaveLength(20);
    expect(screen.getByRole("img", { name: "Incident with 4 reports, High priority" })).toBeInTheDocument();
  });
});

describe("BuildingShape", () => {
  it("renders nothing without coordinates", () => {
    const { container } = render(
      <svg>
        <BuildingShape b={{ id: "Z", code: "Z", name_en: "Zed", name_ar: "زد", map_x: 5, map_y: null }} />
      </svg>,
    );
    expect(container.querySelector("g")).toBeNull();
  });
});

describe("RequestDot", () => {
  const radius = (priority: string) =>
    Number(
      render(
        <svg>
          <RequestDot x={10} y={20} category="IT Support" priority={priority} />
        </svg>,
      ).container.querySelector("circle")!.getAttribute("r"),
    );

  it("sizes the dot by priority: 4, 6 and 9", () => {
    expect([radius("low"), radius("medium"), radius("high")]).toEqual([4, 6, 9]);
  });

  it("colours by category, has an accessible name, and marks simulated dots", () => {
    const { container, rerender } = render(
      <svg>
        <RequestDot x={1} y={2} category="Finance" priority="high" />
      </svg>,
    );
    const real = container.querySelector("circle")!;
    expect(real).toHaveAttribute("fill", "var(--cp-cat-finance)");
    expect(real).toHaveAccessibleName("Finance, High priority request");
    expect(real).not.toHaveAttribute("stroke-dasharray");
    rerender(
      <svg>
        <RequestDot x={1} y={2} category="Finance" priority="high" simulated />
      </svg>,
    );
    const sim = container.querySelector("circle")!;
    expect(sim).toHaveAccessibleName("Finance, High priority request (simulated)");
    expect(sim).toHaveAttribute("stroke-dasharray");
  });

  it("names the dot in Arabic", () => {
    render(
      <LangScope lang="ar">
        <svg>
          <RequestDot x={1} y={2} category="Finance" priority="low" />
        </svg>
      </LangScope>,
    );
    expect(screen.getByRole("img")).toHaveAccessibleName(/^طلب .*أولوية /);
  });
});

describe("IncidentRing", () => {
  it("pulses by default and is named with its report count", () => {
    mockReducedMotion(false);
    const { container } = render(
      <svg>
        <IncidentRing x={50} y={60} priority="high" reportCount={4} />
      </svg>,
    );
    expect(screen.getByRole("img", { name: "Incident with 4 reports, High priority" })).toHaveAttribute("data-animated", "true");
    expect(container.querySelector(".cp-ring-pulse")).not.toBeNull();
    expect(container.querySelectorAll("circle")).toHaveLength(2);
  });

  it("is a static ring under prefers-reduced-motion", () => {
    mockReducedMotion(true);
    const { container } = render(
      <svg>
        <IncidentRing x={50} y={60} priority="medium" reportCount={2} />
      </svg>,
    );
    expect(screen.getByRole("img")).toHaveAttribute("data-animated", "false");
    expect(container.querySelector(".cp-ring-pulse")).toBeNull();
    expect(container.querySelectorAll("circle")).toHaveLength(1);
  });

  it("grows with the number of reports, up to a cap", () => {
    mockReducedMotion(true);
    const r = (n: number) =>
      Number(
        render(
          <svg>
            <IncidentRing x={0} y={0} priority="low" reportCount={n} />
          </svg>,
        ).container.querySelector("circle")!.getAttribute("r"),
      );
    expect(r(1)).toBeLessThan(r(5));
    expect(r(10)).toBe(r(40));
  });
});

describe("MapLegend", () => {
  it("lists every category and priority and is a labelled region", () => {
    render(<MapLegend />);
    const legend = screen.getByRole("region", { name: "Map legend" });
    expect(within(legend).getAllByRole("listitem").length).toBeGreaterThanOrEqual(11);
    expect(within(legend).getByText("Academic Support")).toBeInTheDocument();
  });

  it("is plain HTML, so it follows the Arabic direction while the map stays fixed", () => {
    const { container } = render(
      <LangScope lang="ar">
        <MapLegend />
        <CampusMap buildings={FIXTURE_BUILDINGS} />
      </LangScope>,
    );
    expect(container.querySelector("section")!.closest("[dir]")).toHaveAttribute("dir", "rtl");
    expect(container.querySelector("svg[role=img]")).toHaveAttribute("dir", "ltr");
  });
});
