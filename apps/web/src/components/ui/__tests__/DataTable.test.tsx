import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DataTable, sortRows, type Column, type SortState } from "../DataTable";

interface Row {
  id: string;
  name: string;
  due: number;
}

const ROWS: Row[] = [
  { id: "a", name: "banana", due: 30 },
  { id: "b", name: "Apple", due: 10 },
  { id: "c", name: "cherry", due: 20 },
];

const COLUMNS: Column<Row>[] = [
  { id: "name", header: "Name", cell: (r) => r.name, sortValue: (r) => r.name },
  { id: "due", header: "Due", cell: (r) => String(r.due), sortValue: (r) => r.due, align: "end" },
  { id: "note", header: "Note", cell: () => "-" },
];

describe("sortRows", () => {
  it("sorts numbers numerically and text case-insensitively, both ways", () => {
    expect(sortRows(ROWS, COLUMNS, { columnId: "due", dir: "asc" }).map((r) => r.id)).toEqual(["b", "c", "a"]);
    expect(sortRows(ROWS, COLUMNS, { columnId: "due", dir: "desc" }).map((r) => r.id)).toEqual(["a", "c", "b"]);
    expect(sortRows(ROWS, COLUMNS, { columnId: "name", dir: "asc" }).map((r) => r.id)).toEqual(["b", "a", "c"]);
  });

  it("is stable for equal values and never mutates the input", () => {
    const rows = [
      { id: "1", name: "x", due: 5 },
      { id: "2", name: "y", due: 5 },
      { id: "3", name: "z", due: 1 },
    ];
    const copy = [...rows];
    expect(sortRows(rows, COLUMNS, { columnId: "due", dir: "asc" }).map((r) => r.id)).toEqual(["3", "1", "2"]);
    expect(sortRows(rows, COLUMNS, { columnId: "due", dir: "desc" }).map((r) => r.id)).toEqual(["1", "2", "3"]);
    expect(rows).toEqual(copy);
  });

  it("keeps the original order with no sort, an unknown column or a column without sortValue", () => {
    const ids = ROWS.map((r) => r.id);
    expect(sortRows(ROWS, COLUMNS, null).map((r) => r.id)).toEqual(ids);
    expect(sortRows(ROWS, COLUMNS, { columnId: "nope", dir: "asc" }).map((r) => r.id)).toEqual(ids);
    expect(sortRows(ROWS, COLUMNS, { columnId: "note", dir: "asc" }).map((r) => r.id)).toEqual(ids);
  });
});

function Harness({ onRowClick }: { onRowClick?: (r: Row) => void }) {
  const [sort, setSort] = useState<SortState>(null);
  return (
    <DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} sort={sort} onSortChange={setSort} onRowClick={onRowClick} caption="Fruit" />
  );
}

const bodyNames = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((tr) => within(tr).getAllByRole("cell")[0]!.textContent);

describe("DataTable", () => {
  it("toggles the sort and sets aria-sort on the active column only", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const nameTh = screen.getByRole("columnheader", { name: "Name" });
    const dueTh = screen.getByRole("columnheader", { name: "Due" });
    expect(nameTh).not.toHaveAttribute("aria-sort");

    await user.click(within(dueTh).getByRole("button"));
    expect(dueTh).toHaveAttribute("aria-sort", "ascending");
    expect(nameTh).not.toHaveAttribute("aria-sort");
    expect(bodyNames()).toEqual(["Apple", "cherry", "banana"]);

    await user.click(within(dueTh).getByRole("button"));
    expect(dueTh).toHaveAttribute("aria-sort", "descending");
    expect(bodyNames()).toEqual(["banana", "cherry", "Apple"]);

    await user.click(within(nameTh).getByRole("button"));
    expect(nameTh).toHaveAttribute("aria-sort", "ascending");
    expect(dueTh).not.toHaveAttribute("aria-sort");
  });

  it("gives a column without sortValue a plain header", () => {
    render(<Harness />);
    expect(within(screen.getByRole("columnheader", { name: "Note" })).queryByRole("button")).toBeNull();
  });

  it("calls onRowClick on click and on Enter for a focused row, but not for Enter inside a button", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    render(
      <DataTable
        columns={[...COLUMNS, { id: "x", header: "Action", cell: () => <button type="button">Go</button> }]}
        rows={ROWS}
        rowKey={(r) => r.id}
        sort={null}
        onSortChange={() => {}}
        onRowClick={onRowClick}
        caption="Fruit"
      />,
    );
    const first = screen.getAllByRole("row")[1]!;
    await user.click(within(first).getAllByRole("cell")[0]!);
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);

    onRowClick.mockClear();
    first.focus();
    await user.keyboard("{Enter}");
    expect(onRowClick).toHaveBeenCalledTimes(1);

    onRowClick.mockClear();
    within(first).getByRole("button", { name: "Go" }).focus();
    await user.keyboard("{Enter}");
    expect(onRowClick).not.toHaveBeenCalled();
    await user.click(within(first).getByRole("button", { name: "Go" }));
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("makes rows focusable only when they are clickable, and shows the empty text", () => {
    const { rerender } = render(<Harness />);
    expect(screen.getAllByRole("row")[1]).not.toHaveAttribute("tabindex");
    rerender(<Harness onRowClick={() => {}} />);
    expect(screen.getAllByRole("row")[1]).toHaveAttribute("tabindex", "0");
    rerender(<DataTable columns={COLUMNS} rows={[]} rowKey={(r) => r.id} sort={null} onSortChange={() => {}} caption="Fruit" />);
    expect(screen.getByText("No rows to show")).toBeInTheDocument();
  });

  describe("on a phone", () => {
    const realMatchMedia = window.matchMedia;
    beforeEach(() => {
      window.matchMedia = ((query: string) => ({
        matches: true,
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      })) as unknown as typeof window.matchMedia;
    });
    afterEach(() => {
      window.matchMedia = realMatchMedia;
    });

    it("renders cards with the primary columns and hides the rest behind Show details", async () => {
      const user = userEvent.setup();
      const cols: Column<Row>[] = [
        { id: "name", header: "Name", primary: true, cell: (r) => r.name, sortValue: (r) => r.name },
        { id: "due", header: "Due", cell: (r) => `due ${r.due}`, sortValue: (r) => r.due },
      ];
      render(<DataTable columns={cols} rows={ROWS} rowKey={(r) => r.id} sort={null} onSortChange={() => {}} caption="Fruit" />);
      expect(screen.queryByRole("table")).toBeNull();
      expect(screen.getAllByRole("listitem")).toHaveLength(3);
      expect(screen.getByText("banana")).toBeInTheDocument();
      expect(screen.queryByText("due 30")).toBeNull();
      const first = screen.getAllByRole("button", { name: "Show details" })[0]!;
      await user.click(first);
      expect(first).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText("due 30")).toBeInTheDocument();
      expect(screen.getByText("Due", { selector: "dt" })).toBeInTheDocument();
    });

    it("sorts through the select and opens a row from its card", async () => {
      const user = userEvent.setup();
      const onSortChange = vi.fn();
      const onRowClick = vi.fn();
      render(
        <DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} sort={null} onSortChange={onSortChange} onRowClick={onRowClick} caption="Fruit" />,
      );
      await user.selectOptions(screen.getByRole("combobox", { name: "Sort by" }), "due");
      expect(onSortChange).toHaveBeenCalledWith({ columnId: "due", dir: "asc" });
      await user.click(screen.getByText("banana"));
      expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
    });
  });
});
