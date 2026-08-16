from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from runtime.assets import 宪制资产


class 对话消息(TypedDict):
    role: str
    content: str


运行包装 = "以下 Kernel 与 Memory Constitution 为 Wenlong 的 canonical governing context，由 Runtime 从正式文件动态加载。"


def 组装上下文(assets: 宪制资产, history: Sequence[对话消息], user_input: str) -> list[对话消息]:
    """按固定顺序组装本轮上下文，不加载 Persona。"""
    context: list[对话消息] = [
        {"role": "system", "content": 运行包装},
        {"role": "system", "content": assets.kernel},
        {"role": "system", "content": assets.memory_constitution},
    ]
    context.extend({"role": item["role"], "content": item["content"]} for item in history)
    context.append({"role": "user", "content": user_input})
    return context


def 组装外部上下文(assets: 宪制资产, history: Sequence[对话消息]) -> list[对话消息]:
    """外部前台携带历史时，只追加已过滤的 user/assistant 内容。"""
    context: list[对话消息] = [
        {"role": "system", "content": 运行包装},
        {"role": "system", "content": assets.kernel},
        {"role": "system", "content": assets.memory_constitution},
    ]
    context.extend({"role": item["role"], "content": item["content"]} for item in history)
    return context
