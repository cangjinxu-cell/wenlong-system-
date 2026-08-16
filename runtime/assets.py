from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


class 宪制资产错误(RuntimeError):
    """正式宪制文件不可用时，运行时必须拒绝启动。"""


@dataclass(frozen=True)
class 宪制资产:
    kernel: str
    memory_constitution: str
    kernel_sha256: str
    memory_constitution_sha256: str


class 宪制加载器:
    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = repository_root or Path(__file__).resolve().parent.parent

    def 加载(self) -> 宪制资产:
        kernel = self._读取("wenlong/kernel.md", "Kernel")
        memory = self._读取("wenlong/memory-constitution.md", "Memory Constitution")
        return 宪制资产(
            kernel=kernel,
            memory_constitution=memory,
            kernel_sha256=sha256(kernel.encode("utf-8")).hexdigest(),
            memory_constitution_sha256=sha256(memory.encode("utf-8")).hexdigest(),
        )

    def _读取(self, relative_path: str, display_name: str) -> str:
        path = self.repository_root / relative_path
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as error:
            raise 宪制资产错误(f"无法读取正式 {display_name} 文件：{path}") from error
        if not content.strip():
            raise 宪制资产错误(f"正式 {display_name} 文件为空：{path}")
        return content
