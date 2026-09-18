"""Contract check against the pinned Hermes session implementation.

Set HERMES_AGENT_SOURCE to a Hermes checkout to run this test elsewhere.  A
missing checkout skips the test instead of pretending to verify a copied key
algorithm.
"""

import importlib.util
import os
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType
import unittest


class HermesSessionContractTests(unittest.TestCase):
    def test_dm_thread_id_is_stable_and_isolates_topics(self):
        checkout = Path(
            os.getenv(
                "HERMES_AGENT_SOURCE",
                Path(__file__).parents[1] / ".tmp-hermes-agent",
            )
        )
        session_file = checkout / "gateway" / "session.py"
        if not session_file.exists():
            self.skipTest("set HERMES_AGENT_SOURCE to a Hermes Agent checkout")

        module = _load_official_session_module(session_file)
        source_a = module.SessionSource(
            platform=module.Platform.WEIXIN,
            chat_id="peer-1",
            chat_type="dm",
            user_id="peer-1",
            thread_id="topic-a",
        )
        source_b = module.SessionSource(
            platform=module.Platform.WEIXIN,
            chat_id="peer-1",
            chat_type="dm",
            user_id="peer-1",
            thread_id="topic-b",
        )
        source_a_after_restart = module.SessionSource(
            platform=module.Platform.WEIXIN,
            chat_id="peer-1",
            chat_type="dm",
            user_id="peer-1",
            thread_id="topic-a",
        )

        key_a = module.build_session_key(source_a)
        key_b = module.build_session_key(source_b)
        key_a_after_restart = module.build_session_key(source_a_after_restart)

        self.assertNotEqual(key_a, key_b)
        self.assertEqual(key_a, key_a_after_restart)


def _load_official_session_module(session_file: Path):
    """Load upstream session.py with tiny import stubs, not a copied algorithm."""
    names = [
        "gateway",
        "gateway.config",
        "gateway.whatsapp_identity",
        "gateway.session_persistence",
        "gateway.session_recovery",
        "gateway.session_lifecycle",
        "gateway.session_transcript",
        "gateway._contract_session",
    ]
    previous = {name: sys.modules.get(name) for name in names}
    try:
        package = ModuleType("gateway")
        package.__path__ = [str(session_file.parent)]
        sys.modules["gateway"] = package

        config = ModuleType("gateway.config")

        class Platform(Enum):
            WEIXIN = "weixin"
            WHATSAPP = "whatsapp"
            SLACK = "slack"
            SIGNAL = "signal"
            TELEGRAM = "telegram"
            BLUEBUBBLES = "bluebubbles"
            DISCORD = "discord"
            LOCAL = "local"
            MATRIX = "matrix"
            YUANBAO = "yuanbao"

        config.Platform = Platform
        config.GatewayConfig = type("GatewayConfig", (), {})
        config.HomeChannel = type("HomeChannel", (), {})
        sys.modules["gateway.config"] = config

        whatsapp = ModuleType("gateway.whatsapp_identity")
        whatsapp.canonical_whatsapp_identifier = lambda value: value
        sys.modules["gateway.whatsapp_identity"] = whatsapp

        persistence = ModuleType("gateway.session_persistence")
        persistence.SessionPersistenceMixin = type("SessionPersistenceMixin", (), {})
        persistence._DB_UNPINNED = 0
        sys.modules["gateway.session_persistence"] = persistence

        recovery = ModuleType("gateway.session_recovery")
        recovery.SessionRecoveryMixin = type("SessionRecoveryMixin", (), {})
        sys.modules["gateway.session_recovery"] = recovery

        lifecycle = ModuleType("gateway.session_lifecycle")
        lifecycle.SessionLifecycleMixin = type("SessionLifecycleMixin", (), {})
        lifecycle._iso = lambda value: str(value)
        lifecycle._new_session_id = lambda: "session"
        lifecycle._now = lambda: None
        lifecycle._parse_iso = lambda value: value
        sys.modules["gateway.session_lifecycle"] = lifecycle

        transcript = ModuleType("gateway.session_transcript")
        transcript.SessionTranscriptMixin = type("SessionTranscriptMixin", (), {})
        sys.modules["gateway.session_transcript"] = transcript

        spec = importlib.util.spec_from_file_location(
            "gateway._contract_session", session_file
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


if __name__ == "__main__":
    unittest.main()
