# Appendix B — Pretrained models and LLM tiers

> Part of the CampusPulse plan ([PLAN.md](../PLAN.md)). `§n` refers to [ARCHITECTURE.md](../ARCHITECTURE.md).

**Pinning approach.**
1. In P1, `frameworks/cli/export_encoder.py` resolves the HF commit with `huggingface_hub.model_info(repo_id).sha` and downloads exactly that revision (`revision=<sha>`).
2. It records `encoder.model_id` and `encoder.revision` in `config.json`.
3. It exports and quantises to ONNX int8, and writes the sha256 of every produced file into `MANIFEST.json`.

Inference never contacts the Hub: `predict.py` sets `HF_HUB_OFFLINE=1`, and the encoder ships as our release asset ([Appendix C](appendix_C_artifacts.md)). Commit SHAs are filled in at P1 (**VERIFY@P1**). They are not known today.

Latency columns: **ESTIMATE** (E) unless marked V. "2 vCPU" is the research reference box. "Render 0.5 CPU" is scaled ×3 from it (E) and must be confirmed by `scripts/measure_rss.py` ([P4.13](P4_product_backend.md#p4-13)).

| Role | HF repo ID | Revision | Params | Size fp32 | Size int8 ONNX | Licence | CPU b=1 / b=32 int8, 2 vCPU | Render 0.5 CPU b=1 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **M2 encoder (primary)**, also used by: kNN index, OOD, memory, FAQ retrieval, incident clustering, guard exemplars | `intfloat/multilingual-e5-small` | sha @P1 | 118 M (V) | 471 MB (V) | ≈ 118 MB (V for HF's `model_qint8_avx512_vnni.onnx`; our dynamic export E ≈ 118–125 MB) + tokenizer.json ≈ 17 MB (E) | MIT | 10–18 ms / 150–250 ms (E) | 40–70 ms (E) | 384-d, max 512 tokens (we cap at 256). **Needs the `query: ` prefix** ([LD-9](../PLAN.md#ld-9)). |
| M2 encoder (fallback, same cost) | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | sha @P1 | 118 M (V) | 471 MB (V) | ≈ 118 MB (E) | Apache-2.0 | same (E) | same (E) | max 128 tokens, no prefix |
| **M3** fine-tune (cut #4, time-boxed in P2) | base `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (different from M2 for diversity; research recommendation) or e5-small | sha @P1 | 118 M | 471 MB | ≈ 118 MB (E) | Apache-2.0 (derivative: state the base) | +15 ms / +200 ms (E) | +40–70 ms (E) | **A second encoder adds about 150 MB RSS on Render, over the §3.17 budget** ([LD-6](../PLAN.md#ld-6)) |
| FAQ retrieval | same as M2, with cosine over pgvector `faq` | — | — | — | — | — | — | — | no reranker (research: FAQ < 100 rows) |
| Smaller-encoder fallback (§3.17 step 2) | **none found ≤ 80 MB int8 with Arabic** ([LD-30](../PLAN.md#ld-30)) | — | — | — | — | — | — | — | Options: vocabulary pruning of e5-small (E: 30–40 MB), or Render Standard |
| Voice | browser Web Speech API (`ar-JO`, `en-US`) | — | — | — | — | browser vendor service | — | — | no server model; Whisper cut |

**Rejected models** (research flags):
- `Alibaba-NLP/gte-multilingual-base`: needs `trust_remote_code`.
- `BAAI/bge-m3`: 2.3 GB.
- `jinaai/jina-reranker-v2-base-multilingual`: CC-BY-NC-4.0.
- `UBC-NLP/MARBERTv2` and `aubmindlab/bert-base-arabertv02-twitter`: no licence declared on HF.
- `google/embeddinggemma-300m`: gated, Gemma terms.
- Supabase Edge `gte-small`: English-only and a different vector space (user decision).

**LLM tiers via OpenRouter.** Prices were verified on 2026-10-31 from `/api/v1/models`, in USD per 1 M tokens (input/output). The IDs go into env only (`OPENROUTER_TIER1_MODEL`/`_TIER2_MODEL`). Re-query `https://openrouter.ai/api/v1/models` on the day of [P3.3](P3_intelligence.md#p3-3) and on 9 Nov. If an ID disappears, switch to the alternate and log it.

| Tier | Pinned ID | $ in / out | Structured outputs | Est. cost per 1 k escalations (≈ 400 in / 40 out tokens) | Alternate |
| --- | --- | --- | --- | --- | --- |
| 1 | `anthropic/claude-haiku-5.5` | 0.10 / 0.50 | yes | ≈ $0.06 | `deepseek/deepseek-v4.1-flash` (0.045 / 0.50) |
| 2 (cut #3) | `anthropic/claude-sonnet-5.5` | 2.00 / 10.00 | yes | ≈ $1.20 | `google/gemini-3.8-flash` (0.825 / 4.125) |
| Augmentation drafting (P2) | tier-1 ID | — | — | disclosed in README | — |

`:free` model variants are **not used**: 50 requests/day without credits, shared across keys. Spending is capped twice: by `LLM_DAILY_BUDGET_USD` (code) and by an OpenRouter per-key limit (account).

**Disclosure text for README** (generated in [P6.6](P6_ship.md#p6-6)):
- "Sentence encoder `intfloat/multilingual-e5-small` (MIT, © intfloat), exported to ONNX int8 by us."
- "M3 fine-tuned from `<base>` (Apache-2.0) [only if shipped]."
- "LLM tie-breaker via OpenRouter: `anthropic/claude-haiku-5.5` [and `anthropic/claude-sonnet-5.5`]; request text leaves the system only when `ENABLE_LLM=true` and no injection flag."
- "LLM-drafted paraphrases (`author_method=llm_draft`) were human-checked."
