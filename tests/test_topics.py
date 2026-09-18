import asyncio
import json
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest


sys.path.insert(0, str(Path(__file__).parents[1]))

from topics import TopicBoundaryDetector, TopicRoutingModule, TopicStore


class FakeLlm:
    def __init__(self, parsed=None, error=None):
        self.parsed = parsed
        self.error = error
        self.calls = []

    async def acomplete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(parsed=self.parsed)


def message(text, message_id="message-1", peer_id="peer-1"):
    return SimpleNamespace(
        text=text,
        message_id=message_id,
        source=SimpleNamespace(user_id=peer_id, chat_id=peer_id),
    )


class TopicRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "topics.sqlite3"
        self.store = TopicStore(self.path)
        self.router = TopicRoutingModule(self.store, "account-1")

    def tearDown(self):
        self.temp.cleanup()

    def decide(self, text, message_id="message-1"):
        return asyncio.run(self.router.decide(message(text, message_id)))

    def test_normal_messages_keep_the_same_topic(self):
        first = self.decide("第一条", "m1")
        second = self.decide("继续", "m2")

        self.assertEqual("route", first.action)
        self.assertEqual(first.topic_id, second.topic_id)

    def test_new_with_content_routes_content_to_a_new_topic(self):
        old = self.decide("原话题", "m1")
        new = self.decide("新话题：讨论东京旅行", "m2")

        self.assertNotEqual(old.topic_id, new.topic_id)
        self.assertEqual("讨论东京旅行", new.content)
        self.assertEqual("explicit", new.reason)

    def test_empty_new_command_is_consumed_and_moves_pointer(self):
        old = self.decide("原话题", "m1")
        confirmation = self.decide("/new", "m2")
        following = self.decide("新会话第一条", "m3")

        self.assertEqual("reply", confirmation.action)
        self.assertNotEqual(old.topic_id, following.topic_id)

    def test_list_switch_and_undo(self):
        old = self.decide("原话题", "m1")
        new = self.decide("/new 新话题内容", "m2")

        listing = self.decide("话题列表", "m3")
        switched = self.decide(f"切到 {old.topic_id[:8]}", "m4")
        current = self.decide("当前话题", "m5")
        undone = self.decide("撤销切换", "m6")

        self.assertIn(old.topic_id[:8], listing.reply)
        self.assertIn(new.topic_id[:8], listing.reply)
        self.assertIn(old.topic_id[:8], switched.reply)
        self.assertIn(old.topic_id[:8], current.reply)
        self.assertIn(new.topic_id[:8], undone.reply)

    def test_duplicate_message_is_silently_consumed(self):
        first = self.decide("/new 只创建一次", "same-id")
        duplicate = self.decide("/new 只创建一次", "same-id")

        self.assertEqual("route", first.action)
        self.assertEqual("reply", duplicate.action)
        self.assertEqual("", duplicate.reply)
        self.assertEqual(2, len(self.store.list_topics("account-1", "peer-1")))

    def test_state_survives_a_restart(self):
        created = self.decide("/new 持久化话题", "m1")

        restarted = TopicRoutingModule(TopicStore(self.path), "account-1")
        decision = asyncio.run(restarted.decide(message("继续", "m2")))

        self.assertEqual(created.topic_id, decision.topic_id)

    def test_peers_are_isolated(self):
        peer_one = asyncio.run(self.router.decide(message("你好", "m1", "peer-1")))
        peer_two = asyncio.run(self.router.decide(message("你好", "m2", "peer-2")))

        self.assertNotEqual(peer_one.topic_id, peer_two.topic_id)

    def test_archive_hides_old_topic_without_deleting_it(self):
        old = self.decide("需要保留", "m1")
        archived = self.decide("归档当前话题", "m2")

        visible = self.store.list_topics("account-1", "peer-1")
        with closing(self.store._connect()) as connection:
            row = connection.execute(
                "SELECT archived FROM topics WHERE topic_id = ?", (old.topic_id,)
            ).fetchone()

        self.assertEqual("reply", archived.action)
        self.assertNotIn(old.topic_id, [topic.topic_id for topic in visible])
        self.assertEqual(1, row["archived"])

    def test_clear_natural_boundary_creates_a_topic_without_llm(self):
        router = TopicRoutingModule(
            self.store, "account-1", auto_detect=True, cooldown_turns=99
        )
        old = asyncio.run(router.decide(message("继续原来的事情", "m1")))
        new = asyncio.run(router.decide(message("换个完全不同的问题，东京怎么玩", "m2")))

        self.assertNotEqual(old.topic_id, new.topic_id)
        self.assertEqual("rule", new.reason)

    def test_high_confidence_detection_routes_trigger_to_new_topic(self):
        llm = FakeLlm(
            {
                "is_new_topic": True,
                "confidence": 0.97,
                "suggested_title": "东京旅行",
            }
        )
        router = TopicRoutingModule(
            self.store,
            "account-1",
            detector=TopicBoundaryDetector(llm),
            auto_detect=True,
            cooldown_turns=2,
        )
        old = asyncio.run(router.decide(message("讨论邮件队列设计", "m1")))
        asyncio.run(router.decide(message("队列需要支持重试机制", "m2")))
        new = asyncio.run(router.decide(message("下个月去东京应该怎样安排行程", "m3")))

        self.assertNotEqual(old.topic_id, new.topic_id)
        self.assertEqual("detected", new.reason)
        self.assertEqual("下个月去东京应该怎样安排行程", new.content)
        self.assertEqual(1, len(llm.calls))
        payload = json.loads(llm.calls[0]["input"][0]["text"])
        self.assertEqual(["讨论邮件队列设计", "队列需要支持重试机制"], payload["recent_user_messages"])
        self.assertEqual("weixin_topic_boundary", llm.calls[0]["task"])

    def test_low_confidence_or_detector_failure_keeps_current_topic(self):
        low = FakeLlm(
            {
                "is_new_topic": True,
                "confidence": 0.70,
                "suggested_title": "可能的新话题",
            }
        )
        router = TopicRoutingModule(
            self.store,
            "account-1",
            detector=TopicBoundaryDetector(low),
            auto_detect=True,
            cooldown_turns=0,
        )
        current = asyncio.run(router.decide(message("这是一个足够长的原始问题", "m1")))

        failing = FakeLlm(error=RuntimeError("provider unavailable"))
        router.detector = TopicBoundaryDetector(failing)
        after_failure = asyncio.run(
            router.decide(message("这是另一个足够长但检测失败的问题", "m2"))
        )

        self.assertEqual("current", current.reason)
        self.assertEqual(current.topic_id, after_failure.topic_id)

    def test_continuation_skips_the_detector(self):
        llm = FakeLlm(
            {
                "is_new_topic": True,
                "confidence": 0.99,
                "suggested_title": "错误切换",
            }
        )
        router = TopicRoutingModule(
            self.store,
            "account-1",
            detector=TopicBoundaryDetector(llm),
            auto_detect=True,
            cooldown_turns=0,
        )

        decision = asyncio.run(
            router.decide(message("继续解释一下刚才的实现细节", "m1"))
        )

        self.assertEqual("current", decision.reason)
        self.assertEqual([], llm.calls)

    def test_invalid_or_timed_out_structured_response_fails_closed(self):
        invalid = TopicBoundaryDetector(FakeLlm({"is_new_topic": "yes"}))
        timed_out = TopicBoundaryDetector(FakeLlm(error=TimeoutError()))
        arguments = {
            "current_title": "当前",
            "recent_messages": ["上下文"],
            "current_message": "一条足够长的新消息",
            "turn_count": 9,
        }

        invalid_result = asyncio.run(invalid.detect(**arguments))
        timeout_result = asyncio.run(timed_out.detect(**arguments))

        self.assertIsNone(invalid_result)
        self.assertIsNone(timeout_result)

    def test_detection_metrics_keep_content_out_of_the_database(self):
        detector = TopicBoundaryDetector(
            FakeLlm(
                {
                    "is_new_topic": True,
                    "confidence": 0.97,
                    "suggested_title": "新话题",
                }
            )
        )
        router = TopicRoutingModule(
            self.store,
            "account-1",
            detector=detector,
            auto_detect=True,
            cooldown_turns=0,
        )

        switched = asyncio.run(router.decide(message("这是足够长的无关新问题", "m1")))
        asyncio.run(router.decide(message("撤销切换", "m2")))
        metrics = self.store.detection_summary("account-1")
        with closing(self.store._connect()) as connection:
            stored = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'detection_events'"
            ).fetchone()["sql"]

        self.assertEqual("detected", switched.reason)
        self.assertEqual(1, metrics["automatic_switches"])
        self.assertEqual(1, metrics["undone_switches"])
        self.assertNotIn("content", stored.lower())


