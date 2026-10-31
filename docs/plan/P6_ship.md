# P6 — Ship

> **Status:** DRAFT — awaiting user approval. **Budget:** 1 d (ARCHITECTURE §4.0) · **Calendar:** Mon 9 (pm) – Tue 10 Nov (am); Tue 10 pm is the submission buffer until 23:59 · **Planned (not cut-flagged):** 11.75 h · **Cut-flagged:** 0 h.
>
> Conventions: [PLAN.md › Conventions](../PLAN.md#conventions). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md); `LD-n` and `OQ-n` link to the lead decisions and open questions in [PLAN.md](../PLAN.md). Tick `- [ ] Done` under each task as you finish it, and tick this phase's decision log at the bottom.

**Goal.** Deliver a submission a judge can reproduce on a common computer offline, plus a hosted demo that is warm, a 2-page report and a ≤ 3-minute video.

**Phase contract (§4.7).** Hands to the submission:
- **Model:** a final `train.py` run → `models/frozen/v1` (CURRENT); GitHub Release asset `campuspulse-models-v1.tar.gz` plus checksums (plus an HF mirror); `predictions.csv` for the official validation file.
- **Reproducibility:** `scripts/clean_machine_check.{sh,ps1}` passing on a fresh clone (Linux 3.11 container plus Windows 3.13, `requirements.txt` only, no torch).
- **Hosting:** Render redeployed from the tagged commit and warmed; Netlify and Supabase final.
- **Documents:** README (setup ≤ 3 commands, architecture, Disclosures), `docs/report/report.pdf` (2 pages), the video, and the submission email draft.

<a id="exit-criteria"></a>
**Exit criteria (SPEC §12, measurable).**

| # | Check | Command → expected |
| --- | --- | --- |
| X6.1 | Fresh clone → documented commands → identical predictions (Linux 3.11, network off at predict) | `bash scripts/clean_machine_check.sh https://github.com/<owner>/campuspulse v1.0.0` → `IDENTICAL LABELS (62/62 rows)` |
| X6.2 | Same on Windows 3.13 | `powershell -File scripts/clean_machine_check.ps1 -Repo https://github.com/<owner>/campuspulse -Tag v1.0.0` → `IDENTICAL LABELS (62/62 rows)` |
| X6.3 | Hosted demo | `cd apps/web && set PW_BASE_URL=https://<site>.netlify.app && npx playwright test e2e/moment1-ask.spec.ts e2e/moment2-pulse.spec.ts e2e/moment3-attack-learn.spec.ts` → `3 passed`. `curl -s %RENDER_URL%/health` → `"artifact":"v1"`, `rss_mb` ≤ 400 after the run. |
| X6.4 | Report done | `python scripts/check_report.py docs/report/report.pdf` → `pages=2 sections=7 OK` |
| X6.5 | Video done | `ffprobe -v error -show_entries format=duration -of csv=p=0 docs/report/video.mp4` → a value ≤ `180.0` (or the duration of the uploaded file, noted in the email) |
| X6.6 | Checklist | every SPEC §15 box is ticked in `docs/report/submission_checklist.md`, with the evidence path for each |

---

<a id="p6-1"></a>
## P6.1 — Run the final train, freeze v1, regenerate reports and notebooks

- [ ] Done
- Depends on: P2 complete; [P3.5](P3_intelligence.md#p3-5) (exemplar collections); [P4.5](P4_product_backend.md#p4-5)/P4.10 (`config/hand_tuned.yaml`)
- Est: 1.5 h (mostly wall-clock) · Cut: no
- Files:
  - models/frozen/v1/** (committed parts)
  - models/frozen/CURRENT
  - reports/*.json
  - reports/benchmark.md
  - notebooks/01–05 (executed)
  - scripts/run_notebooks.py
- Interfaces: `train.py` (P1/P2), `evaluate.py --all` (P2), `artifacts/io.py` MANIFEST.
- Config keys: all of `FrozenConfig`; nothing hand-edited in `config.json`
- Steps:
  1. Run `python services/ai/train.py --seed 42`. This is a full pool run: stage A/B/C plus the exemplar collections.
  2. Run `python services/ai/evaluate.py --all` → `reports/*`.
  3. Run `python scripts/run_notebooks.py`, which executes notebooks 01–05 with `nbclient` so they are never stale (§6.2 #10).
  4. Commit `models/frozen/v1` (≤ 25 MB, no file ≥ 50 MB). Write `CURRENT` = `v1`.
  5. Check that the encoder sha256 in MANIFEST equals the RC asset's. If it changed, rebuild the asset in P6.2.
- Acceptance:
  - `python -c "from campuspulse_ai.adapters.artifacts.io import load_manifest; m=load_manifest('models/frozen/v1'); print(m.version, len(m.files))"` → `v1 <n>`
  - `git ls-files -s models/frozen/v1 | python scripts/check_sizes.py --max-file-mb 50 --max-total-mb 25` (Files added) → `OK`
- Hands off: the frozen v1 to P6.2 and P6.3.

<a id="p6-2"></a>
## P6.2 — Package and publish the model release asset (GitHub Release plus HF mirror)

- [ ] Done
- Depends on: P6.1
- Est: 0.75 h · Cut: no. The HF mirror is optional backup and is not cut-numbered.
- Files:
  - scripts/package_models.py (Files added)
  - dist/campuspulse-models-v1.tar.gz (not committed)
  - dist/SHA256SUMS
  - scripts/fetch_models.py (default URL → the final release)
- Interfaces: the fetch contract in [Appendix C](appendix_C_artifacts.md).
- Steps:
  1. Run `python scripts/package_models.py --version v1`. It tars `models/frozen/v1/encoder/` (and `m3/` if listed) deterministically: sorted entries, `mtime=0`, `uid/gid=0`, gzip `mtime=0`. It then writes SHA256SUMS.
  2. Run `gh release create models-v1 dist/campuspulse-models-v1.tar.gz dist/SHA256SUMS --title "CampusPulse frozen models v1" --notes-file docs/release_notes_models_v1.md`.
  3. Optional mirror: `huggingface-cli upload <dev>/campuspulse-models dist/campuspulse-models-v1.tar.gz` (dev machine, train extras).
  4. Delete the RC release only after P6.5 has rebuilt Render from the final one.
- Acceptance: `python scripts/fetch_models.py --force --verify` (fresh `encoder/`) → `fetched campuspulse-models-v1.tar.gz (… MB) sha256 OK; MANIFEST OK`

<a id="p6-3"></a>
## P6.3 — Produce `predictions.csv` and the reproducibility reference

- [ ] Done
- Depends on: P6.2
- Est: 0.5 h · Cut: no
- Files:
  - predictions.csv (repo root: validation smoke sample, `request_id,category,priority`)
  - reports/predictions_val_check.csv
  - reports/predictions_val_debug.csv
  - scripts/make_predictions.py
  - scripts/make_predictions.sh (one-line wrapper, §6.1 #12)
- Steps:
  1. Run `python services/ai/predict.py --input data/raw/validation.csv --output predictions.csv`.
  2. Copy it to `reports/predictions_val_check.csv`.
  3. Run the `--debug` version for probabilities, so near-tie flips across CPUs can be explained (§6.2 #6/#15).
  4. `make_predictions.py --input <csv>` wraps predict with the default model dir. It is the documented judge command for the hidden test.
- Acceptance:
  - `python services/ai/predict.py --input data/raw/validation.csv --output predictions.csv` → `wrote 62 rows → predictions.csv (artifact v1 sha=…, tier0=62, llm=0, …)`
  - `python -c "import csv;r=list(csv.reader(open('predictions.csv',encoding='utf-8')));print(r[0],len(r)-1)"` → `['request_id', 'category', 'priority'] 62`
- Notes: the hidden test is never opened. The judges run the same command, or we run it on delivery if the organiser sends the file.

<a id="p6-4"></a>
## P6.4 — Write the clean-machine reproducibility scripts (Linux 3.11 container, Windows 3.13)

- [ ] Done
- Depends on: P6.3; the repo is public on GitHub ([OQ-7](../PLAN.md#oq-7))
- Est: 1.5 h · Cut: no
- Files:
  - scripts/clean_machine_check.sh
  - scripts/clean_machine_check.ps1
  - scripts/compare_predictions.py (Files added)
- Interfaces:
  - `clean_machine_check.sh <repo-url> <tag>` and `clean_machine_check.ps1 -Repo <url> -Tag <tag>`;
  - `compare_predictions.py <a.csv> <b.csv>` → exit 0 if every row's `category` and `priority` match (labels are compared, not bytes; [LD-7](../PLAN.md#ld-7)). Otherwise it prints the differing rows, with the `--debug` margins from `reports/predictions_val_debug.csv`.
- Steps:
  1. **Linux, two docker runs.**
     - Run 1, with network: `docker run --rm -v cpvol:/w python:3.11-slim bash -lc "apt-get update && apt-get install -y --no-install-recommends git && git clone --depth 1 --branch $TAG $REPO /w/repo && cd /w/repo && python -m venv /w/venv && /w/venv/bin/pip install -r services/ai/requirements.txt && /w/venv/bin/python scripts/fetch_models.py --verify"`.
     - Run 2, **`--network none`**: `/w/venv/bin/python services/ai/predict.py --input data/raw/validation.csv --output /w/out.csv && /w/venv/bin/python scripts/compare_predictions.py /w/out.csv reports/predictions_val_check.csv`.
  2. **Windows.** The script clones to `%TEMP%\cp_clean`, then runs `py -3.13 -m venv .venv`, `pip install -r services/ai/requirements.txt`, `fetch_models.py` and `predict.py`. Offline is simulated with `HF_HUB_OFFLINE=1`, `NO_PROXY=*` and `HTTPS_PROXY=http://127.0.0.1:9` during predict, so any network attempt fails loudly. Then it compares.
  3. Both scripts assert that `pip freeze` contains no `torch` and print the wall time. The time must be < 60 s for 1,000 rows (`predict.py --input tests/fixtures/rows_1000.csv`, a synthetic file built from `data/our_test` repeats; Files added).
  4. **If labels differ** on one platform: do not chase bit-exactness (§6.2 #15). Record the differing rows and their margins in the README "Reproducibility" note. X6.1 must still pass on Linux 3.11, which is the reference judge platform.
- Acceptance: X6.1 and X6.2 → `IDENTICAL …`; `predict.py` on 1,000 rows → `< 60 s` printed in the summary line.

<a id="p6-5"></a>
## P6.5 — Final deployment: Supabase migrations and seeds, Render from the tag, Netlify, warm-up

- [ ] Done
- Depends on: P6.2, P5 complete
- Est: 1.5 h · Cut: no
- Files:
  - netlify.toml (root: `[build] base = "apps/web"`, `command = "npm run build"`; `NODE_VERSION = "22"` in `[build.environment]`)
  - render.yaml
  - docs/deploy.md (Files added: runbook)
- Steps:
  1. **Supabase:** `supabase link --project-ref <ref>` → `supabase db push` (0001–0005, plus 0006 only if S1 shipped) → seeds → `python scripts/seed_demo_users.py` → `python scripts/seed_faq.py`. Verify no pending migrations with `supabase migration list`.
  2. **Tag** `git tag v1.0.0 && git push --tags`. Render deploys `main` at the tag commit (`autoDeployTrigger: commit`) and the Docker build fetches **`models-v1`** (final). `/health` shows `"artifact":"v1","sha":"<MANIFEST sha>"`.
  3. **Netlify:** set the env vars of [Appendix D](appendix_D_accounts.md), with `AI_SERVICE_TOKEN` scoped to Functions/runtime. Deploy from the tag and smoke-test `/login`.
  4. **Ops before the video and before judging:**
     - `scripts/keep_warm.ps1 -Hours 6`, which also keeps Supabase active (free projects pause after 7 idle days);
     - check the OpenRouter `limit_remaining`;
     - archive demo Linear issues to stay under the free cap;
     - clear demo rows with `python scripts/reset_demo.py` (Files added: truncates requests, predictions, tickets, incidents, outbox, notifications and request_embeddings, **keeps** memory_examples only if `--keep-memory`).
  5. Run X6.3.
- Acceptance: X6.3 → `3 passed`; `supabase migration list` → every local migration also on remote; `node apps/web/scripts/check-bundle-secrets.mjs` on the Netlify build output → `bundle clean`.

<a id="p6-6"></a>
## P6.6 — Write the README and Disclosures, and finalise `.env.example`

- [ ] Done
- Depends on: P6.4, P6.5
- Est: 1.5 h · Cut: no
- Files:
  - README.md
  - .env.example
  - docs/architecture.svg (Files added: exported from the §1.1 diagram)
- Steps:
  1. **README sections:**
     - pitch (2 lines);
     - "integration-ready prototype on synthetic data";
     - **Setup in ≤ 3 commands** (`pip install -r services/ai/requirements.txt` · `python scripts/fetch_models.py` · `python services/ai/predict.py --input <csv> --output predictions.csv`), "tested on Python 3.11 and 3.13";
     - hosted links;
     - architecture (diagram plus the 4-layer description);
     - results table (from `reports/benchmark.md`);
     - reproducibility note (label-level identity, int8 CPU caveat);
     - running the app locally;
     - responsible AI;
     - **Disclosures**.
  2. **Disclosures**, generated from Appendices A and B: every pretrained model (ID, revision, licence), every API (OpenRouter with the model IDs, Supabase, Linear, Gmail SMTP, Render, Netlify, plus Google Calendar and Meta WhatsApp only if shipped), datasets (official plus our augmentation, with `author_method`, including that LLM-drafted paraphrases were human-checked), fonts, and copied snippets (none, or listed).
  3. **`.env.example`** lists every key from [Appendix D](appendix_D_accounts.md) with empty values and a comment saying where it is used.
- Acceptance: `python scripts/check_readme.py` (Files added) → `setup_commands=3 disclosures>=N env_keys_documented=all OK`. It checks every `Settings` field name appears in `.env.example` and every `requirements*.txt`/`package.json` dependency appears in Disclosures or the deps table.

<a id="p6-7"></a>
## P6.7 — Write the 2-page report (SPEC §14)

- [ ] Done
- Depends on: P6.1 (final numbers)
- Est: 2 h · Cut: no
- Files:
  - docs/report/report.md (source)
  - docs/report/report.pdf
  - docs/report/figures/*.svg|png (from `reports/`)
  - scripts/check_report.py
- Steps:
  1. Write the seven SPEC §14 sections in order. Every number is copied from `reports/*.json` by `scripts/fill_report_numbers.py` (Files added), which replaces `{{metric:path}}` placeholders. Nothing is typed by hand.
  2. Include the honesty points from §6.2:
     - 42 scenarios;
     - conformal effective n ≈ the number of scenarios, so the guarantee is approximate;
     - own test set ≥ 60 rows, written before training;
     - "M4" = the LLM zero-shot row;
     - router coverage applies to tier 0 only;
     - the data is thin (42 unique texts, 30 groups, effective n ≈ 30), and fairness slices are reported with counts ([LD-32](../PLAN.md#ld-32));
     - the Arabizi slice comes only from our augmentation and our own test set ([LD-33](../PLAN.md#ld-33));
     - the "today → high" shortcut in the official data, with the `mask_deadline` ablation and the `deadline_shortcut` probe results ([LD-34](../PLAN.md#ld-34)).
  3. Export to PDF. A Word or Google Docs export is fine; record which tool in the Decisions log. `check_report.py` counts pages with a regex on `/Type /Page`, with no dependency.
- Acceptance: X6.4 → `pages=2 sections=7 OK`

<a id="p6-8"></a>
## P6.8 — Record and cut the ≤ 3-minute video (SPEC §13)

- [ ] Done
- Depends on: P6.5 (hosted, warm), [P5.13](P5_frontend.md#p5-13) (demo_script)
- Est: 2 h · Cut: no
- Files:
  - docs/report/video_runbook.md
  - docs/report/video.mp4 (or the unlisted link in the README/email; not committed if > 50 MB)
- Steps:
  1. **Pre-flight, 30 min before recording:**
     - `keep_warm.ps1`;
     - `reset_demo.py`;
     - the [X3.4](P3_intelligence.md#exit-criteria) sentences re-validated against the hosted API (`pytest services/ai/tests/e2e/test_demo_sentences_real.py --api %RENDER_URL% -m artifacts`);
     - Gmail demo inbox open;
     - Linear board open.
  2. Record each storyboard segment separately (OBS, 1080p), following SPEC §13 timings, and cut to ≤ 3:00. Moment 1 voice is used only if [P5.9](P5_frontend.md#p5-9) shipped; otherwise typed.
  3. Closing card: the responsible-AI line plus "integration-ready prototype".
- Acceptance: X6.5 → ≤ `180.0`

<a id="p6-9"></a>
## P6.9 — Run the submission checklist and email (SPEC §15)

- [ ] Done
- Depends on: P6.1–P6.8
- Est: 0.5 h · Cut: no
- Files:
  - docs/report/submission_checklist.md
  - docs/report/submission_email.md (draft, sent by the user)
- Steps: tick each SPEC §15 line with its evidence:
  - [ ] Repo + README (setup ≤ 3 commands, architecture, Disclosures) → `README.md`, X6.1
  - [ ] `predict.py` offline + `predictions.csv` → P6.3, X6.1/X6.2
  - [ ] Notebooks 01–05 → P6.1 executed outputs
  - [ ] 2-page PDF → X6.4
  - [ ] Video ≤ 3 min → X6.5
  - [ ] Hosted app link + runnable package → X6.3; release `models-v1`; tag `v1.0.0`
  - [ ] Email "AI Quest 2026 – Track C – <Team Name>" with name and student ID; **team-size question resolved with the organiser** (§6.2 #1; must be settled before 3 Nov)
- Acceptance: `python scripts/check_submission.py` (Files added) → `7/7 items have evidence`. The user sends the email; Claude never sends it.

## P6 risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Cross-CPU int8 label flip in X6.2 | Linux 3.11 is the reference. Document the rows in the README. Do not change the model on 9 Nov. |
| Render or Supabase down during judging | Keep-warm plus a pre-recorded video. The README states the local run (`uvicorn` + `npm run dev`). The free Supabase project gets daily `/health?deep=1` pings through 30 Nov. |
| Release asset unreachable (GitHub outage) | `fetch_models.py --source hf` mirror ([Appendix C](appendix_C_artifacts.md)) |
| Time | Everything cut-flagged elsewhere is already gone. P6 tasks are never cut. Report and video take priority over README polish. |

## P6 decisions logged during this phase
- [ ] Final `models-v1` release sha and tag `v1.0.0`
- [ ] Clean-machine results: Linux 3.11 / Windows 3.13 (labels identical? differing rows?)
- [ ] Final URLs: Netlify, Render, Supabase project
- [ ] Report PDF export tool
- [ ] Video length and upload link
- [ ] Submission email sent (date/time)
