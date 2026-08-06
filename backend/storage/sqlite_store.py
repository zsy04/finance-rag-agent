"""SQLite 持久化存储 — MemoryStore 接口实现

grill 定案（2026-08-05）：SQLite 标准库零依赖（答辩零风险），
MongoDB 降级为"后期迁移"目标 —— 靠 MemoryStore 抽象层 + 一次性迁移脚本实现，
结构固定可平滑迁移。不引入 Redis（单进程单用户无缓存需求）。

三张表：
  threads         会话注册表（thread_id → 创建/更新时间）
  messages        对话历史（完整 Message JSON 存 payload，role/content 为冗余列便于 SQL 过滤）
  user_contexts   用户画像（主键 user_id，当前 user_id = thread_id 占位，登录体系后零返工）

并发模型：单连接 + 全局写锁。
  毕设 demo 单进程单用户；sqlite3 默认单连接串行，锁是"跨线程读 + 写"的兜底。
  多进程部署时：SQLite WAL 模式 or 按规划迁移 MongoDB（仅换实现类）。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from config import SQLITE_DB_PATH

logger = logging.getLogger(__name__)

# 全局写锁：sqlite3 连接默认单连接串行，锁兜底"多线程同时写"
_write_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    thread_id  TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id  TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    payload    TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, id);

CREATE TABLE IF NOT EXISTS user_contexts (
    user_id    TEXT PRIMARY KEY,
    data       TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    """本地时间 ISO 串（demo 单机，无时区换算需求）"""
    return datetime.now().isoformat(timespec="seconds")


class MemoryStore(ABC):
    """存储抽象层：业务侧只依赖本接口，后期换 MongoDB 仅换实现类，业务零改动。"""

    # ── 会话 / 消息 ──
    @abstractmethod
    def ensure_thread(self, thread_id: str) -> None:
        """确保会话存在（幂等），不存在则注册"""

    @abstractmethod
    def get_history(self, thread_id: str) -> list[dict]:
        """返回会话完整历史（完整 Message JSON，时间升序）；无则 []"""

    @abstractmethod
    def append_message(self, thread_id: str, role: str, content: str, payload: dict | None = None) -> None:
        """追加一条消息；payload 为完整 Message JSON（含 role/content/附件字段）"""

    @abstractmethod
    def delete_thread(self, thread_id: str) -> None:
        """删除整个会话：消息 + 画像 + 会话记录（前端「新会话」按钮 / 换人重置用）"""

    @abstractmethod
    def list_threads(self) -> list[dict]:
        """返回全部会话列表（thread_id/标题预览/消息数/更新时间），按更新时间倒序"""

    # ── 用户画像 ──
    @abstractmethod
    def get_context(self, user_id: str) -> dict:
        """读取用户画像 dict；无则 {}"""

    @abstractmethod
    def update_context(self, user_id: str, key: str, value: str) -> dict:
        """写入/更新画像单项，返回更新后的完整画像 dict"""


class SQLiteStore(MemoryStore):
    """SQLite 实现（sqlite3 标准库，零外部依赖）"""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = str(db_path or SQLITE_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：FastAPI 异步线程池中调用，连接跨线程复用
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with _write_lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        logger.info("SQLiteStore 就绪: %s", self._db_path)

    def __del__(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # ── 会话 / 消息 ──
    def ensure_thread(self, thread_id: str) -> None:
        now = _now()
        with _write_lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO threads (thread_id, created_at, updated_at) VALUES (?, ?, ?)",
                (thread_id, now, now),
            )
            if cur.rowcount == 0:
                self._conn.execute(
                    "UPDATE threads SET updated_at = ? WHERE thread_id = ?", (now, thread_id)
                )
            self._conn.commit()

    def get_history(self, thread_id: str) -> list[dict]:
        with _write_lock:
            rows = self._conn.execute(
                "SELECT payload FROM messages WHERE thread_id = ? ORDER BY id ASC",
                (thread_id,),
            ).fetchall()
        history: list[dict] = []
        for row in rows:
            try:
                msg = json.loads(row["payload"])
                if isinstance(msg, dict) and msg.get("role"):
                    history.append(msg)
            except (json.JSONDecodeError, TypeError):
                logger.warning("消息 payload 解析失败，跳过: thread=%s", thread_id)
        return history

    def append_message(self, thread_id: str, role: str, content: str, payload: dict | None = None) -> None:
        self.ensure_thread(thread_id)
        body = payload if payload is not None else {"role": role, "content": content}
        with _write_lock:
            self._conn.execute(
                "INSERT INTO messages (thread_id, role, content, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (thread_id, role, content, json.dumps(body, ensure_ascii=False), _now()),
            )
            self._conn.execute(
                "UPDATE threads SET updated_at = ? WHERE thread_id = ?", (_now(), thread_id)
            )
            self._conn.commit()

    def delete_thread(self, thread_id: str) -> None:
        """删除会话及其全部消息与画像（幂等：不存在也不报错）"""
        with _write_lock:
            self._conn.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM user_contexts WHERE user_id = ?", (thread_id,))
            self._conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
            self._conn.commit()

    def list_threads(self) -> list[dict]:
        """全部会话列表，按更新时间倒序；标题 = 首条 user 消息内容前 20 字"""
        with _write_lock:
            rows = self._conn.execute(
                """
                SELECT t.thread_id, t.updated_at,
                       (SELECT COUNT(*) FROM messages m
                        WHERE m.thread_id = t.thread_id) AS msg_count,
                       (SELECT payload FROM messages m
                        WHERE m.thread_id = t.thread_id AND m.role = 'user'
                        ORDER BY m.id ASC LIMIT 1) AS first_payload
                FROM threads t
                ORDER BY t.updated_at DESC
                """
            ).fetchall()
        threads: list[dict] = []
        for r in rows:
            title = ""
            if r["first_payload"]:
                try:
                    content = json.loads(r["first_payload"]).get("content", "") or ""
                    title = " ".join(content.split())[:20]
                except (json.JSONDecodeError, TypeError):
                    title = ""
            threads.append({
                "thread_id": r["thread_id"],
                "title": title,
                "message_count": r["msg_count"],
                "updated_at": r["updated_at"],
            })
        return threads

    # ── 用户画像 ──
    def get_context(self, user_id: str) -> dict:
        with _write_lock:
            row = self._conn.execute(
                "SELECT data FROM user_contexts WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return {}
        try:
            data = json.loads(row["data"])
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning("画像 JSON 解析失败，重置: user_id=%s", user_id)
            return {}

    def update_context(self, user_id: str, key: str, value: str) -> dict:
        ctx = self.get_context(user_id)
        ctx[key] = value
        with _write_lock:
            self._conn.execute(
                "INSERT INTO user_contexts (user_id, data, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
                (user_id, json.dumps(ctx, ensure_ascii=False), _now()),
            )
            self._conn.commit()
        return ctx


# ── 全局单例（懒加载 + 双重检查锁，与 get_agent()/get_retriever() 模式一致）──
_store: MemoryStore | None = None
_store_lock = threading.Lock()


def get_store() -> MemoryStore:
    """获取全局存储单例（线程安全）"""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SQLiteStore()
    return _store
