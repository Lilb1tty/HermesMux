import asyncio
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest


sys.path.insert(0, str(Path(__file__).parents[1]))

from topics import TopicRoutingModule, TopicStore


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


if __name__ == "__main__":
    unittest.main()
