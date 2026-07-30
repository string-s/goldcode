#!/usr/bin/env python3
"""本地检查：语法检查 + 全部测试。等价于 Node 版的 npm run check。"""

import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SOURCES = [
    "bot.py",
    "strategy.py",
    "tools/replay_recorder.py",
    "tools/replay_server.py",
    "tools/__init__.py",
    "analysis/__init__.py",
    "analysis/match_report.py",
    "storage/__init__.py",
    "storage/profile_store.py",
    "check.py",
    "tests/__init__.py",
    "tests/test_strategy.py",
    "tests/test_wolf_strategy.py",
    "tests/test_replay_recorder.py",
    "tests/test_replay_server.py",
    "tests/test_lifecycle.py",
    "tests/test_match_report.py",
    "tests/test_collision_navigation.py",
    "tests/test_profiles_series.py",
]
SOURCES.extend(
    str(path.relative_to(BASE_DIR))
    for path in sorted((BASE_DIR / "strategy_core").glob("*.py"))
)
TESTS = [
    "tests/test_strategy.py",
    "tests/test_wolf_strategy.py",
    "tests/test_replay_recorder.py",
    "tests/test_replay_server.py",
    "tests/test_lifecycle.py",
    "tests/test_match_report.py",
    "tests/test_collision_navigation.py",
    "tests/test_profiles_series.py",
]


def main():
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("缺少 websockets 依赖，请先运行：python3 -m pip install -r requirements.txt",
              file=sys.stderr)
        return 1

    for name in SOURCES:
        path = BASE_DIR / name
        try:
            compile(path.read_text(encoding="utf-8"), name, "exec")
        except SyntaxError as error:
            print(f"{name} 语法错误：{error}", file=sys.stderr)
            return 1
    print(f"syntax check passed ({len(SOURCES)} files)", flush=True)

    for name in TESTS:
        env = dict(os.environ)
        current_python_path = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(BASE_DIR)
            if not current_python_path
            else str(BASE_DIR) + os.pathsep + current_python_path
        )
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / name)],
            cwd=str(BASE_DIR),
            env=env,
            check=False,
        )
        if result.returncode != 0:
            print(f"\n{name} 失败", file=sys.stderr)
            return result.returncode

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
