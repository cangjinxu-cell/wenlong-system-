from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from adapters.model import 模型结果, 模型适配器
from adapters.openai_compatible import OpenAICompatibleAdapter, 模型调用错误
from runtime.assets import 宪制加载器, 宪制资产
from runtime.config import 运行配置, 运行目录
from runtime.context import 组装上下文
from runtime.session import 会话, 会话存储
from runtime.trace import 追踪记录器


class 本轮失败(RuntimeError):
    pass


@dataclass(frozen=True)
class 轮次结果:
    session: 会话
    content: str


class 文龙运行时:
    def __init__(self, assets: 宪制资产, store: 会话存储, adapter: 模型适配器) -> None:
        self.assets = assets
        self.store = store
        self.adapter = adapter
        self.traces = 追踪记录器(store.traces_dir)

    @classmethod
    def 从环境启动(cls, repository_root: Path | None = None) -> "文龙运行时":
        assets = 宪制加载器(repository_root).加载()
        config = 运行配置.从环境读取()
        adapter = OpenAICompatibleAdapter(config.base_url, config.api_key, config.model)
        return cls(assets, 会话存储(运行目录()), adapter)

    def 新建会话(self) -> 会话:
        return self.store.新建()

    def 恢复会话(self, session_id: str) -> 会话:
        return self.store.加载(session_id)

    def 处理输入(self, session: 会话, user_input: str) -> 轮次结果:
        turn_id = str(uuid.uuid4())
        started_at = self.traces.开始时间()
        context = 组装上下文(self.assets, [message.对话() for message in session.messages], user_input)
        try:
            result = self.adapter.complete(context)
            updated, user, assistant = session.添加完整轮次(user_input, result.content, turn_id)
            self.store.保存(updated)
        except Exception as error:
            self._记录失败(session.session_id, turn_id, started_at, error)
            if isinstance(error, 模型调用错误):
                raise 本轮失败(str(error)) from None
            raise 本轮失败("本轮未完成，会话未写入新的半截记录。") from None
        self.traces.记录(
            session.session_id,
            turn_id=turn_id,
            started_at=started_at,
            completed_at=self.traces.完成时间(),
            status="success",
            provider=result.provider,
            adapter="openai-compatible",
            model=result.model,
            kernel_sha256=self.assets.kernel_sha256,
            memory_constitution_sha256=self.assets.memory_constitution_sha256,
            user_message_id=user.message_id,
            assistant_message_id=assistant.message_id,
        )
        return 轮次结果(updated, result.content)

    def _记录失败(self, session_id: str, turn_id: str, started_at: str, error: Exception) -> None:
        self.traces.记录(
            session_id,
            turn_id=turn_id,
            started_at=started_at,
            completed_at=self.traces.完成时间(),
            status="failure",
            provider=getattr(self.adapter, "provider", "unknown"),
            adapter="openai-compatible",
            model=getattr(self.adapter, "model", "unknown"),
            kernel_sha256=self.assets.kernel_sha256,
            memory_constitution_sha256=self.assets.memory_constitution_sha256,
            user_message_id=None,
            assistant_message_id=None,
            error_type=type(error).__name__,
            error_code=getattr(error, "code", None),
        )
