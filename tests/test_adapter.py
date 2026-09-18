import asyncio
import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest


ROOT = Path(__file__).parents[1]


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = _load_plugin_with_gateway_contract()

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.config = SimpleNamespace(
            extra={
                "account_id": "account-1",
                "topics": {"database_path": str(Path(self.temp.name) / "topics.sqlite3")},
            }
        )
        self.adapter = self.plugin.adapter.WeixinTopicsAdapter(self.config)

    def tearDown(self):
        self.temp.cleanup()

    def test_routes_topic_through_thread_id_before_base_handler(self):
        event = _event("新话题：讨论东京", "m1")

        asyncio.run(self.adapter.handle_message(event))

        self.assertEqual("讨论东京", event.text)
        self.assertIsNotNone(event.source.thread_id)
        self.assertEqual([(event.source.thread_id, "讨论东京")], self.adapter.handled)

    def test_topic_commands_are_consumed_without_agent_turn(self):
        event = _event("当前话题", "m1")

        asyncio.run(self.adapter.handle_message(event))

        self.assertEqual([], self.adapter.handled)
        self.assertIn("当前话题", self.adapter.sent[0][1])

    def test_refuses_to_poll_alongside_builtin_weixin(self):
        self.adapter.gateway_runner = SimpleNamespace(
            config=SimpleNamespace(
                platforms={self.plugin.adapter.Platform.WEIXIN: SimpleNamespace(enabled=True)}
            )
        )

        connected = asyncio.run(self.adapter.connect())

        self.assertFalse(connected)
        self.assertEqual("weixin_topics_conflict", self.adapter.fatal_error[0])

    def test_registers_as_a_distinct_platform(self):
        calls = []
        tasks = []
        context = SimpleNamespace(
            llm=object(),
            register_auxiliary_task=lambda name, **kwargs: tasks.append((name, kwargs)),
            register_platform=lambda **kwargs: calls.append(kwargs),
        )

        self.plugin.register(context)

        self.assertEqual("weixin_topics", calls[0]["name"])
        self.assertEqual("weixin_topic_boundary", tasks[0][0])


def _event(text, message_id):
    source = SimpleNamespace(
        chat_id="peer-1", user_id="peer-1", chat_type="dm", thread_id=None
    )
    return SimpleNamespace(text=text, message_id=message_id, source=source)


def _load_plugin_with_gateway_contract():
    fake_names = [
        "gateway",
        "gateway.config",
        "gateway.platforms",
        "gateway.platforms.weixin",
        "hermes_cli",
        "hermes_cli.config",
    ]
    previous = {name: sys.modules.get(name) for name in fake_names}
    package_name = "hermesmux_adapter_test"
    try:
        gateway = ModuleType("gateway")
        gateway.__path__ = []
        sys.modules["gateway"] = gateway

        config = ModuleType("gateway.config")

        class PlatformValue:
            def __init__(self, value):
                self.value = value

        class Platform:
            WEIXIN = PlatformValue("weixin")

            def __new__(cls, value):
                return PlatformValue(value)

        config.Platform = Platform
        sys.modules["gateway.config"] = config

        platforms = ModuleType("gateway.platforms")
        platforms.__path__ = []
        sys.modules["gateway.platforms"] = platforms

        weixin = ModuleType("gateway.platforms.weixin")

        class WeixinAdapter:
            MAX_MESSAGE_LENGTH = 2000

            def __init__(self, config):
                self.config = config
                self._account_id = config.extra.get("account_id", "")
                self._group_policy = config.extra.get("group_policy", "disabled")
                self.handled = []
                self.sent = []

            async def handle_message(self, event):
                self.handled.append((event.source.thread_id, event.text))

            async def connect(self, *, is_reconnect=False):
                return True

            def _set_fatal_error(self, code, message, retryable=False):
                self.fatal_error = (code, message, retryable)

            async def send(self, chat_id, content, reply_to=None, metadata=None):
                self.sent.append((chat_id, content, reply_to))

        weixin.WeixinAdapter = WeixinAdapter
        weixin.check_weixin_requirements = lambda: True
        sys.modules["gateway.platforms.weixin"] = weixin

        hermes_cli = ModuleType("hermes_cli")
        hermes_cli.__path__ = []
        sys.modules["hermes_cli"] = hermes_cli
        hermes_config = ModuleType("hermes_cli.config")
        hermes_config.get_hermes_home = lambda: str(ROOT / ".test-hermes")
        sys.modules["hermes_cli.config"] = hermes_config

        spec = importlib.util.spec_from_file_location(
            package_name,
            ROOT / "__init__.py",
            submodule_search_locations=[str(ROOT)],
        )
        package = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = package
        spec.loader.exec_module(package)
        package.adapter = sys.modules[f"{package_name}.adapter"]
        return package
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


if __name__ == "__main__":
    unittest.main()
