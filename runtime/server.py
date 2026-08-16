from __future__ import annotations

import hmac
import json
import os
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from runtime.context import 对话消息
from runtime.core import 文龙运行时, 本轮失败


class Bridge配置错误(RuntimeError):
    pass


def 读取桥接密钥() -> str:
    key = os.environ.get("WENLONG_BRIDGE_API_KEY", "").strip()
    if not key:
        raise Bridge配置错误("缺少 WENLONG_BRIDGE_API_KEY，拒绝启动本机 Bridge。")
    return key


class _BridgeHandler(BaseHTTPRequestHandler):
    server: "WorkBuddy服务"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._frontend()
        elif path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok", "service": "wenlong", "version": "0.1"})
        elif path == "/v1/models":
            if self._authorized():
                self._json(HTTPStatus.OK, {"object": "list", "data": [{"id": "wenlong", "object": "model", "owned_by": "wenlong-system"}]})
        else:
            self._error(HTTPStatus.NOT_FOUND, "未找到接口。", "not_found")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/v1/chat/completions":
            self._error(HTTPStatus.NOT_FOUND, "未找到接口。", "not_found")
            return
        if not self._authorized():
            return
        try:
            payload = self._body()
            history = self._history(payload)
            result = self.server.runtime.处理外部对话(history, str(uuid.uuid4()))
        except 请求错误 as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error), "invalid_request_error")
            return
        except 本轮失败 as error:
            self._error(HTTPStatus.BAD_GATEWAY, str(error), "upstream_error")
            return
        completion_id = f"chatcmpl-{uuid.uuid4()}"
        created = int(time.time())
        if payload.get("stream") is True:
            self._sse(completion_id, created, result.content)
        else:
            self._json(HTTPStatus.OK, {"id": completion_id, "object": "chat.completion", "created": created, "model": "wenlong", "choices": [{"index": 0, "message": {"role": "assistant", "content": result.content}, "finish_reason": "stop"}]})

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.bridge_key}"
        received = self.headers.get("Authorization", "")
        if not hmac.compare_digest(received, expected):
            self._error(HTTPStatus.UNAUTHORIZED, "Bridge 鉴权失败。", "authentication_error")
            return False
        return True

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            raise 请求错误("请求 JSON 无效。") from None
        if not isinstance(value, dict):
            raise 请求错误("请求 JSON 无效。")
        return value

    def _history(self, payload: dict[str, Any]) -> list[对话消息]:
        if payload.get("model") != "wenlong":
            raise 请求错误("model 必须为 wenlong。")
        # 顶层工具声明只是客户端能力元数据，不进入文龙上下文，也不触发工具调用。
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise 请求错误("messages 必须为非空数组。")
        history: list[对话消息] = []
        for message in messages:
            if not isinstance(message, dict):
                raise 请求错误("messages 包含无效项。")
            role = message.get("role")
            if role in {"tool", "function"} or message.get("tool_calls"):
                raise 请求错误("WorkBuddy Bridge V0.1 暂不支持 tool calling。")
            if role in {"system", "developer"}:
                continue
            content = message.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                raise 请求错误("仅支持 user 与 assistant 文本消息。")
            history.append({"role": role, "content": content})
        if not history:
            raise 请求错误("messages 未包含可用对话内容。")
        return history

    def _json(self, status: HTTPStatus, value: object) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _frontend(self) -> None:
        path = Path(__file__).resolve().parent.parent / "web" / "index.html"
        try:
            body = path.read_bytes()
        except OSError:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "本机页面不可用。", "frontend_error")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, completion_id: str, created: int, content: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        chunks = [
            {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": "wenlong", "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]},
            {"id": completion_id, "object": "chat.completion.chunk", "created": created, "model": "wenlong", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        for chunk in chunks:
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def _error(self, status: HTTPStatus, message: str, code: str) -> None:
        self._json(status, {"error": {"message": message, "type": code, "code": code}})


class 请求错误(RuntimeError):
    pass


class WorkBuddy服务(ThreadingHTTPServer):
    def __init__(self, runtime: 文龙运行时, bridge_key: str, port: int) -> None:
        self.runtime = runtime
        self.bridge_key = bridge_key
        super().__init__(("127.0.0.1", port), _BridgeHandler)


def 启动服务(runtime: 文龙运行时, bridge_key: str, port: int) -> None:
    server = WorkBuddy服务(runtime, bridge_key, port)
    print(f"WorkBuddy Bridge 已监听 http://127.0.0.1:{port}/v1")
    try:
        server.serve_forever()
    finally:
        server.server_close()
