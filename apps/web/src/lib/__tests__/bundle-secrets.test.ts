import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { buildNeedles, scan } from "../../../scripts/check-bundle-secrets.mjs";

const dirs: string[] = [];
function bundle(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "cp-bundle-"));
  dirs.push(dir);
  for (const [name, text] of Object.entries(files)) {
    mkdirSync(join(dir, name, ".."), { recursive: true });
    writeFileSync(join(dir, name), text);
  }
  return dir;
}
afterEach(() => dirs.splice(0).forEach((d) => rmSync(d, { recursive: true, force: true })));

describe("leak check", () => {
  it("passes a clean bundle", () => {
    const dir = bundle({ "a.js": "console.log('hello')", "b/c.css": "body{}" });
    expect(scan([dir], buildNeedles({}))).toEqual([]);
  });

  it.each(["AI_SERVICE_TOKEN", "service_role", "sk-or-v1-abc", "GMAIL_APP_PASSWORD", "WHATSAPP_TOKEN"])(
    "finds the marker %s",
    (marker) => {
      const dir = bundle({ "chunks/x.js": `var k="${marker}";` });
      expect(scan([dir], buildNeedles({}))).toHaveLength(1);
    },
  );

  it("finds the literal value of a secret in the environment without echoing it", () => {
    const dir = bundle({ "page.html": "<script>var t='tok_9f8e7d6c5b4a'</script>" });
    const hits = scan([dir], buildNeedles({ AI_SERVICE_TOKEN: "tok_9f8e7d6c5b4a" }));
    expect(hits.map((h: { needle: string }) => h.needle)).toContain("value of AI_SERVICE_TOKEN");
    expect(JSON.stringify(hits)).not.toContain("tok_9f8e7d6c5b4a");
  });

  it("ignores a missing root", () => {
    expect(scan([join(tmpdir(), "does-not-exist-cp")], buildNeedles({}))).toEqual([]);
  });
});
