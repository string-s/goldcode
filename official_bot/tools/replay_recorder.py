"""把一局比赛录制成单文件回放（replay.ccreplay.json）。"""

import json
import math
import time
from pathlib import Path

REPLAY_FORMAT = "crazy-crash-replay"
REPLAY_VERSION = 1
REPLAY_FILE_NAME = "replay.ccreplay.json"


def _now_ms():
    return int(time.time() * 1000)


def _js_round(value):
    """等价于 JS 的 Math.round：.5 一律向上取整。"""
    return math.floor(value + 0.5)


def _number(value):
    """等价于 JS 的 Number(...)：无法解析或不是有限值时返回 None（相当于 NaN）。"""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def without_attack_value(value):
    """递归剔除 attackValue：可分享的回放不得包含任何玩家的攻击预设。"""
    if isinstance(value, list):
        return [without_attack_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: without_attack_value(item)
            for key, item in value.items()
            if key != "attackValue"
        }
    return value


def finite_timestamp(*values):
    for value in values:
        parsed = _number(value)
        if parsed is not None and parsed >= 0:
            return parsed
    return None


def rankings_from_settlement(message):
    message = message or {}
    if isinstance(message.get("rankings"), list):
        return message["rankings"]
    result = message.get("result")
    if isinstance(result, dict) and isinstance(result.get("ranking"), list):
        return result["ranking"]
    return []


class ReplayRecorder:
    def __init__(self, directory, meta=None):
        if not directory:
            raise ValueError("ReplayRecorder.directory is required")
        self.file_path = Path(directory) / REPLAY_FILE_NAME
        self.meta = without_attack_value(meta or {})
        self.start_state = {"rabbits": []}
        self.frames = []
        self.start_received_at = None
        self.start_source_at = None
        self.closed_at_ms = 0
        self.last_at_ms = 0
        self.complete = False
        self.rankings = []

    def start(self, message, received_at=None):
        message = message or {}
        self.start_received_at = finite_timestamp(received_at, _now_ms())
        self.start_source_at = finite_timestamp(
            message.get("timeStamp"),
            message.get("timestamp"),
            self.start_received_at,
        )
        self.start_state = without_attack_value(message.get("data") or {"rabbits": []})

    def frame(self, message, received_at=None):
        message = message or {}
        at_ms = self.relative_time(message, received_at)
        self.frames.append({
            "atMs": at_ms,
            "state": without_attack_value(message.get("data") or {"rabbits": []}),
        })
        self.last_at_ms = at_ms

    def close(self, received_at=None):
        self.closed_at_ms = max(self.last_at_ms, self.received_relative_time(received_at))
        self.complete = False
        self.rankings = []
        self.write()
        return str(self.file_path)

    def settle(self, message):
        self.complete = True
        self.rankings = without_attack_value(rankings_from_settlement(message))
        self.write()
        return str(self.file_path)

    def snapshot(self):
        return {
            "format": REPLAY_FORMAT,
            "version": REPLAY_VERSION,
            "meta": self.meta,
            "start": self.start_state,
            "frames": self.frames,
            "end": {
                "atMs": max(self.closed_at_ms, self.last_at_ms),
                "complete": self.complete,
                "rankings": self.rankings,
            },
        }

    def relative_time(self, message, received_at):
        source_at = finite_timestamp(message.get("timestamp"), message.get("timeStamp"))
        source_delta = (
            None if source_at is None or self.start_source_at is None
            else source_at - self.start_source_at
        )
        received_delta = self.received_relative_time(received_at)
        candidate = source_delta if source_delta is not None and source_delta >= 0 else received_delta
        return max(self.last_at_ms, _js_round(candidate))

    def received_relative_time(self, received_at):
        current = finite_timestamp(received_at, _now_ms())
        if self.start_received_at is None:
            return 0
        return max(0, _js_round(current - self.start_received_at))

    def write(self):
        temporary_path = self.file_path.with_name(self.file_path.name + ".tmp")
        temporary_path.write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.file_path)
