# CampusPulse

A bilingual (English, Jordanian Arabic, Arabizi) campus-request triage system for GJU AI Quest 2026, Track C.
It classifies each student request by **category** and **priority** with calibrated (conformal) uncertainty,
asks a clarifying question when unsure, explains its decision, acts (FAQ answer, ticket, advisor booking,
safety alert), detects incidents on a live map, and learns from staff corrections.

> Integration-ready prototype on synthetic data. Not a verified university deployment.

## Prediction (the scored path)

Python 3.11+ on CPU:

```
pip install -r services/ai/requirements.txt
python scripts/fetch_models.py
python services/ai/predict.py --input <requests.csv> --output predictions.csv
```

`fetch_models.py` downloads the model release asset and verifies every file against
`models/frozen/v1/MANIFEST.json`. The input is `request_id,text`. The output is `request_id,category,priority`.

**LLM mode on by default when a key is present (D-057, D-058).** If `OPENROUTER_API_KEY` is set (in the
environment or a `.env` file), two LLM steps run around our trained model (pinned model, temperature 0, cached):
Arabic and Arabizi requests are first translated to English, then a set-constrained tie-breaker chooses the
category among the model's three most probable ones and re-judges priority. It never lowers a `high` set by a
safety, distress or deadline rule, never moves the priority of a queue-jumping message, and injection-flagged rows
never reach it. On our blind set 4 (144 rows, written after every design decision) category / priority macro-F1
goes from 0.751 / 0.676 offline to 0.925 / 0.958; the official validation file stays at 1.000 / 1.000. A failed
LLM call is retried once after the batch; the last output line reports `llm_failed=N` (rows that kept the
offline labels). Without a key the same command
runs fully offline on CPU and prints a one-line notice. Flags: `--offline` never calls a network; `--use-llm` requires the LLM (exit 3 without a key).
The last output line says `llm_frontend=on` or `off`.

## Repository layout

| Path | What |
|---|---|
| `services/ai/` | Python package `campuspulse_ai` (domain, application, adapters, frameworks), FastAPI service, `train.py`, `predict.py`, `evaluate.py` |
| `apps/web/` | Next.js web app (student chat, staff desk, Pulse map, model lab, outbox) |
| `supabase/` | SQL migrations (Postgres, pgvector, RLS) |
| `data/` | official data (`raw/`, `clean/`), our augmentation (`augmented/`), our holdout (`our_test/`) |
| `docs/` | plan, architecture, API, DB, ML and UI docs |
| `reports/` | evaluation reports (`results_v1.md`, red-team runs, model-lab metrics) |

The full README (results, architecture diagram, local app setup, responsible AI) is written in P6.6.

## Disclosures

The challenge rules require disclosing external services and pretrained models. This list is kept current as
components are added.

**Pretrained models**
- `intfloat/multilingual-e5-small` at revision `614241f622f53c4eeff9890bdc4f31cfecc418b3` (MIT licence).
  Shipped as an int8 ONNX export whose vocabulary we pruned to Latin, Arabic, digit and symbol pieces with our
  own tool (`frameworks/cli/prune_encoder.py`). The embeddings are bit-identical to the unpruned int8 model on
  981 checked texts.
- `Helsinki-NLP/opus-mt-ar-en` at revision `c5b2a50db78d6be98ae207223f8d4f63bc7a0ff1` (Apache-2.0), converted
  to CTranslate2 int8. Part of the shipped model since v1-rc3 (D-019): Arabic-script requests are translated to
  English in front of the encoder only, locally, on CPU, with no network and no API key (`ctranslate2`,
  `sentencepiece`; files under `models/frozen/v1/translator/`, hashed in MANIFEST.json). The guards and
  language detection read the original text.
  Arabizi is not translated (v1-rc4): its category quality is the weakest (our_test F1 about 0.4) and its
  conformal sets are wide (about 3.5 of 6 categories), so most Arabizi requests are sent to human review.

