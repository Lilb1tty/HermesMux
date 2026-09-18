# Route Direct WeChat Conversations to Isolated Hermes Sessions

Status: Superseded by ADR 0003.

This decision isolated different WeChat peers but did not solve multiple unrelated topics inside one peer's long-running DM. ADR 0003 replaces it with explicit Topic routing through Hermes's official `thread_id` seam.
