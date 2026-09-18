"""Personal Weixin iLink adapter with stable logical topics."""

from __future__ import annotations

from pathlib import Path

from gateway.config import Platform
from gateway.platforms.weixin import WeixinAdapter, check_weixin_requirements
from hermes_cli.config import get_hermes_home

from .topics import TopicBoundaryDetector, TopicRoutingModule, TopicStore


class WeixinTopicsAdapter(WeixinAdapter):
    """Reuse Hermes's official iLink transport and add routing before session keying."""

    def __init__(self, config, *, llm=None):
        super().__init__(config)
        # The platform has already been registered before its factory runs, so Hermes can
        # safely create this dynamic enum member. A distinct name preserves old `weixin`
        # transcripts and prevents accidental key migration.
        self.platform = Platform("weixin_topics")
        self._group_policy = "disabled"

        topics = (config.extra or {}).get("topics") or {}
        database_path = topics.get("database_path")
        if not database_path:
            database_path = Path(get_hermes_home()) / "state" / "weixin_topics.sqlite3"
        store = TopicStore(
            database_path,
            processed_retention_days=topics.get("processed_retention_days", 7),
        )
        auto_detect = _as_bool(topics.get("auto_detect", True))
        detector = (
            TopicBoundaryDetector(
                llm,
                confidence_threshold=topics.get("confidence_threshold", 0.90),
                timeout=topics.get("detector_timeout_seconds", 3),
            )
            if auto_detect and llm is not None
            else None
        )
        self._topic_router = TopicRoutingModule(
            store,
            self._account_id,
            detector=detector,
            auto_detect=auto_detect,
            recent_user_messages=topics.get("recent_user_messages", 4),
            cooldown_turns=topics.get("cooldown_turns", 4),
        )

    async def handle_message(self, event) -> None:
        # Group topics are deliberately out of scope. The official transport also has its
        # group policy forced to disabled above, making this a defense-in-depth fallback.
        if event.source.chat_type != "dm":
            await super().handle_message(event)
            return

        try:
            decision = await self._topic_router.decide(event)
        except Exception as error:
            # Fail closed when topic metadata is corrupt. Falling back to a made-up or old
            # topic could silently mix histories, which is worse than surfacing the error.
            await self.send(event.source.chat_id, f"话题路由失败，消息未发送：{error}")
            return

        if decision.action == "reply":
            if decision.reply:
                await self.send(
                    event.source.chat_id,
                    decision.reply,
                    reply_to=event.message_id,
                )
            return

        event.source.thread_id = decision.topic_id
        event.text = decision.content or event.text
        await super().handle_message(event)


def register(ctx) -> None:
    ctx.register_auxiliary_task(
        "weixin_topic_boundary",
        display_name="Weixin topic boundary",
        description="Conservatively detects clear topic changes in personal Weixin DMs.",
    )
    ctx.register_platform(
        name="weixin_topics",
        label="Weixin Topics",
        adapter_factory=lambda config: WeixinTopicsAdapter(config, llm=ctx.llm),
        check_fn=check_weixin_requirements,
        required_env=["WEIXIN_ACCOUNT_ID"],
        allowed_users_env="WEIXIN_ALLOWED_USERS",
        max_message_length=WeixinAdapter.MAX_MESSAGE_LENGTH,
        emoji="💬",
        platform_hint=(
            "You are chatting through personal Weixin. The user may switch logical "
            "topics; answer only from the current Hermes session and shared memory."
        ),
    )


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
