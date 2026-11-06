# CampusPulse — instructions for Claude Code

Read `docs/SPEC.md` first. It is the single source of truth for scope, architecture and build order. Reference material is in `docs/reference/`.

## Project in one line
Track C entry for GJU AI Quest 2026: CampusPulse, a bilingual (EN + Jordanian Arabic, Arabizi, voice) campus nervous system. It classifies requests by category and priority with calibrated (conformal) uncertainty, asks a clarifying question when unsure, explains with counterfactuals, acts (FAQ, tickets → Linear, advisor booking, safety alerts), detects incidents on a live Pulse map, learns from staff corrections instantly, and defends against injection and queue-jumping. Built with a Next.js web app, a Python FastAPI AI service and Supabase. Deadline: 10 Nov 2026, 23:59 Amman.

## Non-negotiables
- NEVER open, read, list or use `hidden_test.csv`, `hidden_test_labels.csv` or `JUDGE_GUIDE.md` if they appear anywhere. If one shows up in the repo, stop and tell the user.
- NEVER edit official labels in `data/raw` or `data/clean`. Label adjustments only live in `data/clean/label_flags.csv` as soft targets.
- NEVER send email, calendar invites or messages to an address that has not consented. Send only to addresses in the `DEMO_EMAIL_ALLOWLIST` env var, or to a notification email its owner typed on their profile after **ticking a consent box** ("this is my own address and I agree to receive demo emails"; user decision 2026-11-02, so testers such as the course doctor can receive real emails; no code verification because the demo has one tester), enforced in one place in code. Never to departments or staff addresses taken from anywhere else. Advisor names in seed data are fictional.
- API keys (OpenRouter, Resend, Google, Supabase service role) live server-side in env vars only. Never in client code, never committed. Keep `.env.example` up to date.
- `services/ai/predict.py` must run fully offline with no API key, on CPU, from a clean `pip install -r requirements.txt`. With `OPENROUTER_API_KEY` set it uses the LLM front end by default (user decision D-057, 2026-11-06); `--offline` must always give the pure offline path, and a missing key must never fail the run.
- Evaluate only with scenario-held-out CV (`cv_group` column) and our own test set. Never report random-split scores.
- Pin model IDs and use temperature 0 for every LLM call; cache responses.

## Data
- `data/raw/`: official train and validation, untouched (UTF-8 with BOM → `utf-8-sig`).
- `data/clean/`: produced by `python scripts/clean_data.py`. Run `python scripts/test_clean.py` after any change. Key columns: `core`, `text_norm`, `scenario_id`, `cv_group`, `lang`.
- `data/augmented/`: our paraphrases and new scenarios. Every row needs `source` and `needs_human_check`.
- `data/our_test/`, `data/robustness/`: never used for training.

## Conventions
- Python 3.11+, type hints, `ruff` + `pytest`. The AI package is `services/ai/campuspulse_ai/`, and the API, `train.py` and `predict.py` all import it.
- Next.js App Router + TypeScript + Tailwind. Server-side calls only for anything that needs a key.
- Supabase changes go through SQL migrations in `supabase/migrations/`.
- Small, reviewable commits. Every model or service added gets a line in the README "Disclosures" section.

## Order of work
Follow the phases in SPEC §12 (P0 → P6). Each phase has exit criteria; don't start the next until they pass. The plan lives in `docs/PLAN.md` (keep it updated: tasks checked off, decisions recorded). Scored core (P1–P2) comes before any product work. Check with the user before cutting scope or changing architecture.

## Solo developer
One developer, no fixed schedule. Prefer small, complete increments that leave the repo demoable and `predict.py` working at every commit.