class QualityGateTests(unittest.TestCase):
    @staticmethod
    def _write_dataset(labels: Path, predictions: Path, *, error_switch: bool = False):
        labels.write_text(
            "\n".join(
                json.dumps({"id": str(index), "is_new_topic": index < 120})
                for index in range(200)
            ),
            encoding="utf-8",
        )
        predictions.write_text(
            "\n".join(
                json.dumps(
                    {
                        "id": str(index),
                        "is_new_topic": index < 75 or (error_switch and index == 199),
                        "confidence": 0.96 if index < 75 or (error_switch and index == 199) else 0.10,
                        "status": "error" if error_switch and index == 199 else "ok",
                    }
                )
                for index in range(200)
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _run_gate(labels: Path, predictions: Path):
        return subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parents[1] / "tools" / "evaluate_boundary_dataset.py"),
                "--labels",
                str(labels),
                "--predictions",
                str(predictions),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_quality_gate_accepts_a_passing_200_sample_dataset(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            labels = root / "labels.jsonl"
            predictions = root / "predictions.jsonl"
            self._write_dataset(labels, predictions)
            result = self._run_gate(labels, predictions)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('"precision": 1.0', result.stdout)

    def test_quality_gate_rejects_error_that_requested_a_switch(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            labels = root / "labels.jsonl"
            predictions = root / "predictions.jsonl"
            self._write_dataset(labels, predictions, error_switch=True)
            result = self._run_gate(labels, predictions)

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn('"error_switches": 1', result.stdout)


if __name__ == "__main__":
    unittest.main()
