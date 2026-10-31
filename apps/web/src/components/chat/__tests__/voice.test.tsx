import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LangScope } from "@/i18n";
import type { RecognitionLike, SpeechErrorEvent, SpeechResultEvent } from "@/lib/voice/speech";
import { ToastProvider } from "../../ui/Toast";
import { Composer } from "../Composer";
import { MicButton } from "../MicButton";

class FakeRecognition implements RecognitionLike {
  static last: FakeRecognition | null = null;
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  onresult: ((e: SpeechResultEvent) => void) | null = null;
  onerror: ((e: SpeechErrorEvent) => void) | null = null;
  onend: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn(() => this.onend?.());
  abort = vi.fn();
  constructor() {
    FakeRecognition.last = this;
  }
  say(text: string) {
    this.onresult?.({ results: [[{ transcript: text }]] });
  }
}
const win = window as unknown as { webkitSpeechRecognition?: unknown };

beforeEach(() => {
  FakeRecognition.last = null;
  win.webkitSpeechRecognition = FakeRecognition;
});
afterEach(() => {
  delete win.webkitSpeechRecognition;
});

function Composed({ onSubmit }: { onSubmit: (t: string, m: "text" | "voice") => void }) {
  return (
    <ToastProvider>
      <Composer
        busy={false}
        onSubmit={onSubmit}
        micSlot={(mic) => <MicButton lang="en-US" onStart={mic.begin} onTranscript={mic.apply} />}
      />
    </ToastProvider>
  );
}

describe("MicButton", () => {
  it("renders nothing where the browser has no Web Speech API", () => {
    delete win.webkitSpeechRecognition;
    render(<MicButton lang="en-US" onTranscript={() => {}} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("is a toggle button that names its language, and announces listening", async () => {
    const user = userEvent.setup();
    render(<MicButton lang="en-US" onTranscript={() => {}} />);
    const mic = screen.getByRole("button", { name: "Dictate in English" });
    expect(mic).toHaveAttribute("aria-pressed", "false");
    await user.click(mic);
    expect(FakeRecognition.last!.lang).toBe("en-US");
    expect(screen.getByRole("button", { name: "Stop listening" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Listening");
    await user.click(screen.getByRole("button", { name: "Stop listening" }));
    expect(screen.getByRole("button", { name: /Dictate/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("uses Jordanian Arabic when the page is Arabic", async () => {
    const user = userEvent.setup();
    render(
      <LangScope lang="ar">
        <MicButton lang="ar-JO" onTranscript={() => {}} />
      </LangScope>,
    );
    await user.click(screen.getByRole("button", { name: "املي بصوتك (العربي)" }));
    expect(FakeRecognition.last!.lang).toBe("ar-JO");
  });

  it("reports a blocked microphone with a toast", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <MicButton lang="en-US" onTranscript={() => {}} />
      </ToastProvider>,
    );
    await user.click(screen.getByRole("button", { name: /Dictate/ }));
    act(() => {
      FakeRecognition.last!.onerror?.({ error: "not-allowed" });
      FakeRecognition.last!.onend?.();
    });
    expect(await screen.findByText(/microphone is blocked/)).toBeInTheDocument();
  });

  it("stays quiet for an aborted session", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <MicButton lang="en-US" onTranscript={() => {}} />
      </ToastProvider>,
    );
    await user.click(screen.getByRole("button", { name: /Dictate/ }));
    act(() => FakeRecognition.last!.onerror?.({ error: "aborted" }));
    expect(screen.queryByText(/microphone|Nothing was heard|did not work/)).not.toBeInTheDocument();
  });
});

describe("Composer with voice", () => {
  it("puts the transcript in the box for confirmation and sends it as voice", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Composed onSubmit={onSubmit} />);
    await user.click(screen.getByRole("button", { name: /Dictate/ }));
    act(() => FakeRecognition.last!.say("the wifi in building M"));
    const box = screen.getByLabelText("Your request");
    expect(box).toHaveValue("the wifi in building M");
    expect(onSubmit).not.toHaveBeenCalled();

    // The student can still edit before sending.
    await user.type(box, " is down");
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect(onSubmit).toHaveBeenCalledWith("the wifi in building M is down", "voice");
    expect(box).toHaveValue("");
  });

  it("appends the transcript to text that was already typed", async () => {
    const user = userEvent.setup();
    render(<Composed onSubmit={() => {}} />);
    await user.type(screen.getByLabelText("Your request"), "Hello,");
    await user.click(screen.getByRole("button", { name: /Dictate/ }));
    act(() => FakeRecognition.last!.say("my password"));
    act(() => FakeRecognition.last!.say("my password expired"));
    expect(screen.getByLabelText("Your request")).toHaveValue("Hello, my password expired");
  });

  it("goes back to text mode when the box is emptied, and after each send", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Composed onSubmit={onSubmit} />);
    await user.click(screen.getByRole("button", { name: /Dictate/ }));
    act(() => FakeRecognition.last!.say("dictated"));
    await user.clear(screen.getByLabelText("Your request"));
    await user.type(screen.getByLabelText("Your request"), "typed instead");
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect(onSubmit).toHaveBeenLastCalledWith("typed instead", "text");

    await user.type(screen.getByLabelText("Your request"), "next");
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect(onSubmit).toHaveBeenLastCalledWith("next", "text");
  });

  it("still works with a plain node as micSlot", () => {
    render(<Composer busy={false} onSubmit={() => {}} micSlot={<span>mic here</span>} />);
    expect(screen.getByText("mic here")).toBeInTheDocument();
  });
});