**External services**
- **Supabase**: Postgres with pgvector, Auth and Realtime (app data, request embeddings, FAQ vectors).
- **Render**: hosts the FastAPI AI service. **Netlify**: hosts the web app.
- **OpenRouter**: the optional LLM tier in the live app, consulted only when the trained model is unsure
  (`ENABLE_LLM`, pinned model IDs, temperature 0, cached). Also used offline to draft training augmentation.
  `predict.py` never calls it.
- **OpenRouter, LLM front end** (`deepseek/deepseek-v4.1-flash`, pinned in `config/llm_frontend.yaml`,
  temperature 0, cached in `.cache/llm_frontend.sqlite`; P7.4/D-050, default since D-057): translates Arabic and
  Arabizi request text to English in front of our encoder, and its structured cues can only raise a priority to
  high (P7.9). On by default in `predict.py` when `OPENROUTER_API_KEY` is set; `--offline` turns it off. Only the
  request text is sent. A failed call falls back to the offline path for that row.
- **OpenRouter, tie-breaker** (`deepseek/deepseek-v4.1-flash`, prompt `config/prompts/oracle_v3.md`, temperature 0,
  cached in `.cache/llm.sqlite`; D-058 to D-060): in `predict.py`'s LLM mode it picks one category from the model's
  top three and one priority (a `high` set by a safety, distress or deadline rule is kept). Only the request text and the allowed labels are sent.
  A failed or out-of-set answer keeps the model's labels.
- **OpenRouter, optional Arabizi translator** (`openai/gpt-4o-mini-2024-07-18`, pinned, temperature 0, cached on
  disk; D-025): translates a Latin-script Arabic (Arabizi) request into English in front of the encoder only.
  Off by default, so the scored offline path is unchanged. It runs only with `predict.py --use-llm` or
  `LLM_ARABIZI_TRANSLATE=true` plus `OPENROUTER_API_KEY`. The only text sent is the student's request text of
  requests detected as Arabizi: no names, ids, labels or other requests. A failed call means no translation.
- **Linear**: ticket mirroring and status sync, in a separate demo workspace.
- **Gmail SMTP**: notifications, sent only to allow-listed demo inboxes (enforced in code).
- **GitHub Releases**: hosts the model artifact tarball.

**Data**
- Official `train.csv` and `validation.csv` from the organizers (synthetic). Labels are never edited;
  disputed labels live only in `data/clean/label_flags.csv` as soft targets.
- `data/augmented/arabizi.csv`: rule-based Arabizi transliterations (`author_method=rule`).
- `data/augmented/new_scenarios.csv`: 78 new scenarios (390 rows), written by an LLM (`author_method=llm`).
  They are used for training only after human review (`needs_human_check`).
- `data/augmented/arabizi_from_official.csv`: 126 Arabizi renderings of the official scenarios, written by `anthropic/claude-sonnet-5.5` (`author_method=llm`, unreviewed, used only in the Arabizi measurement arm, never in a frozen model).
- `data/augmented/paraphrases.csv` and `translations.csv`: paraphrases, EN/AR translations and Arabizi versions
  of the official scenarios, drafted by `anthropic/claude-sonnet-5.5` via OpenRouter (temperature 0, cached,
  0.27 USD; `author_method=llm:<model>`). Trained on only after human review.
- `data/augmented/review/review_sheet.csv`: independent labels from `anthropic/claude-haiku-5.5` (OpenRouter)
  for every unreviewed draft, used only to focus the human review; never used as labels.
- `config/office_descriptions.yaml`: short descriptions of each office's work (EN/AR), written with an AI coding
  assistant (Claude) from the challenge category definitions and public GJU pages, not copied from any dataset;
  embedded as the `m2proto` member's office prototypes. Its author had read the official training texts, so
  the office part is not fully held out from them (see `reports/results_v2.md`).
- `data/our_test/`: our holdout, never trained on. Sets 1 to 4 were written by an LLM (decision D-010 in
  `docs/PLAN.md`). Scores are reported per set.

**Code**
- No copied code without attribution. Third-party libraries are listed in `services/ai/requirements*.txt`
  and `apps/web/package.json`.
