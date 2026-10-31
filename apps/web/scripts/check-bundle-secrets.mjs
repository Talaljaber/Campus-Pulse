#!/usr/bin/env node
// Leak check (P5.6): scans what the browser can download for server-side secrets.
//
//   pnpm build && node scripts/check-bundle-secrets.mjs
//
// It reads `.next/static/**` (the client bundle) and the prerendered HTML under
// `.next/server/app` (data inlined into pages). It fails when it finds
//   - the literal value of AI_SERVICE_TOKEN or SUPABASE_SERVICE_ROLE_KEY (if set in env),
//   - or one of the marker strings below.
// Exit 0 prints "bundle clean (0 matches)"; exit 1 lists every match.

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const MARKERS = ["AI_SERVICE_TOKEN", "service_role", "sk-or-", "GMAIL_APP_PASSWORD", "WHATSAPP_TOKEN"];
const SECRET_ENV = ["AI_SERVICE_TOKEN", "SUPABASE_SERVICE_ROLE_KEY"];
const TEXT_EXT = /\.(js|mjs|cjs|css|html|json|txt|map|rsc|svg)$/i;

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (TEXT_EXT.test(name)) yield full;
  }
}

/** Scans `roots` for `needles`; returns `{ file, needle }` for each hit (secret values are never echoed). */
export function scan(roots, needles) {
  const hits = [];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    for (const file of walk(root)) {
      const text = readFileSync(file, "utf8");
      for (const needle of needles) {
        if (text.includes(needle.value)) hits.push({ file, needle: needle.label });
      }
    }
  }
  return hits;
}

/** Marker strings plus the literal secret values present in this process's environment. */
export function buildNeedles(env = process.env) {
  const needles = MARKERS.map((m) => ({ value: m, label: m }));
  for (const key of SECRET_ENV) {
    const v = env[key];
    if (v && v.length >= 8) needles.push({ value: v, label: `value of ${key}` });
  }
  return needles;
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const base = resolve(fileURLToPath(new URL("..", import.meta.url)), ".next");
  const roots = [join(base, "static"), join(base, "server", "app")];
  if (!existsSync(join(base, "static"))) {
    console.error("No .next/static found. Run `pnpm build` first.");
    process.exit(2);
  }
  const hits = scan(roots, buildNeedles());
  if (hits.length === 0) {
    console.log("bundle clean (0 matches)");
  } else {
    for (const h of hits) console.error(`LEAK: ${h.needle} in ${relative(process.cwd(), h.file)}`);
    console.error(`bundle NOT clean (${hits.length} matches)`);
    process.exit(1);
  }
}
