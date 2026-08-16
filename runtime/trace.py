from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _时间() -> str:
    return datetime.now(timezone.utc).isoformat()


class 追踪记录器:
    def __init__(self, traces_dir: Path) -> None:
        self.traces_dir = traces_dir

    def 记录(self, session_id: str, **fields: object) -> None:
        event = {"trace_id": str(uuid.uuid4()), "session_id": session_id, **fields}
        path = self.traces_dir / f"{session_id}.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def 开始时间() -> str:
        return _时间()

    @staticmethod
    def 完成时间() -> str:
        return _时间()
