"""验证策略返回的动作合法、边界场景不会乱动。"""

import json
import math
import re
from pathlib import Path

from strategy import STRATEGY_IMPLEMENTED, choose_command

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
SIMPLE_COMMANDS = {"goForward", "goBack", "stop", "steerBack"}
TURN_COMMANDS = {"turnLeft", "turnRight"}


def assert_legal_command(command):
    assert isinstance(command, dict), "策略必须返回动作对象"
    if command.get("commandType") in SIMPLE_COMMANDS:
        return
    if command.get("commandType") in TURN_COMMANDS:
        speed = float(command["data"])
        assert 0.01 <= speed <= 0.1, "转向速度必须在 0.01～0.1"
        return
    if command.get("commandType") == "setAttackValue":
        value = float(command["data"])
        assert 0 <= value <= 1000, "攻击预设必须在 0～1000"
        return
    raise AssertionError(f"非法动作：{command.get('commandType')}")


def collect_keys(value, keys=None):
    if keys is None:
        keys = set()
    if isinstance(value, list):
        for item in value:
            collect_keys(item, keys)
    elif isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            collect_keys(item, keys)
    return keys


assert isinstance(STRATEGY_IMPLEMENTED, bool), "STRATEGY_IMPLEMENTED 必须是 bool"
assert STRATEGY_IMPLEMENTED is True, "当前分支应附带可以实际移动和转向的基准策略"

assert choose_command({"rabbits": []}, 1001) == {"commandType": "stop"}, "找不到本人时必须停止"

# 样例帧必须和真实协议一致：服务端与大屏都不再下发 attackValue。
sample_frame = json.loads(
    (BASE_DIR / "fixtures" / "sample-refresh-data.json").read_text(encoding="utf-8"))
assert "attackValue" not in collect_keys(sample_frame), \
    "tests/fixtures/sample-refresh-data.json 不能再出现 attackValue"
assert_legal_command(choose_command(sample_frame, sample_frame["rabbits"][0]["id"]))

sample_state = {
    "rabbits": [
        {
            "id": 1001,
            "active": True,
            "position": {"x": 720, "y": 410},
            "angle": 0,
            "energy": 1000,
            "score": 10,
            "deathCount": 0,
            "survivalTime": 12,
        },
        {
            "id": 1002,
            "active": True,
            "position": {"x": 900, "y": 410},
            "angle": math.pi,
            "energy": 1000,
            "score": 10,
            "deathCount": 0,
            "survivalTime": 12,
        },
    ],
    "goldCarrot": {"x": 760, "y": 200},
}

sample_command = choose_command(sample_state, 1001)
assert_legal_command(sample_command)
assert sample_command["commandType"] in TURN_COMMANDS, "面向场地右侧、金萝卜在上方时应主动转向目标"

# 本人已淘汰时必须停止：帧里仍会带上这只兔子，但 active=False。
eliminated = dict(sample_state["rabbits"][0], active=False, energy=0, score=0)
assert choose_command({"rabbits": [eliminated], "goldCarrot": None}, 1001) == {"commandType": "stop"}

# 本地 sample 服务会给兔子 ID 增加 ai: 前缀，策略仍应识别本人。
prefixed = dict(sample_state["rabbits"][0], id="ai:1001")
assert_legal_command(choose_command({"rabbits": [prefixed], "goldCarrot": None}, 1001))

source = (PROJECT_DIR / "strategy.py").read_text(encoding="utf-8")
# 只禁止“从帧里读对手/自己的攻击预设”，不禁止把自己的预设存进本地状态。
frame_property_access = re.search(
    r"""\[\s*["']attackValue["']\s*\]|\.get\(\s*["']attackValue["']|\.attackValue\b""",
    source.replace("setAttackValue", ""))
assert frame_property_access is None, \
    f"协议帧不再下发 attackValue，不能读取 {frame_property_access and frame_property_access.group(0)}"

if STRATEGY_IMPLEMENTED is False:
    assert sample_command == {"commandType": "stop"}, "空白模板必须保持原地停止，参赛者需要自行实现动作"
    assert "TODO（参赛者实现）" in source, "空白模板必须保留明确的实现入口"
else:
    assert "STRATEGY_IMPLEMENTED = False" not in source, \
        "策略已实现时必须把 STRATEGY_IMPLEMENTED 改为 True"

print(f"strategy tests passed ({'implemented' if STRATEGY_IMPLEMENTED else 'starter'})")
