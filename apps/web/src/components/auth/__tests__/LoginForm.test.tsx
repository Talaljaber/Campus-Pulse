import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const submit = vi.fn();
let hookState = { pending: false, error: null as null | "invalid" | "no_profile" | "network" | "wrong_role" };

vi.mock("@/hooks/useSignIn", () => ({
  useSignIn: () => ({ submit, ...hookState }),
}));

import { LoginForm } from "../LoginForm";
import { ServiceBanner } from "../../ui/ServiceBanner";

beforeEach(() => {
  submit.mockReset();
  hookState = { pending: false, error: null };
});

describe("LoginForm", () => {
  it("offers the ten demo usernames (no advisor) and each one fills only the username", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    const username = screen.getByLabelText("Username") as HTMLInputElement;
    const password = screen.getByLabelText("Password") as HTMLInputElement;
    for (const name of ["talal", "lina", "omar", "registrar", "it", "finance", "transport", "facilities", "academic", "admin"]) {
      await user.click(screen.getByRole("button", { name }));
      expect(username.value).toBe(name);
    }
    expect(screen.queryByRole("button", { name: "advisor" })).toBeNull();
    expect(password.value).toBe("");
    expect(password).toHaveFocus();
  });

  it("keeps both buttons off until both fields are filled", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    expect(screen.getByRole("button", { name: "Log in as student" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Log in as staff" })).toBeDisabled();
    await user.type(screen.getByLabelText("Username"), "talal");
    await user.type(screen.getByLabelText("Password"), "typed-by-hand");
    expect(screen.getByRole("button", { name: "Log in as student" })).toBeEnabled();
  });

  it("turns a bare username into <username>@demo.local and passes the pressed role", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.type(screen.getByLabelText("Username"), "it");
    await user.type(screen.getByLabelText("Password"), "typed-by-hand");
    await user.click(screen.getByRole("button", { name: "Log in as staff" }));
    expect(submit).toHaveBeenLastCalledWith("it@demo.local", "typed-by-hand", "staff");
    await user.click(screen.getByRole("button", { name: "Log in as student" }));
    expect(submit).toHaveBeenLastCalledWith("it@demo.local", "typed-by-hand", "student");
  });

  it("keeps an email as typed, and Enter in the password field logs in as student", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.type(screen.getByLabelText("Username"), "someone@demo.local");
    await user.type(screen.getByLabelText("Password"), "pw{Enter}");
    expect(submit).toHaveBeenCalledWith("someone@demo.local", "pw", "student");
  });

  it("shows the wrong-role message in an alert", () => {
    hookState = { pending: false, error: "wrong_role" };
    render(<LoginForm />);
    expect(screen.getByRole("alert")).toHaveTextContent("cannot log in with that button");
  });

  it("shows a translated alert for a failed sign-in", () => {
    hookState = { pending: false, error: "invalid" };
    render(<LoginForm />);
    expect(screen.getByRole("alert")).toHaveTextContent("The email or the password is wrong.");
  });

  it("shows the simulated login note and never renders a password value", () => {
    const { container } = render(<LoginForm />);
    expect(screen.getByText("Simulated university login: fictional accounts only.")).toBeInTheDocument();
    expect(container.innerHTML).not.toMatch(/value="[^"]+"/);
  });
});

describe("ServiceBanner", () => {
  it("renders nothing visible when ok, but keeps the live region", () => {
    render(<ServiceBanner state="ok" />);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });
  it("announces waking and down in the status region", () => {
    const { rerender } = render(<ServiceBanner state="waking" />);
    expect(screen.getByRole("status")).toHaveTextContent("waking up");
    rerender(<ServiceBanner state="down" />);
    expect(screen.getByRole("status")).toHaveTextContent("not available");
  });
});
