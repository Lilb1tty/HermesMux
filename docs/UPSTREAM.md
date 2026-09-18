# Upstream Hermes contract

The Phase 0/1 implementation is verified against:

```text
repository: https://github.com/NousResearch/hermes-agent
commit: c661785f872b5647fbac7c138d965180783bd9af
verified: 2026-09-19
```

The plugin currently subclasses `gateway.platforms.weixin.WeixinAdapter` because the pinned Hermes version does not expose its iLink transport as a separate public component. The narrow override is `handle_message()`, which the official adapter calls after text batching and for media messages.

Automatic detection uses the supported plugin LLM surface: `ctx.register_auxiliary_task()` and `ctx.llm.acomplete_structured()`. Provider credentials and model routing remain owned by Hermes.

Before upgrading Hermes, run the test suite with `HERMES_AGENT_SOURCE` pointing to the candidate checkout. The contract test executes that checkout's real `gateway/session.py` and verifies that different DM `thread_id` values produce different stable keys.
