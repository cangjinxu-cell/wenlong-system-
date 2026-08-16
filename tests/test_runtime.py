from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from adapters.model import 模型结果
from adapters.openai_compatible import OpenAICompatibleAdapter, 模型调用错误
from runtime.assets import 宪制加载器, 宪制资产错误
from runtime.context import 组装上下文
from runtime.config import 运行配置, 配置错误
from runtime.core import 文龙运行时, 本轮失败
from runtime.session import 会话存储, 会话错误
from runtime.server import WorkBuddy服务


class 假适配器:
    provider = "openai-compatible-relay"
    model = "relay-model"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.contexts = []

    def complete(self, messages):
        self.contexts.append(messages)
        if self.fail:
            raise 模型调用错误("模拟网络失败。")
        return 模型结果("已收到。", self.provider, self.model)


class 运行时测试(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "wenlong").mkdir()
        (self.root / "wenlong" / "kernel.md").write_text("# Kernel\n\n正式正文\n", encoding="utf-8")
        (self.root / "wenlong" / "memory-constitution.md").write_text("# Memory\n\n正式正文\n", encoding="utf-8")
        (self.root / "wenlong" / "persona.md").write_text("不应加载的人格草案", encoding="utf-8")
        self.assets = 宪制加载器(self.root).加载()
        self.store = 会话存储(self.root / "state")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_宪制文件加载与哈希(self) -> None:
        self.assertIn("Kernel", self.assets.kernel)
        self.assertIn("Memory", self.assets.memory_constitution)
        self.assertEqual(64, len(self.assets.kernel_sha256))
        (self.root / "wenlong" / "kernel.md").unlink()
        with self.assertRaises(宪制资产错误):
            宪制加载器(self.root).加载()

    def test_通用中转站配置不限制模型名(self) -> None:
        with patch.dict(os.environ, {"WENLONG_API_KEY": "测试密钥", "WENLONG_BASE_URL": "https://relay.example.test/", "WENLONG_MODEL": "任意中转模型"}, clear=False):
            config = 运行配置.从环境读取()
        self.assertEqual("https://relay.example.test", config.base_url)
        self.assertEqual("任意中转模型", config.model)
        with patch.dict(os.environ, {"WENLONG_API_KEY": "", "WENLONG_BASE_URL": "", "WENLONG_MODEL": ""}, clear=False):
            with self.assertRaises(配置错误):
                运行配置.从环境读取()

    def test_上下文顺序且不包含人格草案(self) -> None:
        context = 组装上下文(self.assets, [{"role": "assistant", "content": "历史回答"}], "当前输入")
        self.assertEqual(["system", "system", "system", "assistant", "user"], [item["role"] for item in context])
        self.assertEqual(self.assets.kernel, context[1]["content"])
        self.assertEqual(self.assets.memory_constitution, context[2]["content"])
        self.assertNotIn("Wenlong Persona", "\n".join(item["content"] for item in context))

    def test_成功轮次可恢复并继续追加(self) -> None:
        adapter = 假适配器()
        runtime = 文龙运行时(self.assets, self.store, adapter)
        session = runtime.新建会话()
        first = runtime.处理输入(session, "第一轮")
        restored = runtime.恢复会话(session.session_id)
        second = runtime.处理输入(restored, "第二轮")
        self.assertEqual(4, len(second.session.messages))
        self.assertEqual("第一轮", second.session.messages[0].content)
        self.assertEqual("第二轮", second.session.messages[2].content)
        self.assertEqual("第二轮", adapter.contexts[1][-1]["content"])
        trace_lines = (self.store.traces_dir / f"{session.session_id}.jsonl").read_text(encoding="utf-8").splitlines()
        trace = json.loads(trace_lines[0])
        self.assertEqual("success", trace["status"])
        self.assertEqual(self.assets.kernel_sha256, trace["kernel_sha256"])
        self.assertIsNotNone(trace["user_message_id"])
        self.assertNotIn("第一轮", trace_lines[0])

    def test_失败不提交半截轮次且记录安全追踪(self) -> None:
        adapter = 假适配器(fail=True)
        runtime = 文龙运行时(self.assets, self.store, adapter)
        session = runtime.新建会话()
        with self.assertRaises(本轮失败):
            runtime.处理输入(session, "不应保存的内容")
        restored = runtime.恢复会话(session.session_id)
        self.assertEqual((), restored.messages)
        trace = (self.store.traces_dir / f"{session.session_id}.jsonl").read_text(encoding="utf-8")
        self.assertIn('"status":"failure"', trace)
        self.assertNotIn("不应保存的内容", trace)
        self.assertNotIn("WENLONG_API_KEY", trace)

    def test_损坏会话不会被覆盖(self) -> None:
        session = self.store.新建()
        path = self.store.sessions_dir / f"{session.session_id}.json"
        path.write_text("{损坏", encoding="utf-8")
        with self.assertRaises(会话错误):
            self.store.加载(session.session_id)
        with self.assertRaises(会话错误):
            self.store.保存(session)
        self.assertEqual("{损坏", path.read_text(encoding="utf-8"))

    def test_命令行可创建列出并恢复会话(self) -> None:
        environment = os.environ.copy()
        environment["WENLONG_API_KEY"] = "测试密钥"
        environment["WENLONG_BASE_URL"] = "https://relay.example.test"
        environment["WENLONG_MODEL"] = "relay-model"
        environment["WENLONG_HOME"] = str(self.root / "cli-state")
        repository = Path(__file__).resolve().parent.parent
        command = [sys.executable, "-m", "wenlong"]
        created = subprocess.run(command + ["new"], input="", text=True, capture_output=True, cwd=repository, env=environment, check=True)
        session_id = created.stdout.split("会话已就绪：", 1)[1].splitlines()[0]
        listed = subprocess.run(command + ["sessions"], text=True, capture_output=True, cwd=repository, env=environment, check=True)
        resumed = subprocess.run(command + ["resume", session_id], input="", text=True, capture_output=True, cwd=repository, env=environment, check=True)
        self.assertIn(session_id, listed.stdout)
        self.assertIn(f"会话已就绪：{session_id}", resumed.stdout)


