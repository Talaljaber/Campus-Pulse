# CampusPulse

A bilingual campus-request triage system for GJU AI Quest 2026, Track C. Students write in English, Jordanian
Arabic or Arabizi. CampusPulse classifies each request by **category** (6 offices) and **priority**
(low, medium, high) with calibrated (conformal) uncertainty. When it is unsure, it asks a clarifying question.
It explains its decision and then acts: an FAQ answer, a ticket for the right office, an advisor booking or a
safety alert. Staff see incidents on a live map and can correct a label, and the system learns from it at once.

> Integration-ready prototype on synthetic data. Not a verified university deployment. Advisor names and
> offices in the demo are fictional; no real department is contacted.

## Try it

**Hosted app:** https://gjupulse.netlify.app. The demo password is in the submission email.

| Role | Log in as | Users |
|---|---|---|
| Student | student | `talal`, `lina`, `omar` |
| Office staff | staff | `registrar`, `it`, `finance`, `transport`, `facilities`, `academic` |
| Admin | staff | `admin` |

Pick a user, type the password, and log out to switch. The first message after a quiet period can take
about a minute while the AI service wakes up.

**On your own Windows laptop**, from the submitted folder (it already contains the models and the `.env`):

| Script | What it does | First run | Later runs |
|---|---|---|---|
| `RUN_ME.bat <file.csv>` | Predicts a test file. Writes `predictions.csv` (default, with the LLM) and `predictions_offline.csv` (our model alone) | 5 to 10 min (installs Python 3.13 and packages) | About 1 min |
| `START_APP.bat` | Runs the whole app locally: AI service on port 8000, website on http://localhost:3000. It uses the same hosted database | 10 to 15 min (also installs Node and builds the site) | About 1 min |

Both scripts install whatever is missing, so a laptop with nothing installed works. Close the two server
windows to stop the app.

## Prediction (the scored path)

The input is `request_id,text`. The output is `request_id,category,priority`.

```
pip install -r services/ai/requirements.txt
python scripts/fetch_models.py        # only for a git clone; the submitted folder already has the models
python services/ai/predict.py --input <requests.csv> --output predictions.csv
```

Python 3.11 or newer, CPU only. `fetch_models.py` downloads the model release and checks every file against
`models/frozen/v1/MANIFEST.json`.

**Two modes.**
- **Default (with `OPENROUTER_API_KEY` set, in the environment or `.env`):** two LLM steps run around our trained
  model, with a pinned model, temperature 0 and cached answers.
  1. Arabic and Arabizi requests are translated to English before our encoder.
  2. A tie-breaker picks the category from our model's three most likely ones and re-judges the priority.

  The LLM never lowers a `high` set by a safety, distress or deadline rule. It never changes the priority of a
  queue-jumping message, and rows flagged as prompt injection never reach it. A failed call is retried once;
  the last output line reports `llm_failed=N` (rows that kept the offline labels).
- **Offline (`--offline`, or no key):** our model alone, on CPU, with no network. A missing key never fails the
  run. `--use-llm` instead requires the LLM and exits with code 3 without a key.

The last output line says `llm_frontend=on` or `off`.

## How it works

1. **Guards** read the original text: language detection, prompt-injection and queue-jumping checks, a safety
   lexicon (accidents, fire, injuries, medical emergencies, distress, in English, Arabic and Arabizi) and a
   gibberish check.
2. **Translation:** Arabic goes through a local opus-mt translator (offline mode) or the LLM (default mode).
3. **Encoder:** multilingual-e5-small (int8 ONNX) embeds the text.
4. **Ensemble:** a logistic-regression head, a kNN member, office prototypes, and a TF-IDF model for priority.
5. **Rules** can only raise a priority (for example, a safety report is always high).
6. **Conformal sets** say how sure the model is. A wide set means the chat asks a clarifying question or a
   human reviews the request.

In the web app, the chat agent (DeepSeek v4.1 Flash via OpenRouter) only talks: it explains and asks questions.
The category and priority always come from the classifier above.

## Results

Macro-F1. Evaluation uses scenario-held-out cross-validation and our own test sets only; never a random split.

| Data | Rows | Offline: category / priority | Default (with LLM): category / priority |
|---|---|---|---|
| Official data, cross-validation | 432 | 0.935 / 0.904 | n/a |
| Official validation file | 62 | n/a | 1.000 / 1.000 |
| Our test sets 1 to 4, pooled | 396 | 0.769 / 0.752 | **0.960 / 0.972** |
| Test set 4, the final blind set (written after every design decision) | 144 | 0.751 / 0.676 | **0.932 / 0.972** |

- The official data is 432 rows, but only 42 distinct request texts with 9 to 11 wrappers each. An English
  scenario and its Arabic translation share a fold, giving 30 independent groups. Cross-validation is therefore
  optimistic, and our own test sets are the harder check.
- The weakest area offline is Arabizi category. With the LLM, our test sets reach category 0.960 English,
  0.970 Arabic and 0.942 Arabizi.
- Offline scores come from `evaluate.py --all`. Scores with the LLM come from `scripts/score_llm_mode.py`, which
  scores the saved default-mode predictions in `reports/llm_mode/`. Both appear in
  `notebooks/02_benchmark.ipynb`, with 95% bootstrap intervals for the LLM mode.
- The full record, including what each number does not prove, is in [docs/RESULTS.md](docs/RESULTS.md).

## Repository layout

