import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(__dirname, "../../../..");
const cli = join(root, "node_modules/openapi-typescript/bin/cli.js");
const spec = resolve(root, "../../services/ai/openapi.json");
const committed = join(root, "src/lib/ai/types.gen.ts");

describe("generated API types", () => {
  it("types.gen.ts is up to date with services/ai/openapi.json (run `pnpm gen:types`)", () => {
    const dir = mkdtempSync(join(tmpdir(), "cp-types-"));
    try {
      const out = join(dir, "types.gen.ts");
      execFileSync(process.execPath, [cli, spec, "-o", out], { stdio: "pipe" });
      const norm = (s: string) => s.replace(/\r\n/g, "\n");
      expect(norm(readFileSync(committed, "utf8"))).toBe(norm(readFileSync(out, "utf8")));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }, 30_000);
});
