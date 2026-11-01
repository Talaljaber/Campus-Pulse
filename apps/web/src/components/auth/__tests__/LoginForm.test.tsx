import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const submit = vi.fn();
let hookState = { pending: false, error: null as null | "invalid" | "no_profile" | "network" };

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
  it("offers the four demo accounts and each one fills only the email", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    const email = screen.getByLabelText("Email") as HTMLInputElement;
    const password = screen.getByLabelText("Password") as HTMLInputElement;

    await user.click(screen.getByRole("button", { name: "Sign in as Student" }));
    expect(email.value).toBe("talal@demo.local");
    expect(password.value).toBe("");
    expect(password).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Sign in as IT staff" }));
    expect(email.value).toBe("it@demo.local");
    await user.click(screen.getByRole("button", { name: "Sign in as Advisor" }));
    expect(email.value).toBe("advisor@demo.local");
    await user.click(screen.getByRole("button", { name: "Sign in as Admin" }));
    expect(email.value).toBe("admin@demo.local");
    expect(password.value).toBe("");
  });

  it("keeps the submit button off until both fields are filled, then submits", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    const go = screen.getByRole("button", { name: "Sign in" });
    expect(go).toBeDisabled();
    await user.type(screen.getByLabelText("Email"), "it@demo.local");
    await user.type(screen.getByLabelText("Password"), "typed-by-hand{Enter}");
    expect(submit).toHaveBeenCalledWith("it@demo.local", "typed-by-hand");
  });

  it("shows a translated alert for a failed sign-in", () => {
    hookState = { pending: false, error: "invalid" };
    render(<LoginForm />);
    expect(screen.getByRole("alert")).toHaveTextContent("The email or the password is wrong.");
  });

  it("never renders a password value", () => {
    const { container } = render(<LoginForm />);
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
