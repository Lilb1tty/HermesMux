"""Persistent topic routing for the personal Weixin plugin.

This module deliberately knows nothing about Hermes session IDs.  It only chooses a
stable topic ID; Hermes remains the sole owner of session-key construction.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal


DecisionAction = Literal["route", "reply"]
DecisionReason = Literal["current", "explicit", "switch", "undo"]


@dataclass(frozen=True)
class RoutingDecision:
    action: DecisionAction
    topic_id: str | None = None
    content: str | None = None
    reply: str | None = None
    reason: DecisionReason | None = None


@dataclass(frozen=True)
class Topic:
    topic_id: str
    title: str
    source: str
    created_at: str
    last_active_at: str
    archived: bool

    @property
    def short_id(self) -> str:
        return self.topic_id[:8]


class TopicStore:
    """Small SQLite index for topic metadata and the active-topic pointer."""

    def __init__(self, path: str | Path, *, processed_retention_days: int = 7):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.processed_retention_days = max(1, int(processed_retention_days))
        self._initialize()
        try:
            self.path.chmod(0o600)
        except OSError:
            # Windows ACLs and some mounted filesystems do not implement POSIX modes.
            pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS peer_state (
                    account_id TEXT NOT NULL,
                    peer_id TEXT NOT NULL,
                    current_topic_id TEXT NOT NULL,
                    previous_topic_id TEXT,
                    revision INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_id, peer_id)
                );

                CREATE TABLE IF NOT EXISTS topics (
                    account_id TEXT NOT NULL,
                    peer_id TEXT NOT NULL,
                    topic_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_id, peer_id, topic_id)
                );

                CREATE TABLE IF NOT EXISTS processed_messages (
                    account_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, message_id)
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    def claim_message(self, account_id: str, message_id: str | None) -> bool:
        """Return False when this iLink message was already routed."""
        if not message_id:
            return True
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=self.processed_retention_days)).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM processed_messages WHERE processed_at < ?", (cutoff,)
            )
            cursor = connection.execute(
                """INSERT OR IGNORE INTO processed_messages
                   (account_id, message_id, processed_at) VALUES (?, ?, ?)""",
                (account_id, message_id, now.isoformat()),
            )
            return cursor.rowcount == 1

    def current_topic(self, account_id: str, peer_id: str) -> Topic:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute(
                """SELECT current_topic_id FROM peer_state
                   WHERE account_id = ? AND peer_id = ?""",
                (account_id, peer_id),
            ).fetchone()
            if state is None:
                topic_id = self._new_id()
                now = self._now()
                connection.execute(
                    """INSERT INTO topics
                       (account_id, peer_id, topic_id, title, source, created_at, last_active_at)
                       VALUES (?, ?, ?, '默认话题', 'default', ?, ?)""",
                    (account_id, peer_id, topic_id, now, now),
                )
                connection.execute(
                    """INSERT INTO peer_state
                       (account_id, peer_id, current_topic_id)
                       VALUES (?, ?, ?)""",
                    (account_id, peer_id, topic_id),
                )
            else:
                topic_id = state["current_topic_id"]
            row = connection.execute(
                """SELECT * FROM topics
                   WHERE account_id = ? AND peer_id = ? AND topic_id = ?""",
                (account_id, peer_id, topic_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("当前话题索引损坏；已停止路由以保护现有会话")
            return self._topic(row)

    def touch(self, account_id: str, peer_id: str, topic_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """UPDATE topics SET last_active_at = ?
                   WHERE account_id = ? AND peer_id = ? AND topic_id = ?""",
                (self._now(), account_id, peer_id, topic_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("话题不存在；消息未被重新映射")

    def create_topic(
        self, account_id: str, peer_id: str, title: str, *, source: str = "explicit"
    ) -> Topic:
        # Ensure a valid previous pointer exists before changing it.
        current = self.current_topic(account_id, peer_id)
        topic_id = self._new_id()
        now = self._now()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO topics
                   (account_id, peer_id, topic_id, title, source, created_at, last_active_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account_id, peer_id, topic_id, title, source, now, now),
            )
            cursor = connection.execute(
                """UPDATE peer_state
                   SET previous_topic_id = current_topic_id,
                       current_topic_id = ?, revision = revision + 1
                   WHERE account_id = ? AND peer_id = ? AND current_topic_id = ?""",
                (topic_id, account_id, peer_id, current.topic_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("话题已被另一条消息切换，请重试")
        return Topic(topic_id, title, source, now, now, False)

    def list_topics(self, account_id: str, peer_id: str, *, limit: int = 10) -> list[Topic]:
        self.current_topic(account_id, peer_id)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """SELECT * FROM topics
                   WHERE account_id = ? AND peer_id = ? AND archived = 0
                   ORDER BY last_active_at DESC LIMIT ?""",
                (account_id, peer_id, max(1, min(int(limit), 50))),
            ).fetchall()
            return [self._topic(row) for row in rows]

    def switch_topic(self, account_id: str, peer_id: str, short_id: str) -> Topic:
        current = self.current_topic(account_id, peer_id)
        needle = short_id.strip().lower().lstrip("#")
        if len(needle) < 4 or not re.fullmatch(r"[0-9a-f]+", needle):
            raise ValueError("请输入话题列表中的短编号")
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """SELECT * FROM topics
                   WHERE account_id = ? AND peer_id = ? AND archived = 0
                     AND lower(topic_id) LIKE ?""",
                (account_id, peer_id, f"{needle}%"),
            ).fetchall()
            if not rows:
                raise ValueError("没有找到这个话题")
            if len(rows) > 1:
                raise ValueError("编号不够明确，请多输入几位")
            target = self._topic(rows[0])
            if target.topic_id == current.topic_id:
                return target
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE peer_state
                   SET previous_topic_id = current_topic_id,
                       current_topic_id = ?, revision = revision + 1
                   WHERE account_id = ? AND peer_id = ? AND current_topic_id = ?""",
                (target.topic_id, account_id, peer_id, current.topic_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("话题已被另一条消息切换，请重试")
            connection.execute(
                """UPDATE topics SET last_active_at = ?
                   WHERE account_id = ? AND peer_id = ? AND topic_id = ?""",
                (self._now(), account_id, peer_id, target.topic_id),
            )
            return target

    def undo_switch(self, account_id: str, peer_id: str) -> Topic:
        current = self.current_topic(account_id, peer_id)
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute(
                """SELECT previous_topic_id FROM peer_state
                   WHERE account_id = ? AND peer_id = ?""",
                (account_id, peer_id),
            ).fetchone()
            previous_id = state["previous_topic_id"] if state else None
            if not previous_id:
                raise ValueError("没有可以撤销的切换")
            row = connection.execute(
                """SELECT * FROM topics
                   WHERE account_id = ? AND peer_id = ? AND topic_id = ?""",
                (account_id, peer_id, previous_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("上一个话题索引损坏；未修改当前话题")
            connection.execute(
                """UPDATE peer_state
                   SET current_topic_id = ?, previous_topic_id = ?, revision = revision + 1
                   WHERE account_id = ? AND peer_id = ?""",
                (previous_id, current.topic_id, account_id, peer_id),
            )
            return self._topic(row)

    def archive_current(self, account_id: str, peer_id: str) -> tuple[Topic, Topic]:
        old = self.current_topic(account_id, peer_id)
        new = self.create_topic(account_id, peer_id, "未命名话题")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """UPDATE topics SET archived = 1
                   WHERE account_id = ? AND peer_id = ? AND topic_id = ?""",
                (account_id, peer_id, old.topic_id),
            )
        return old, new

    @staticmethod
    def _topic(row: sqlite3.Row) -> Topic:
        return Topic(
            topic_id=row["topic_id"],
            title=row["title"],
            source=row["source"],
            created_at=row["created_at"],
            last_active_at=row["last_active_at"],
            archived=bool(row["archived"]),
        )


_NEW_WITH_CONTENT = (
    re.compile(r"^/new(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^新话题\s*[：:]\s*(.+)$", re.DOTALL),
    re.compile(r"^换个话题\s*[，,]\s*(.+)$", re.DOTALL),
)
_NEW_ONLY = {"/new", "新话题", "换话题", "换个话题"}
_SWITCH = re.compile(r"^切到\s*#?([0-9a-fA-F]{4,32})$")


class TopicRoutingModule:
    """Serialize decisions per peer and map explicit commands to topic IDs."""

    def __init__(self, store: TopicStore, account_id: str):
        self.store = store
        self.account_id = account_id or "default"
        self._locks: dict[str, asyncio.Lock] = {}

    async def decide(self, message) -> RoutingDecision:
        source = message.source
        peer_id = str(source.user_id or source.chat_id)
        lock = self._locks.setdefault(peer_id, asyncio.Lock())
        async with lock:
            if not self.store.claim_message(self.account_id, getattr(message, "message_id", None)):
                return RoutingDecision(action="reply", reply="")
            return self._decide(peer_id, (message.text or "").strip())

    def _decide(self, peer_id: str, text: str) -> RoutingDecision:
        if text in _NEW_ONLY:
            topic = self.store.create_topic(self.account_id, peer_id, "未命名话题")
            return RoutingDecision(
                action="reply",
                reply=f"已开启新话题 #{topic.short_id}。下一条消息会进入新会话。",
                reason="explicit",
            )

        for pattern in _NEW_WITH_CONTENT:
            match = pattern.fullmatch(text)
            if match and match.group(1):
                content = match.group(1).strip()
                topic = self.store.create_topic(
                    self.account_id, peer_id, _title_from(content)
                )
                return RoutingDecision(
                    action="route",
                    topic_id=topic.topic_id,
                    content=content,
                    reason="explicit",
                )

        if text == "话题列表":
            current = self.store.current_topic(self.account_id, peer_id)
            topics = self.store.list_topics(self.account_id, peer_id)
            lines = ["最近话题："]
            for topic in topics:
                marker = "→" if topic.topic_id == current.topic_id else " "
                lines.append(f"{marker} #{topic.short_id} {topic.title}")
            lines.append("发送“切到 <编号>”即可恢复该话题。")
            return RoutingDecision(action="reply", reply="\n".join(lines))

        if text == "当前话题":
            topic = self.store.current_topic(self.account_id, peer_id)
            return RoutingDecision(
                action="reply", reply=f"当前话题：#{topic.short_id} {topic.title}"
            )

        switch = _SWITCH.fullmatch(text)
        if switch:
            try:
                topic = self.store.switch_topic(self.account_id, peer_id, switch.group(1))
                reply = f"已切到 #{topic.short_id} {topic.title}。"
            except ValueError as error:
                reply = str(error)
            return RoutingDecision(action="reply", reply=reply, reason="switch")

        if text == "撤销切换":
            try:
                topic = self.store.undo_switch(self.account_id, peer_id)
                reply = f"已返回 #{topic.short_id} {topic.title}。"
            except ValueError as error:
                reply = str(error)
            return RoutingDecision(action="reply", reply=reply, reason="undo")

        if text == "归档当前话题":
            old, new = self.store.archive_current(self.account_id, peer_id)
            return RoutingDecision(
                action="reply",
                reply=(
                    f"已归档 #{old.short_id} {old.title}；"
                    f"当前为新话题 #{new.short_id}。"
                ),
                reason="explicit",
            )

        topic = self.store.current_topic(self.account_id, peer_id)
        self.store.touch(self.account_id, peer_id, topic.topic_id)
        return RoutingDecision(
            action="route", topic_id=topic.topic_id, content=text, reason="current"
        )


def _title_from(content: str) -> str:
    one_line = " ".join(content.split())
    return one_line[:24] + ("…" if len(one_line) > 24 else "")
