# claude CLI verification (Task 0 spike) — 2026-06-07

Empirical verification that the chat-panel architecture is sound, run against the
installed `claude` CLI from `~/dev/pm-os-team`.

## Flags confirmed present
`-p/--print` · `--session-id <uuid>` · `-r/--resume [value]` · `--output-format`
(supports `stream-json`) · `--verbose` · `--allowedTools <tools...>`.

## Continuity confirmed (the load-bearing fact)
1. `claude -p "…" --session-id <SID> --output-format stream-json --verbose --allowedTools Read` → exit 0, created the session.
2. `claude -p "what token did I ask for?" --resume <SID> --output-format stream-json --verbose` → exit 0, **recalled `PONG-7`** from the prior turn.

→ A fresh `claude -p --resume` process continues the prior session's context. This
is exactly what the chat panel relies on. ✅

## GOTCHA — prompt placement vs the variadic `--allowedTools`
`--allowedTools <tools...>` is **variadic** and will swallow a following positional
prompt. `claude -p --allowedTools Read "my prompt"` → error *"Input must be
provided…"* (the prompt got eaten as a tool name).
**Fix:** put the prompt FIRST (`claude -p "my prompt" --session-id … --allowedTools Read`),
exactly as `task_dispatch.py` already does (`["claude", prompt, …]`). `build_chat_cmd`
must place the prompt as the first positional arg (or pipe via stdin). Encode this
in the Task 4 tests.

## Event shapes (for `chat_runner.normalize`)
Stream is one JSON object per line. Relevant `type`s:
- `system`/`hook_started`,`hook_response` — ignore.
- `system`/`init` — has `session_id`, `model`, `cwd`, `tools`. (Use to capture/confirm session id.)
- `assistant` — `message.content[]` blocks:
  - `{type:"text", text}` → normalized `kind:"text"`
  - `{type:"thinking", thinking}` → normalized `kind:"think"`
  - `{type:"tool_use", id, name, input}` → normalized `kind:"tool_step"` (verb from `name`, target from `input.file_path`/`pattern`/`command`/etc.)
- `user` — `message.content[]` `{type:"tool_result", tool_use_id, content}` (tool output; usually not rendered as its own row — the tool_step already shows the call).
- `rate_limit_event` — ignore.
- `result`/`success` — final event: `result` (final text), `usage`
  (`input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`,
  `output_tokens`), `total_cost_usd`, `session_id`, `ttft_ms`, `duration_ms`.
  → normalized `kind:"result"` carrying `usage` + `cost`.

## Cost data point (validates the design's cold-open estimate)
The trivial create turn (tiny prompt, in repo cwd with CLAUDE.md auto-discovery)
reported `cache_creation_input_tokens: 27139` and `total_cost_usd: ~$0.21`. So a
cold open really does reprocess tens of thousands of tokens of context — the
design's ~20k–60k estimate is in the right range. Cache-warm follow-ups read that
cache instead (cheap). The 1h cache-TTL knob (`ephemeral_1h_input_tokens` appeared
here) is the real cost lever and remains a documented follow-on.

## Fixture
`tests/fixtures/stream_json_sample.jsonl` — one real representative line of each
kind (system/init, assistant/tool_use, user/tool_result, assistant/thinking,
assistant/text, result/success). Consumed by `tests/test_chat_runner_normalize.py`.

## Plan impact
No architectural change. One concrete adjustment: **prompt-first arg placement** in
`build_chat_cmd` (Task 4) and `build_claude_cmd` (Task 3) — both already prompt-first,
so the plan holds. Proceed.
