import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.PW_PORT ?? 3100);
const baseURL = process.env.PW_BASE_URL ?? `http://localhost:${PORT}`;

// The e2e runs the real Next.js app against two local doubles, so it needs no secrets:
//  - the mock AI API (fixtures, from services/ai) on 8765, started with PW_PYTHON (a venv that
//    has `-e services/ai` and requirements-dev.txt; default `python`);
//  - a tiny fake Supabase (e2e/support/fake-supabase.mjs) on 54399 that accepts the password
//    in E2E_PASSWORD (default e2e-password) for the three demo logins.
const API_PORT = Number(process.env.PW_API_PORT ?? 8765);
const SUPABASE_PORT = Number(process.env.PW_SUPABASE_PORT ?? 54399);
const PYTHON = process.env.PW_PYTHON ?? "python";
const SERVICE_TOKEN = "e2e-service-token";

export default defineConfig({
  testDir: "./e2e",
  timeout: 150_000,
  // `next dev` compiles each route on first visit, which can take several seconds.
  expect: { timeout: 60_000 },
  fullyParallel: false,
  // One worker: the specs share one dev server and one fake backend, and two workers compiling and signing in
  // at once left the first sign-in of a spec hanging.
  workers: 1,
  reporter: [["list"]],
  use: { baseURL, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.PW_BASE_URL
    ? undefined
    : [
        {
          command: `node e2e/support/fake-supabase.mjs`,
          url: `http://127.0.0.1:${SUPABASE_PORT}/health`,
          env: { FAKE_SUPABASE_PORT: String(SUPABASE_PORT) },
          reuseExistingServer: true,
          timeout: 30_000,
        },
        {
          command: `"${PYTHON}" -m uvicorn campuspulse_ai.frameworks.mock_app:create_mock_app --factory --port ${API_PORT}`,
          url: `http://127.0.0.1:${API_PORT}/health`,
          env: { MOCK_SERVICE_TOKEN: SERVICE_TOKEN },
          reuseExistingServer: true,
          timeout: 150_000,
        },
        {
          command: `pnpm exec next dev -p ${PORT}`,
          url: `${baseURL}/login`,
          env: {
            NEXT_PUBLIC_SUPABASE_URL: `http://localhost:${SUPABASE_PORT}`,
            NEXT_PUBLIC_SUPABASE_ANON_KEY: "e2e-anon-key",
            AI_SERVICE_URL: `http://127.0.0.1:${API_PORT}`,
            AI_SERVICE_TOKEN: SERVICE_TOKEN,
          },
          reuseExistingServer: true,
          timeout: 180_000,
        },
      ],
});
