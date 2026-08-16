from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from adapters.model import 模型结果
from adapters.openai_compatible import OpenAICompatibleAdapter, 模型调用错误
from runtime.assets import 宪制加载器, 宪制资产错误
from runtime.context import 组装上下文
from runtime.core import 文龙运行时, 本轮失败
from runtime.session import 会话存储, 会话错误


class 假适配器:
    provider = "deepseek"
    model = "deepseek-v4-flash"

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
        self.assertNotIn("DEEPSEEK_API_KEY", trace)

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
        environment["DEEPSEEK_API_KEY"] = "测试密钥"
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

        adapter = OpenAICompatibleAdapter("https://example.test/", "测试密钥", "deepseek-v4-flash", transport=transport)
        result = adapter.complete([{"role": "user", "content": "你好"}])
        self.assertEqual("https://example.test/chat/completions", captured["url"])
        self.assertEqual("deepseek-v4-flash", captured["payload"]["model"])
        self.assertEqual("你好", captured["payload"]["messages"][0]["content"])
        self.assertEqual("模型回答", result.content)
        self.assertEqual("deepseek", result.provider)

    def test_无效响应受控失败(self) -> None:
        adapter = OpenAICompatibleAdapter("https://example.test", "测试密钥", "deepseek-v4-flash", transport=lambda *_: {})
        with self.assertRaises(模型调用错误):
            adapter.complete([{"role": "user", "content": "你好"}])

    def test_传输异常受控失败(self) -> None:
        def transport(*_):
            raise OSError("网络不可达")

        adapter = OpenAICompatibleAdapter("https://example.test", "测试密钥", "deepseek-v4-flash", transport=transport)
        with self.assertRaises(模型调用错误):
            adapter.complete([{"role": "user", "content": "你好"}])


if __name__ == "__main__":
    unittest.main()
