from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class 配置错误(RuntimeError):
    pass


@dataclass(frozen=True)
class 运行配置:
    api_key: str
    base_url: str
    model: str

    @classmethod
    def 从环境读取(cls) -> "运行配置":
        api_key = os.environ.get("WENLONG_API_KEY", "").strip()
        base_url = os.environ.get("WENLONG_BASE_URL", "").strip().rstrip("/")
        model = os.environ.get("WENLONG_MODEL", "").strip()
        missing = [name for name, value in (("WENLONG_API_KEY", api_key), ("WENLONG_BASE_URL", base_url), ("WENLONG_MODEL", model)) if not value]
        if missing:
            raise 配置错误(f"缺少运行配置：{'、'.join(missing)}。")
        return cls(api_key=api_key, base_url=base_url, model=model)


def 运行目录() -> Path:
    configured = os.environ.get("WENLONG_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".wenlong"
