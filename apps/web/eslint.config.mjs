import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// RTL safety: physical direction utilities break Arabic layouts. Use logical ones
// (ms-/me-/ps-/pe-/start-/end-/text-start/text-end) in src/components/**.
const PHYSICAL = String.raw`(^|[\s"'\`:])-?(ml|mr|pl|pr|left|right|border-l|border-r|rounded-l|rounded-r|rounded-tl|rounded-tr|rounded-bl|rounded-br)-`;
const PHYSICAL_TEXT = String.raw`(^|[\s"'\`:])text-(left|right)([\s"'\`]|$)`;

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "coverage/**"]),
  {
    files: ["src/components/**/*.{ts,tsx}", "src/app/**/*.{ts,tsx}"],
    ignores: ["**/__tests__/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: `Literal[value=/${PHYSICAL}/]`,
          message: "Use RTL-safe logical utilities (ms-/me-/ps-/pe-/start-/end-), not left/right.",
        },
        {
          selector: `Literal[value=/${PHYSICAL_TEXT}/]`,
          message: "Use text-start / text-end, not text-left / text-right.",
        },
        {
          selector: `TemplateElement[value.raw=/${PHYSICAL}/]`,
          message: "Use RTL-safe logical utilities (ms-/me-/ps-/pe-/start-/end-), not left/right.",
        },
      ],
    },
  },
  {
    // Presentational layer must not reach the data layer (ARCHITECTURE 1.7).
    files: ["src/components/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            { group: ["@/lib/supabase/*", "@/lib/ai/*", "@/lib/repos/*"], message: "Components are presentational; fetch in hooks/pages." },
          ],
        },
      ],
    },
  },
]);