| Path | What |
|---|---|
| `services/ai/` | Python package `campuspulse_ai`, FastAPI service, `train.py`, `predict.py`, `evaluate.py` |
| `apps/web/` | Next.js web app (student chat, staff desk, Pulse map, accounts, outbox) |
| `supabase/` | SQL migrations (Postgres, pgvector, row-level security) |
| `models/frozen/v1/` | The shipped model, with a sha256 for every file in `MANIFEST.json` |
| `config/` | Lexicons, prompts and LLM settings (pinned model IDs) |
| `data/` | Official data (`raw/`, `clean/`), our augmentation (`augmented/`), our test sets (`our_test/`) |
| `notebooks/` | Data exploration and evaluation notebooks |
| `reports/` | Evaluation reports |
| `docs/` | Plan, architecture, API, database, ML and UI docs |

Tests: `pytest services/ai/tests -q -m "not train and not artifacts and not supabase"` and, in `apps/web`,
`pnpm test`.

## Disclosures

The challenge rules require disclosing external services and pretrained models.

**Pretrained models**
- `intfloat/multilingual-e5-small` at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3` (MIT licence).
  Shipped as an int8 ONNX export whose vocabulary we pruned to Latin, Arabic, digit and symbol pieces with our
  own tool (`frameworks/cli/prune_encoder.py`). The embeddings are bit-identical to the unpruned int8 model on
  981 checked texts.
- `Helsinki-NLP/opus-mt-ar-en` at revision `c5b2a50db78d6be98ae207223f8d4f63bc7a0ff1` (Apache-2.0), converted
  to CTranslate2 int8. It translates Arabic-script requests to English in front of the encoder only, locally, on
  CPU, with no network. The guards and language detection read the original text. Arabizi is not translated
  offline.

**LLMs (all through OpenRouter, pinned model IDs, temperature 0, cached)**
- **Translation front end** (`deepseek/deepseek-v4.1-flash`, `config/llm_frontend.yaml`): translates Arabic and
  Arabizi requests to English in front of our encoder. Its structured cues can only raise a priority to high.
  Used by default in `predict.py` when `OPENROUTER_API_KEY` is set; `--offline` turns it off. Only the request
  text is sent. A failed call falls back to the offline path for that row.
- **Tie-breaker** (`deepseek/deepseek-v4.1-flash`, prompt `config/prompts/oracle_v3.md`): in `predict.py`'s
  default mode it picks one category from the model's top three and one priority (a `high` set by a safety,
  distress or deadline rule is kept). Only the request text and the allowed labels are sent. A failed or
  out-of-set answer keeps the model's labels.
- **Chat agent and issue preparer** (`deepseek/deepseek-v4.1-flash`, `config/chat_agent.yaml`): in the web app
  only. The agent writes replies and clarifying questions. The issue preparer summarises the request and may
  recommend raising a priority, with evidence quoted from the student's words. Neither sets the category.
- **Arabizi translator** (`openai/gpt-4o-mini-2024-07-18`): an older optional path, used only when
  `LLM_ARABIZI_TRANSLATE=true` and the front end is off. Never part of a default or offline run.
- **Data drafting** (`anthropic/claude-sonnet-5.5`, `anthropic/claude-haiku-5.5`): used once to draft
  augmentation data and our test sets; see Data below.

**Other services**
- **Supabase**: Postgres with pgvector, Auth and Realtime (app data, request embeddings, FAQ vectors).
- **Render** hosts the FastAPI AI service. **Netlify** hosts the web app.
- **Linear**: ticket mirroring and status sync, in a separate demo workspace.
- **Gmail SMTP**: notification emails, sent only to allow-listed demo inboxes or to an address its owner typed
  on their profile after ticking a consent box. Enforced in one place in code.
- **GitHub Releases**: hosts the model artifact tarball.

**Data**
- Official `train.csv` and `validation.csv` from the organizers (synthetic). Labels are never edited;
  disputed labels live only in `data/clean/label_flags.csv` as soft targets.
- `data/augmented/arabizi.csv`: rule-based Arabizi transliterations (`author_method=rule`).
- `data/augmented/new_scenarios.csv`: 78 new scenarios (390 rows), written by an LLM (`author_method=llm`).
  Used for training only after human review (`needs_human_check`).
- `data/augmented/arabizi_from_official.csv`: 126 Arabizi renderings of the official scenarios, written by
  `anthropic/claude-sonnet-5.5`. Unreviewed, used only in one Arabizi measurement, never in a shipped model.
- `data/augmented/paraphrases.csv` and `translations.csv`: paraphrases, EN/AR translations and Arabizi versions
  of the official scenarios, drafted by `anthropic/claude-sonnet-5.5` (cost 0.27 USD). Trained on only after
  human review.
- `data/augmented/review/review_sheet.csv`: independent labels from `anthropic/claude-haiku-5.5`, used only to
  focus the human review; never used as labels.
- `config/office_descriptions.yaml`: short descriptions of each office's work (EN/AR), written with an AI coding
  assistant (Claude) from the challenge category definitions and public GJU pages. They are embedded as office
  prototypes. Their author had read the official training texts, so they are not fully held out from them.
- `data/our_test/`: our test sets 1 to 4, written by an LLM and never trained on. Scores are reported per set.

**Code**
- Written with the help of an AI coding assistant (Claude Code). No copied code without attribution.
  Third-party libraries are listed in `services/ai/requirements*.txt` and `apps/web/package.json`.
