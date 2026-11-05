# P10 package D report — grounded chat and retry

Implemented in the shared workspace; no deployment, live-key run or push.

## Changed contracts

- `ChatContext.sources` carries current-turn `GroundingSource(id, kind, text, scope)` values; `AgentReply.source_ids` defaults to an empty tuple for existing callers.
- Chat prompt version `chat-v2` asks for source IDs, scopes notices, and gives EN/AR/Arabizi library examples. Its cache key changes with the prompt hash.
- `ChatAgentLLM.reply` and `.phrase` reject unknown source IDs and replace selected unsupported operational claims with a safe response. A scoped announcement claim must repeat its scope. The deterministic check is a backstop; it cannot prove full semantic entailment.
- `OpenRouterClient` accepts optional chat-scoped `retry_on_rate_limit` and `total_deadline_s`; `composition/chat.py` enables one retry for 429, 5xx and timeouts. Default behavior for other callers is unchanged. A long Retry-After falls back immediately. Calls retain the existing `CachedChat` cost/cache path.

## Integrator patch required

`application/use_cases/chat.py::_context` currently builds `announcements` as strings. Populate `ChatContext.sources` from the SAME current-turn live announcements with stable server IDs, complete notice text and scope. No stored assistant message or caller text is a source. If FAQ and hint material is used in a reply, add it only from the retrieved current-turn result; a hint supports routing, never operational advice. Keep `announcements` populated for backward compatibility while transitioning. Package F owns this file, so D left it untouched. For `phrase`, the adapter itself adds `faq:proposal` from `ProposalFacts.faq_answer`.

The source scope should use the human place label appearing in the notice (for example `library`) so the adapter can require it in the reply. For global notices, leave scope empty. If the store cannot supply a reliable scope, keep the full text and use a conservative fallback rather than label a local notice as campus-wide.

## Verification

- Ruff on changed Python files: passed.
- Strict mypy on changed production modules: passed.
- Focused pytest `test_chat_agent_llm.py`, `test_chat_retry.py`, `test_oracle.py`: 36 passed, including the scoped-notice case.
- Fake HTTP transport covered 429/503 retry, 400/401/402 no retry and long Retry-After. Scripted chat covered invented workaround, invalid citation and scope mismatch.

## Limits

The grounding checker is deliberately narrow. It detects common invented promises, instructions and scope omissions; other unsupported claims can still pass. Real-key scripted regression remains a manual integration check. The retry deadline includes backoff and HTTP calls, but transport budgeting across other concurrent requests is outside this package.
