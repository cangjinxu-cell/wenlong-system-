from __future__ import annotations

import argparse
import sys

from runtime.assets import 宪制资产错误
from runtime.config import 配置错误, 运行目录
from runtime.core import 文龙运行时, 本轮失败
from runtime.session import 会话, 会话存储, 会话错误
from runtime.server import Bridge配置错误, 启动服务, 读取桥接密钥


def _交互(runtime: 文龙运行时, session: 会话) -> int:
    print(f"会话已就绪：{session.session_id}")
    while True:
        try:
            user_input = input("主公 > ")
        except EOFError:
            print("会话已结束。")
            return 0
        if not user_input.strip():
            continue
        try:
            result = runtime.处理输入(session, user_input)
        except 本轮失败 as error:
            print(f"本轮未完成：{error}", file=sys.stderr)
            continue
        session = result.session
        print(f"文龙 > {result.content}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m wenlong", description="文龙运行时 V0.1")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("new", help="创建新会话并进入交互")
    resume = commands.add_parser("resume", help="恢复会话并进入交互")
    resume.add_argument("session_id")
    commands.add_parser("sessions", help="列出现有会话")
    serve = commands.add_parser("serve", help="启动 WorkBuddy 本机 Bridge")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "sessions":
            sessions = 会话存储(运行目录()).列表()
            for session in sessions:
                print(f"{session.session_id}\t{session.created_at}\t{session.updated_at}")
            return 0
        runtime = 文龙运行时.从环境启动()
        if args.command == "serve":
            启动服务(runtime, 读取桥接密钥(), args.port)
            return 0
        session = runtime.新建会话() if args.command == "new" else runtime.恢复会话(args.session_id)
        return _交互(runtime, session)
    except (宪制资产错误, 配置错误, 会话错误, Bridge配置错误) as error:
        print(f"文龙无法启动：{error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n会话已中断。")
        return 130
