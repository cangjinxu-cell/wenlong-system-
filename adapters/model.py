from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from runtime.context import 对话消息


@dataclass(frozen=True)
class 模型结果:
    content: str
    provider: str
    model: str


class 模型适配器(Protocol):
    provider: str
    model: str

    def complete(self, messages: Sequence[对话消息]) -> 模型结果:
        ...


# 对外保留协议层的通用名称，便于后续替换 Provider。
ModelAdapter = 模型适配器
