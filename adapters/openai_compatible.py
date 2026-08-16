from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from adapters.model import 模型结果
from runtime.context import 对话消息


class 模型调用错误(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        content_type: str | None = None,
        response_bytes: int | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.content_type = content_type
        self.response_bytes = response_bytes


传输函数 = Callable[[str, Mapping[str, object], Mapping[str, str], float], Mapping[str, Any]]


def 默认传输(url: str, payload: Mapping[str, object], headers: Mapping[str, str], timeout: float) -> Mapping[str, Any]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            http_status = getattr(response, "status", None)
            response_headers = getattr(response, "headers", None)
            content_type = response_headers.get("Content-Type") if response_headers is not None else None
    except HTTPError as error:
        raise 模型调用错误(
            f"模型服务返回 HTTP {error.code}。",
            http_status=error.code,
            content_type=error.headers.get("Content-Type") if error.headers else None,
        ) from None
    except URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise 模型调用错误("模型服务响应超时。") from None
        raise 模型调用错误("无法连接模型服务，请检查网络或服务状态。") from None
    except TimeoutError:
        raise 模型调用错误("模型服务响应超时。") from None
    except OSError:
        raise 模型调用错误("模型服务返回了无法识别的响应。") from None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise 模型调用错误(
            "模型服务返回了无法识别的响应。",
            http_status=http_status,
            content_type=content_type,
            response_bytes=len(raw),
        ) from None
    if not isinstance(decoded, Mapping):
        raise 模型调用错误("模型服务返回了无效响应。")
    return decoded


class OpenAICompatibleAdapter:
    """通用 OpenAI-compatible 协议层；Provider 通过配置提供。"""

    def __init__(self, base_url: str, api_key: str, model: str, provider: str = "openai-compatible-relay", transport: 传输函数 = 默认传输) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self._transport = transport

    def complete(self, messages: Sequence[对话消息]) -> 模型结果:
        payload: dict[str, object] = {"model": self.model, "messages": list(messages), "stream": False}
        try:
            response = self._transport(
                f"{self.base_url}/chat/completions",
                payload,
                {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                120.0,
            )
        except 模型调用错误:
            raise
        except TimeoutError:
            raise 模型调用错误("模型服务响应超时。") from None
        except OSError:
            raise 模型调用错误("无法连接模型服务，请检查网络或服务状态。") from None
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise 模型调用错误("模型服务未返回有效的助手回答。") from None
        if not isinstance(content, str) or not content.strip():
            raise 模型调用错误("模型服务未返回有效的助手回答。")
        return 模型结果(content=content, provider=self.provider, model=self.model)
