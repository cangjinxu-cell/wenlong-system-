from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
SUPPORTED_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}


class 配置错误(RuntimeError):
    pass


@dataclass(frozen=True)
class 运行配置:
    api_key: str
    base_url: str
    model: str

    @classmethod
    def 从环境读取(cls) -> "运行配置":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise 配置错误("缺少 DEEPSEEK_API_KEY，无法启动交互。")
        base_url = os.environ.get("WENLONG_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
        model = os.environ.get("WENLONG_MODEL", DEFAULT_MODEL).strip()
        if not base_url:
            raise 配置错误("WENLONG_BASE_URL 不能为空。")
        if model not in SUPPORTED_MODELS:
            choices = "、".join(sorted(SUPPORTED_MODELS))
            raise 配置错误(f"WENLONG_MODEL 仅支持：{choices}。")
        return cls(api_key=api_key, base_url=base_url, model=model)


def 运行目录() -> Path:
    configured = os.environ.get("WENLONG_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".wenlong"
