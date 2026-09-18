# Use Personal Weixin iLink and Hermes thread_id Topics

Status: Accepted.

HermesMux is a third-party platform plugin named `weixin_topics`. It reuses the personal-Weixin iLink transport from the pinned Hermes Agent baseline and adds a Topic UUID to inbound DM messages as `SessionSource.thread_id` after official text batching completes.

Hermes remains the sole owner of Session Key generation, Transcripts, context compression, and Memory. The plugin stores only Topic metadata and bounded iLink message IDs in SQLite. The built-in `weixin` platform must be disabled while `weixin_topics` is active so only one long-poll client consumes an account.

Phase 1 provides explicit Topic commands only. Automatic semantic boundary detection requires a separate precision-gated phase and must fail back to the Current Topic.
