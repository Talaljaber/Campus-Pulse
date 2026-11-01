# CampusPulse

A bilingual (English, Jordanian Arabic, Arabizi) campus-request triage system for GJU AI Quest 2026, Track C.
It classifies each student request by **category** and **priority** with calibrated (conformal) uncertainty,
asks a clarifying question when unsure, explains its decision, acts (FAQ answer, ticket, advisor booking,
safety alert), detects incidents on a live map, and learns from staff corrections.

> Integration-ready prototype on synthetic data. Not a verified university deployment.

## Offline prediction (the scored path)

Python 3.11+ on CPU, no API key, no network after the model download:

```
pip install -r services/ai/requirements.txt
python scripts/fetch_models.py
python services/ai/predict.py --input <requests.csv> --output predictions.csv
```

`fetch_models.py` downloads the `models-v1-rc1` release asset and verifies every file against
`models/frozen/v1/MANIFEST.json`. The input is `request_id,text`. The output is `request_id,category,priority`.

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

**External services**
- **Supabase**: Postgres with pgvector, Auth and Realtime (app data, request embeddings, FAQ vectors).
- **Render**: hosts the FastAPI AI service. **Netlify**: hosts the web app.
- **OpenRouter**: the optional LLM tier in the live app, consulted only when the trained model is unsure
  (`ENABLE_LLM`, pinned model IDs, temperature 0, cached). Also used offline to draft training augmentation.
  `predict.py` never calls it.
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
- `data/augmented/paraphrases.csv` and `translations.csv`: paraphrases, EN/AR translations and Arabizi versions
  of the official scenarios, drafted by `anthropic/claude-sonnet-5.5` via OpenRouter (temperature 0, cached,
  0.27 USD; `author_method=llm:<model>`). Trained on only after human review.
- `data/augmented/review/review_sheet.csv`: independent labels from `anthropic/claude-haiku-5.5` (OpenRouter)
  for every unreviewed draft, used only to focus the human review; never used as labels.
- `config/office_descriptions.yaml`: short descriptions of each office's work (EN/AR), written with an AI coding
  assistant (Claude) from the challenge category definitions and public GJU pages, not copied from any dataset;
  embedded as the `m2proto` member's office prototypes. Its author had read the official training texts, so
  the office part is not fully held out from them (see `reports/results_v2.md`).
- `data/our_test/`: our holdout, never trained on. Set 1 was hand-written by the developer; sets 2 and 3 were
  written by an LLM (decision D-010 in `docs/PLAN.md`). Scores are reported per set.

**Code**
- No copied code without attribution. Third-party libraries are listed in `services/ai/requirements*.txt`
  and `apps/web/package.json`.