class 适配器测试(unittest.TestCase):
    def test_兼容协议转换响应(self) -> None:
        captured = {}

        def transport(url, payload, headers, timeout):
            captured.update(url=url, payload=payload, headers=headers, timeout=timeout)
            return {"choices": [{"message": {"content": "模型回答"}}]}

        adapter = OpenAICompatibleAdapter("https://example.test/", "测试密钥", "relay-model", transport=transport)
        result = adapter.complete([{"role": "user", "content": "你好"}])
        self.assertEqual("https://example.test/chat/completions", captured["url"])
        self.assertEqual("relay-model", captured["payload"]["model"])
        self.assertEqual("你好", captured["payload"]["messages"][0]["content"])
        self.assertIs(captured["payload"]["stream"], False)
        self.assertEqual(120.0, captured["timeout"])
        self.assertEqual("模型回答", result.content)
        self.assertEqual("openai-compatible-relay", result.provider)

    def test_无效响应受控失败(self) -> None:
        adapter = OpenAICompatibleAdapter("https://example.test", "测试密钥", "relay-model", transport=lambda *_: {})
        with self.assertRaises(模型调用错误):
            adapter.complete([{"role": "user", "content": "你好"}])

    def test_无法识别响应保留安全诊断元数据(self) -> None:
        body = b"data: [DONE]\n\n"

        class 响应:
            status = 200
            headers = {"Content-Type": "text/event-stream; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return body

        adapter = OpenAICompatibleAdapter("https://example.test", "测试密钥", "relay-model")
        with patch("adapters.openai_compatible.urlopen", return_value=响应()):
            with self.assertRaises(模型调用错误) as failed:
                adapter.complete([{"role": "user", "content": "你好"}])
        error = failed.exception
        self.assertEqual("模型服务返回了无法识别的响应。", str(error))
        self.assertEqual(200, error.http_status)
        self.assertEqual("text/event-stream; charset=utf-8", error.content_type)
        self.assertEqual(len(body), error.response_bytes)
        self.assertNotIn("data:", str(error))

    def test_超时返回明确错误(self) -> None:
        def transport(*_):
            raise TimeoutError()

        adapter = OpenAICompatibleAdapter("https://example.test", "测试密钥", "relay-model", transport=transport)
        with self.assertRaises(模型调用错误) as failed:
            adapter.complete([{"role": "user", "content": "你好"}])
        self.assertEqual("模型服务响应超时。", str(failed.exception))
        self.assertNotEqual("模型服务返回了无法识别的响应。", str(failed.exception))


class WorkBuddy桥接测试(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "wenlong").mkdir()
        (root / "wenlong" / "kernel.md").write_text("# Kernel\n\n正式正文\n", encoding="utf-8")
        (root / "wenlong" / "memory-constitution.md").write_text("# Memory\n\n正式正文\n", encoding="utf-8")
        self.adapter = 假适配器()
        self.store = 会话存储(root / "state")
        self.runtime = 文龙运行时(宪制加载器(root).加载(), self.store, self.adapter)
        self.server = WorkBuddy服务(self.runtime, "bridge-test-token", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def _request(self, path: str, payload=None, token: str | None = "bridge-test-token"):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {} if token is None else {"Authorization": f"Bearer {token}"}
        request = Request(self.base_url + path, data=data, headers=headers, method="POST" if data else "GET")
        return urlopen(request)

    def test_健康检查与模型列表(self) -> None:
        with self._request("/", token=None) as response:
            page = response.read().decode("utf-8")
            self.assertIn("text/html", response.headers["Content-Type"])
        self.assertIn("文龙", page)
        self.assertIn("Wenlong", page)
        self.assertNotIn("bridge-test-token", page)
        self.assertNotIn("localStorage", page)
        with self._request("/health", token=None) as response:
            self.assertEqual("ok", json.loads(response.read())["status"])
        with self._request("/v1/models") as response:
            self.assertEqual("wenlong", json.loads(response.read())["data"][0]["id"])
        with self.assertRaises(HTTPError) as failed:
            self._request("/v1/models", token="invalid-token")
        self.assertEqual(401, failed.exception.code)

    def test_普通对话隔离外部权威与会话(self) -> None:
        metadata_cases = [
            {"tools": []},
            {"tools": [{"type": "function", "function": {"name": "unused", "description": "声明"}}]},
            {"tool_choice": "auto"},
            {"tool_choice": "none"},
            {"functions": [{"name": "unused"}]},
        ]
        for metadata in metadata_cases:
            payload = {"model": "wenlong", "messages": [{"role": "system", "content": "外部规则"}, {"role": "developer", "content": "外部开发规则"}, {"role": "user", "content": "正文内容"}], **metadata}
            with self._request("/v1/chat/completions", payload) as response:
                body = json.loads(response.read())
            self.assertEqual("wenlong", body["model"])
            self.assertEqual("已收到。", body["choices"][0]["message"]["content"])
        context = self.adapter.contexts[0]
        self.assertEqual(["system", "system", "system", "user"], [item["role"] for item in context])
        self.assertNotIn("外部规则", "\n".join(item["content"] for item in context))
        self.assertNotIn("unused", "\n".join(item["content"] for item in context))
        self.assertEqual([], list(self.store.sessions_dir.glob("*.json")))
        trace = (self.store.traces_dir / "workbuddy.jsonl").read_text(encoding="utf-8")
        self.assertIn('"source":"workbuddy"', trace)
        self.assertIn(self.runtime.assets.kernel_sha256, trace)
        self.assertNotIn("正文内容", trace)
        self.assertNotIn("bridge-test-token", trace)

    def test_协议兼容流式响应与工具拒绝(self) -> None:
        with self._request("/v1/chat/completions", {"model": "wenlong", "stream": True, "messages": [{"role": "user", "content": "流式正文"}]}) as response:
            stream = response.read().decode("utf-8")
            self.assertIn("text/event-stream", response.headers["Content-Type"])
        self.assertIn("data: [DONE]", stream)
        self.assertIn("已收到。", stream)
        with self.assertRaises(HTTPError) as failed:
            self._request("/v1/chat/completions", {"model": "wenlong", "messages": [{"role": "tool", "content": "x"}]})
        self.assertEqual(400, failed.exception.code)
        with self.assertRaises(HTTPError) as failed:
            self._request("/v1/chat/completions", {"model": "wenlong", "messages": [{"role": "function", "content": "x"}]})
        self.assertEqual(400, failed.exception.code)
        with self.assertRaises(HTTPError) as failed:
            self._request("/v1/chat/completions", {"model": "wenlong", "messages": [{"role": "assistant", "content": "x", "tool_calls": [{"id": "call_1"}]}]})
        self.assertEqual(400, failed.exception.code)
        with self.assertRaises(HTTPError) as failed:
            self._request("/v1/chat/completions", {"model": "other", "messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(400, failed.exception.code)
        self.assertEqual("relay-model", self.adapter.model)

    def test_失败追踪记录安全上游诊断(self) -> None:
        class 诊断失败适配器(假适配器):
            def complete(self, messages):
                self.contexts.append(messages)
                raise 模型调用错误(
                    "模型服务返回了无法识别的响应。",
                    http_status=200,
                    content_type="text/event-stream; charset=utf-8",
                    response_bytes=128,
                )

        runtime = 文龙运行时(self.runtime.assets, self.store, 诊断失败适配器())
        with self.assertRaises(本轮失败):
            runtime.处理外部对话([{"role": "user", "content": "不应进入追踪的正文"}], "diagnostic-request")
        raw_trace = (self.store.traces_dir / "workbuddy.jsonl").read_text(encoding="utf-8")
        trace = json.loads(raw_trace.splitlines()[-1])
        self.assertEqual("failure", trace["status"])
        self.assertEqual(200, trace["upstream_http_status"])
        self.assertEqual("text/event-stream; charset=utf-8", trace["upstream_content_type"])
        self.assertEqual(128, trace["upstream_response_bytes"])
        self.assertNotIn("不应进入追踪的正文", raw_trace)
        self.assertNotIn("data: [DONE]", raw_trace)
        self.assertNotIn("测试密钥", raw_trace)

    def test_传输异常受控失败(self) -> None:
        def transport(*_):
            raise OSError("网络不可达")

        adapter = OpenAICompatibleAdapter("https://example.test", "测试密钥", "relay-model", transport=transport)
        with self.assertRaises(模型调用错误):
            adapter.complete([{"role": "user", "content": "你好"}])


if __name__ == "__main__":
    unittest.main()
