from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from runtime.context import 对话消息


class 会话错误(RuntimeError):
    pass


def _时间() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class 消息:
    message_id: str
    turn_id: str
    role: str
    content: str
    created_at: str

    def 对外字典(self) -> dict[str, str]:
        return self.__dict__.copy()

    def 对话(self) -> 对话消息:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class 会话:
    session_id: str
    created_at: str
    updated_at: str
    messages: tuple[消息, ...]
    schema_version: str = "0.1"

    @classmethod
    def 新建(cls) -> "会话":
        now = _时间()
        return cls(str(uuid.uuid4()), now, now, ())

    def 添加完整轮次(self, user_content: str, assistant_content: str, turn_id: str) -> tuple["会话", 消息, 消息]:
        now = _时间()
        user = 消息(str(uuid.uuid4()), turn_id, "user", user_content, now)
        assistant = 消息(str(uuid.uuid4()), turn_id, "assistant", assistant_content, now)
        return replace(self, messages=self.messages + (user, assistant), updated_at=now), user, assistant

    def 对外字典(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [message.对外字典() for message in self.messages],
        }

    @classmethod
    def 从字典(cls, data: object, path: Path) -> "会话":
        try:
            if not isinstance(data, dict) or data.get("schema_version") != "0.1":
                raise ValueError("schema_version 无效")
            raw_messages = data["messages"]
            if not isinstance(raw_messages, list):
                raise ValueError("messages 无效")
            messages = tuple(
                消息(
                    message_id=str(item["message_id"]),
                    turn_id=str(item["turn_id"]),
                    role=str(item["role"]),
                    content=str(item["content"]),
                    created_at=str(item["created_at"]),
                )
                for item in raw_messages
            )
            if any(message.role not in {"user", "assistant"} for message in messages):
                raise ValueError("消息角色无效")
            return cls(str(data["session_id"]), str(data["created_at"]), str(data["updated_at"]), messages)
        except (KeyError, TypeError, ValueError) as error:
            raise 会话错误(f"会话文件已损坏，拒绝覆盖：{path}") from error


class 会话存储:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.sessions_dir = home / "sessions"
        self.traces_dir = home / "traces"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    def 新建(self) -> 会话:
        session = 会话.新建()
        self._原子写入(session, verify_existing=False)
        return session

    def 加载(self, session_id: str) -> 会话:
        path = self._路径(session_id)
        if not path.exists():
            raise 会话错误(f"未找到会话：{session_id}")
        return self._读取(path)

    def 保存(self, session: 会话) -> None:
        path = self._路径(session.session_id)
        if path.exists():
            self._读取(path)
        self._原子写入(session, verify_existing=False)

    def 列表(self) -> list[会话]:
        return sorted((self._读取(path) for path in self.sessions_dir.glob("*.json")), key=lambda item: item.updated_at, reverse=True)

    def _路径(self, session_id: str) -> Path:
        if not session_id or any(char not in "0123456789abcdef-" for char in session_id.lower()):
            raise 会话错误("会话标识格式无效。")
        return self.sessions_dir / f"{session_id}.json"

    def _读取(self, path: Path) -> 会话:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise 会话错误(f"会话文件已损坏，拒绝覆盖：{path}") from error
        return 会话.从字典(data, path)

    def _原子写入(self, session: 会话, verify_existing: bool) -> None:
        path = self._路径(session.session_id)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{session.session_id}.", suffix=".tmp", dir=self.sessions_dir)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(session.对外字典(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError as error:
            raise 会话错误(f"无法安全写入会话：{path}") from error
        finally:
            if temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
