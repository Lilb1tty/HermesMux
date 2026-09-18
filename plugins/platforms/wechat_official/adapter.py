"""WeChat Official Account platform adapter for Hermes Agent."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import xml.etree.ElementTree as xml

from aiohttp import ClientSession, ClientTimeout, web
from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.platforms.event import MessageEvent, MessageType

from .security import valid_callback_signature


LOG = logging.getLogger(__name__)
API_BASE = "https://api.weixin.qq.com/cgi-bin"


class WeChatOfficialAdapter(BasePlatformAdapter):
    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform("wechat_official"))
        extra = config.extra or {}
        self._app_id = os.getenv("WECHAT_OFFICIAL_APP_ID", extra.get("app_id", ""))
        self._app_secret = os.getenv("WECHAT_OFFICIAL_APP_SECRET", extra.get("app_secret", ""))
        self._token = os.getenv("WECHAT_OFFICIAL_TOKEN", extra.get("token", ""))
        self._port = int(os.getenv("WECHAT_OFFICIAL_PORT", extra.get("port", 8080)))
        self._queue: asyncio.Queue[MessageEvent] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._runner: web.AppRunner | None = None
        self._http: ClientSession | None = None
        self._access_token = ""
        self._access_token_expires_at = 0.0

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        self._http = ClientSession(timeout=ClientTimeout(total=15))
        app = web.Application()
        app.router.add_get("/wechat/callback", self._verify_callback)
        app.router.add_post("/wechat/callback", self._receive_callback)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, port=self._port).start()
        self._worker = asyncio.create_task(self._drain_messages())
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        if self._worker:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
        if self._runner:
            await self._runner.cleanup()
        if self._http:
            await self._http.close()
        self._mark_disconnected()

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        try:
            access_token = await self._get_access_token()
            assert self._http is not None
            async with self._http.post(
                f"{API_BASE}/message/custom/send",
                params={"access_token": access_token},
                json={"touser": chat_id, "msgtype": "text", "text": {"content": content}},
            ) as response:
                payload = await response.json(content_type=None)
            if payload.get("errcode", 0) != 0:
                return SendResult(success=False, error=str(payload))
            return SendResult(success=True, message_id=str(payload.get("msgid", "")))
        except Exception as error:
            LOG.exception("WeChat message delivery failed")
            return SendResult(success=False, error=str(error))

    async def get_chat_info(self, chat_id):
        return {"name": chat_id, "type": "dm"}

    async def _verify_callback(self, request: web.Request) -> web.Response:
        if not self._signature_is_valid(request):
            raise web.HTTPForbidden()
        echo = request.query.get("echostr")
        if not echo:
            raise web.HTTPBadRequest(text="missing echostr")
        return web.Response(text=echo)

    async def _receive_callback(self, request: web.Request) -> web.Response:
        if not self._signature_is_valid(request):
            raise web.HTTPForbidden()
        try:
            message = self._parse_message(await request.text())
        except (KeyError, ValueError, xml.ParseError):
            raise web.HTTPBadRequest(text="invalid message") from None
        if message is not None:
            await self._queue.put(message)
        return web.Response(text="success")

    def _signature_is_valid(self, request: web.Request) -> bool:
        return valid_callback_signature(
            self._token,
            request.query.get("timestamp", ""),
            request.query.get("nonce", ""),
            request.query.get("signature", ""),
        )

    def _parse_message(self, body: str) -> MessageEvent | None:
        values = {child.tag: child.text or "" for child in xml.fromstring(body)}
        if values.get("MsgType") != "text":
            return None  # v1 is direct-text messages only.
        chat_id = values["FromUserName"]
        source = self.build_source(
            chat_id=chat_id,
            chat_name=chat_id,
            chat_type="dm",
            user_id=chat_id,
            user_name=chat_id,
        )
        return MessageEvent(
            text=values["Content"],
            message_type=MessageType.TEXT,
            source=source,
            message_id=values["MsgId"],
        )

    async def _drain_messages(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self.handle_message(event)
            except Exception:
                LOG.exception("WeChat message handling failed")
            finally:
                self._queue.task_done()

    async def _get_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._access_token_expires_at:
            return self._access_token
        assert self._http is not None
        async with self._http.get(
            f"{API_BASE}/token",
            params={
                "grant_type": "client_credential",
                "appid": self._app_id,
                "secret": self._app_secret,
            },
        ) as response:
            payload = await response.json(content_type=None)
        if "access_token" not in payload:
            raise RuntimeError(f"WeChat token request failed: {payload}")
        self._access_token = payload["access_token"]
        self._access_token_expires_at = time.monotonic() + max(0, payload.get("expires_in", 0) - 60)
        return self._access_token


def check_requirements() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("WECHAT_OFFICIAL_APP_ID", "WECHAT_OFFICIAL_APP_SECRET", "WECHAT_OFFICIAL_TOKEN")
    )


def validate_config(config) -> bool:
    extra = getattr(config, "extra", {}) or {}
    return all(
        os.getenv(env, extra.get(key, "")).strip()
        for env, key in (
            ("WECHAT_OFFICIAL_APP_ID", "app_id"),
            ("WECHAT_OFFICIAL_APP_SECRET", "app_secret"),
            ("WECHAT_OFFICIAL_TOKEN", "token"),
        )
    )


def _env_enablement() -> dict | None:
    if not check_requirements():
        return None
    return {
        "app_id": os.environ["WECHAT_OFFICIAL_APP_ID"],
        "app_secret": os.environ["WECHAT_OFFICIAL_APP_SECRET"],
        "token": os.environ["WECHAT_OFFICIAL_TOKEN"],
        "port": os.getenv("WECHAT_OFFICIAL_PORT", "8080"),
    }


def register(ctx):
    ctx.register_platform(
        name="wechat_official",
        label="WeChat Official Account",
        adapter_factory=lambda config: WeChatOfficialAdapter(config),
        check_fn=check_requirements,
        validate_config=validate_config,
        required_env=["WECHAT_OFFICIAL_APP_ID", "WECHAT_OFFICIAL_APP_SECRET", "WECHAT_OFFICIAL_TOKEN"],
        allowed_users_env="WECHAT_OFFICIAL_ALLOWED_USERS",
        platform_hint="You are chatting via a WeChat Official Account. Keep responses concise.",
        emoji="💬",
    )
