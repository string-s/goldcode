#!/usr/bin/env python3
"""疯狂 Geek 兔参赛 BOT 运行器（Python 版）。

负责 WebSocket 认证、心跳、中控分桌、轮空、开始轮次后入房、正式赛同桌多局的换房、
房间未开启重试、断线重连、原始帧采集、回放录制、结算落盘和自由赛再次就绪。

参赛者只需要修改 strategy.py。
"""

import asyncio
import hashlib
import json
import math
import os
import re
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import websockets
from websockets.exceptions import ConnectionClosed

import strategy as participant_strategy
from analysis import generate_match_report
from optimization import OptimizationManager
from tools.replay_recorder import ReplayRecorder

BASE_DIR = Path(__file__).resolve().parent


def env_ms(name, default, minimum):
    """与 JS 版一致：非法或 0 都退回默认值，再按下限收敛。"""
    try:
        value = int(float(os.environ.get(name, "")))
    except (TypeError, ValueError, OverflowError):
        value = 0
    return max(minimum, value or default)


SERVER_URL = os.environ.get("CRAZY_CRASH_SERVER_URL") or "https://pre-young-hackathon.alibaba-inc.com"
ACCESS_KEY = os.environ.get("CRAZY_CRASH_ACCESS_KEY")
BOT_VERSION = os.environ.get("BOT_VERSION") or "participant-starter-v1"
RETRY_MS = env_ms("ROOM_RETRY_MS", 2000, 500)
COMMAND_INTERVAL_MS = env_ms("COMMAND_INTERVAL_MS", 100, 80)
BATTLE_DATA_TIMEOUT_MS = env_ms("BATTLE_DATA_TIMEOUT_MS", 5000, 1000)
RECONNECT_DELAY_MS = 1500
RUNTIME_DIR = (
    Path(os.environ["CRAZY_CRASH_RUNTIME_DIR"]).resolve()
    if os.environ.get("CRAZY_CRASH_RUNTIME_DIR")
    else BASE_DIR / "runtime"
)

_server = urlsplit(SERVER_URL)
_default_ws_scheme = "wss" if _server.scheme == "https" else "ws"
WS_URL = os.environ.get("CRAZY_CRASH_WS_URL") or f"{_default_ws_scheme}://{_server.netloc}/ai"


def strategy_hash():
    """Hash the thin entry point and every Python strategy-core module."""
    digest = hashlib.sha256()
    paths = [BASE_DIR / "strategy.py"]
    core_dir = BASE_DIR / "strategy_core"
    if core_dir.exists():
        paths.extend(sorted(core_dir.glob("*.py")))
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


STRATEGY_IMPLEMENTED = participant_strategy.STRATEGY_IMPLEMENTED
choose_command = participant_strategy.choose_command
STRATEGY_HASH = strategy_hash()

SIMPLE_COMMANDS = {"goForward", "goBack", "stop", "steerBack"}
TURN_COMMANDS = {"turnLeft", "turnRight"}
# 服务端用这两个关闭码表示“本次身份不可用，不要继续重连”：
# 1007 认证或元数据非法，1008 同一 AK 重复在线或中控主动下线。
TERMINAL_CLOSE_CODES = {1007, 1008}


def now_ms():
    return int(time.time() * 1000)


def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_number(value):
    """等价于 JS 的 Number(...)：无法解析或不是有限值时返回 None（相当于 NaN）。"""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def number_to_text(value):
    """等价于 JS 的 String(Number)：整数不带小数点。"""
    if value == int(value):
        return str(int(value))
    return repr(float(value))


UNDEFINED = object()


def prop(container, key):
    """等价于 JS 的 `container && container.key`。

    键不存在时返回 UNDEFINED，log() 会像 JSON.stringify 丢弃 undefined 一样丢掉这个键；
    服务端显式下发的 null 仍然照常记录。
    """
    if container is None:
        return None
    return container.get(key, UNDEFINED)


def cancel_task(task):
    """取消定时任务；正在执行的那个任务不取消自己。"""
    if task is not None and task is not asyncio.current_task():
        task.cancel()


def status(message):
    print(f"\n[状态] {message}\n", flush=True)


def safe_segment(value):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(value or "unknown"))[:120]


def write_json(file_path, value):
    Path(file_path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_json_line(file_path, value):
    with open(file_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def normalize_command(command):
    if not isinstance(command, dict):
        raise ValueError("choose_command 必须返回动作对象")
    command_type = command.get("commandType")
    if command_type in SIMPLE_COMMANDS:
        return {"commandType": command_type}
    if command_type in TURN_COMMANDS:
        speed = to_number(command.get("data"))
        if speed is None or speed < 0.01 or speed > 0.1:
            raise ValueError(f"{command_type}.data 必须是 0.01～0.1")
        return {"commandType": command_type, "data": number_to_text(speed)}
    if command_type == "setAttackValue":
        attack_value = to_number(command.get("data"))
        if attack_value is None or attack_value < 0 or attack_value > 1000:
            raise ValueError("setAttackValue.data 必须是 0～1000")
        return {"commandType": command_type, "data": str(math.floor(attack_value + 0.5))}
    raise ValueError(f"不支持的 commandType: {command_type}")


def close_hint(code, reason):
    if "BOT_ALREADY_ONLINE" in reason:
        return "同一 AccessKey 已有另一个进程在线。关闭旧窗口后再重新启动，不要循环重连。"
    if "BOT_AUTH_FAILED" in reason:
        return "身份校验失败。先确认输入格式为 test:<纯数字工号>；格式正确说明当前环境未开启测试 AK，请改用正式 AccessKey。"
    if "BOT_METADATA_INVALID" in reason:
        return "botVersion 或 strategyHash 超出长度限制，请恢复开发包默认值后重试。"
    return f"服务端已终止本连接（{code}{' ' + reason if reason else ''}），不再自动重连。"


class Capture:
    """一局比赛的采集目录。"""

    def __init__(self, directory, match_code, match_id, room_id):
        self.directory = Path(directory)
        self.match_code = match_code
        self.match_id = match_id
        self.room_id = room_id
        self.started_at = None
        self.practice = False
        self.settlement = None
        self.battle_data = None
        self.strategy_finalized = False
        self.replay_recorder = None

    def append(self, file_name, value):
        append_json_line(self.directory / file_name, value)


class Bot:
    def __init__(self):
        self.socket = None
        self.stop_event = asyncio.Event()
        self.shutting_down = False
        self.playing = False
        self.bot_id = None
        self.bot_name = "参赛 BOT"
        self.pending_assignment = None
        self.entered_room_id = None
        self.last_command_at = 0
        self.last_strategy_error_at = 0
        self.frame_count = 0
        self.command_count = 0
        # 当前正在进行的这一局的采集目录。
        self.current_capture = None
        # 已经收到 matchFinished、还在等待 myBattleData 的那一局；三局两胜制下它可能
        # 和 current_capture 不是同一局，因此必须单独持有。
        self.settlement_capture = None
        self.heartbeat_task = None
        self.room_retry_task = None
        self.battle_data_task = None
        self.optimizer = OptimizationManager(BASE_DIR, RUNTIME_DIR)

    # ---- 基础设施 ----

    def log(self, event, **details):
        record = {
            "timestamp": iso_now(),
            "event": event,
            "botId": self.bot_id,
            "botName": self.bot_name,
        }
        record.update({key: value for key, value in details.items() if value is not UNDEFINED})
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        print(line, flush=True)
        with open(RUNTIME_DIR / "events.jsonl", "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    async def send(self, payload):
        socket = self.socket
        if socket is None:
            return False
        try:
            await socket.send(json.dumps(payload, ensure_ascii=False))
        except ConnectionClosed:
            return False
        return True

    def schedule(self, delay_ms, action):
        """等价于 setTimeout：延时执行一次，返回可取消的任务。"""
        async def runner():
            await asyncio.sleep(delay_ms / 1000)
            await action()
        return asyncio.create_task(runner())

    def start_heartbeat(self):
        self.stop_heartbeat()

        async def beat():
            while True:
                await asyncio.sleep(5)
                await self.send({"commandType": "botHeartbeat"})

        self.heartbeat_task = asyncio.create_task(beat())

    def stop_heartbeat(self):
        cancel_task(self.heartbeat_task)
        self.heartbeat_task = None

    # ---- 采集与落盘 ----

    def call_strategy_hook(self, name, *args):
        """Run an optional, synchronous lifecycle hook without risking the connection."""
        hook = getattr(participant_strategy, name, None)
        if hook is None:
            return
        try:
            hook(*args)
        except Exception as error:
            self.log("STRATEGY_HOOK_ERROR", hook=name, message=str(error))

    def create_capture(self, match_code, match_id, room_id):
        directory = RUNTIME_DIR / "matches" / safe_segment(f"{match_code}-{match_id or now_ms()}")
        directory.mkdir(parents=True, exist_ok=True)
        return Capture(directory, match_code, match_id, room_id)

    def start_capture(self, message):
        assignment = self.pending_assignment or {}
        match_code = assignment.get("matchCode") or self.entered_room_id or f"practice-{now_ms()}"
        capture = self.create_capture(match_code, assignment.get("matchId"), self.entered_room_id)
        capture.started_at = iso_now()
        capture.practice = assignment.get("matchType") == "PRACTICE"
        self.current_capture = capture
        metadata = {
            "matchCode": match_code,
            "matchId": capture.match_id,
            "roomId": self.entered_room_id,
            "botId": self.bot_id,
            "botName": self.bot_name,
            "startedAt": capture.started_at,
            "matchType": assignment.get("matchType"),
            "roundNo": assignment.get("roundNo"),
            # 正式赛一桌可能连打多局，gameNo/gamesPerTable 用来区分同一桌的第几局。
            "gameNo": assignment.get("gameNo"),
            "gamesPerTable": assignment.get("gamesPerTable"),
            "strategyHash": STRATEGY_HASH,
            "strategyImplemented": STRATEGY_IMPLEMENTED is True,
            "strategyRuntime": (
                participant_strategy.get_strategy_metadata()
                if hasattr(participant_strategy, "get_strategy_metadata") else {}
            ),
        }
        write_json(capture.directory / "metadata.json", metadata)
        capture.replay_recorder = ReplayRecorder(
            directory=capture.directory,
            meta={
                "matchCode": metadata["matchCode"],
                "matchId": metadata["matchId"],
                "roomId": metadata["roomId"],
                "matchType": metadata["matchType"],
                "roundNo": metadata["roundNo"],
                "gameNo": metadata["gameNo"],
                "gamesPerTable": metadata["gamesPerTable"],
                "recordedAt": capture.started_at,
                "recorderBot": {"id": self.bot_id, "name": self.bot_name},
                "strategyHash": STRATEGY_HASH,
            },
        )
        received_at = now_ms()
        capture.replay_recorder.start(message, received_at)
        capture.append("frames.jsonl", {
            "receivedAt": received_at,
            "sourceTimestamp": message.get("timeStamp") or message.get("timestamp"),
            "commandType": "startGame",
            "data": message.get("data") or {},
        })

    def finish_capture(self):
        capture = self.current_capture
        if capture is None:
            return
        received_at = now_ms()
        # 服务端下发的 closeGame 只有 commandType，没有成绩数据。
        capture.append("frames.jsonl", {"receivedAt": received_at, "commandType": "closeGame"})
        write_json(capture.directory / "capture-summary.json", {
            "matchCode": capture.match_code,
            "matchId": capture.match_id,
            "roomId": capture.room_id,
            "startedAt": capture.started_at,
            "closedAt": iso_now(),
            "frameCount": self.frame_count,
            "commandCount": self.command_count,
        })
        if capture.replay_recorder is not None:
            replay_path = capture.replay_recorder.close(received_at)
            self.log("REPLAY_SAVED", complete=False, matchCode=capture.match_code, path=replay_path)

    def save_settlement(self, message):
        capture = self.current_capture
        same_match = capture is not None and (
            message.get("matchId") is None
            or capture.match_id is None
            or str(capture.match_id) == str(message.get("matchId"))
        )
        if not same_match:
            capture = self.create_capture(
                message.get("matchCode") or "match",
                message.get("matchId"),
                message.get("roomId"),
            )
        capture.practice = (
            message.get("matchType") == "PRACTICE" or message.get("nextState") == "TRAINING")
        capture.settlement = message
        write_json(capture.directory / "settlement.json", message)
        if capture.replay_recorder is not None:
            replay_path = capture.replay_recorder.settle(message)
            self.log("REPLAY_SAVED", complete=True, matchCode=capture.match_code, path=replay_path)
        self.settlement_capture = capture

    def clear_battle_data_timer(self):
        cancel_task(self.battle_data_task)
        self.battle_data_task = None

    async def finish_settlement(self):
        """结算收尾：自由赛在数据落盘后才申请下一场，正式赛只需回到大厅等待。"""
        self.clear_battle_data_timer()
        capture = self.settlement_capture
        self.settlement_capture = None
        if capture is not None and not capture.strategy_finalized:
            capture.strategy_finalized = True
            self.call_strategy_hook("on_game_end", capture.settlement, capture.battle_data)
        if capture is not None:
            try:
                report_path = generate_match_report(capture.directory)
                self.log("MATCH_REPORT_SAVED", matchCode=capture.match_code,
                         path=str(report_path))
            except Exception as error:
                self.log("MATCH_REPORT_ERROR", matchCode=capture.match_code,
                         message=str(error))
                report_path = None
            if capture.practice and report_path is not None:
                try:
                    timeout = float(os.environ.get("WOLF_OPTIMIZER_TOTAL_TIMEOUT_SECONDS", "60"))
                    result = await asyncio.wait_for(
                        asyncio.to_thread(self.optimizer.process_report, report_path),
                        timeout=timeout,
                    )
                    self.log("OPTIMIZER_RESULT", matchCode=capture.match_code,
                             status=result.get("status"), changes=result.get("changes"))
                except Exception as error:
                    self.log("OPTIMIZER_ERROR", matchCode=capture.match_code,
                             message=str(error))
        if capture is not None and capture.practice:
            await self.send({"commandType": "readyForNextMatch"})

    async def request_battle_data(self):
        self.clear_battle_data_timer()
        if not await self.send({"commandType": "getMyBattleData", "limit": 100}):
            await self.finish_settlement()
            return

        async def on_timeout():
            # 服务端异常或消息丢失时不能卡住自由赛的下一场申请。
            capture = self.settlement_capture
            self.log("BATTLE_DATA_TIMEOUT",
                     matchCode=capture.match_code if capture is not None else None)
            await self.finish_settlement()

        self.battle_data_task = self.schedule(BATTLE_DATA_TIMEOUT_MS, on_timeout)

    async def handle_battle_data(self, message):
        capture = self.settlement_capture
        if capture is None:
            return
        capture.battle_data = message
        write_json(capture.directory / "battle-data.json", message)
        self.log("BATTLE_DATA_SAVED",
                 matchCode=capture.match_code, directory=str(capture.directory))
        await self.finish_settlement()

    # ---- 分桌与入房 ----

    def clear_room_retry(self):
        cancel_task(self.room_retry_task)
        self.room_retry_task = None

    def leave_room(self):
        self.playing = False
        self.entered_room_id = None
        self.clear_room_retry()

    def schedule_room_enter(self, delay_ms=RETRY_MS):
        self.clear_room_retry()
        assignment = self.pending_assignment
        if (not assignment or assignment.get("assignmentType") != "MATCH"
                or not assignment.get("roomId")):
            return

        async def enter_room():
            current = self.pending_assignment or {}
            room_id = current.get("roomId")
            if not room_id or self.entered_room_id == room_id:
                return
            self.log("ROOM_ENTER_ATTEMPT", roomId=room_id, matchCode=prop(current, "matchCode"))
            await self.send({"commandType": "aiEnterRoom", "roomId": room_id})

        self.room_retry_task = self.schedule(delay_ms, enter_room)

    def handle_round_start(self, message, event):
        """roundStarted 与 seriesGameStarted 都表示“可以进入这一桌当前这一局的房间了”。"""
        self.pending_assignment = message
        if message.get("roomId") and message.get("roomId") != self.entered_room_id:
            self.entered_room_id = None
        self.log(
            event,
            roundNo=prop(message, "roundNo"),
            matchCode=prop(message, "matchCode"),
            roomId=prop(message, "roomId"),
            gameNo=prop(message, "gameNo"),
            gamesPerTable=prop(message, "gamesPerTable"),
        )
        self.schedule_room_enter(0)

    # ---- 策略 ----

    def decide_command(self, game_state):
        try:
            return normalize_command(choose_command(game_state, self.bot_id))
        except Exception as error:  # 策略抛任何错都不能拖垮连接
            if now_ms() - self.last_strategy_error_at >= 1000:
                self.last_strategy_error_at = now_ms()
                self.log("STRATEGY_ERROR", message=str(error))
            return {"commandType": "stop"}

    # ---- 协议 ----

    async def handle_message(self, message):
        command_type = message.get("commandType")

        if command_type == "botConnected":
            self.bot_id = message.get("botId")
            self.bot_name = message.get("botName") or self.bot_name
            self.leave_room()
            self.pending_assignment = None
            self.start_heartbeat()
            self.log("BOT_CONNECTED", state=prop(message, "state"), wsUrl=WS_URL)
            status(f"{self.bot_name}（BOT {self.bot_id}）已上线，正在大厅等待中控台分桌。")
            if STRATEGY_IMPLEMENTED is not True:
                status("当前 strategy.py 仍是空白策略，进入比赛后只会原地停止。")

        elif command_type == "roundAssigned":
            self.pending_assignment = message
            self.entered_room_id = None
            self.clear_room_retry()
            if message.get("assignmentType") == "BYE":
                self.log("ROUND_BYE",
                         roundNo=prop(message, "roundNo"),
                         roundPoints=prop(message, "roundPoints"))
                status(f"第 {message.get('roundNo')} 轮轮空，无需进入房间。")
            else:
                self.log(
                    "ROUND_ASSIGNED",
                    roundNo=prop(message, "roundNo"),
                    matchCode=prop(message, "matchCode"),
                    roomId=prop(message, "roomId"),
                    tableNo=prop(message, "tableNo"),
                    seatNo=prop(message, "seatNo"),
                    gameNo=prop(message, "gameNo"),
                    gamesPerTable=prop(message, "gamesPerTable"),
                )
                status(f"已分配第 {message.get('roundNo')} 轮第 {message.get('tableNo')} 桌，等待主持人开赛。")

        elif command_type == "roundStarted":
            self.handle_round_start(message, "ROUND_STARTED")

        elif command_type == "seriesGameStarted":
            # 同一桌的下一局：房间号会变，必须重新入房。
            self.handle_round_start(message, "SERIES_GAME_STARTED")

        elif command_type == "roomEntered":
            self.entered_room_id = message.get("roomId")
            self.clear_room_retry()
            self.log("ROOM_ENTERED", roomId=prop(message, "roomId"))

        elif command_type == "startGame":
            self.playing = True
            self.frame_count = 0
            self.command_count = 0
            self.last_command_at = 0
            assignment = self.pending_assignment or {}
            self.call_strategy_hook("on_game_start", message.get("data") or {}, {
                "matchId": assignment.get("matchId"),
                "matchCode": assignment.get("matchCode"),
                "matchType": assignment.get("matchType"),
                "roundNo": assignment.get("roundNo"),
                "gameNo": assignment.get("gameNo"),
                "gamesPerTable": assignment.get("gamesPerTable"),
                "roomId": self.entered_room_id,
                "botId": self.bot_id,
                "runtimeDir": str(RUNTIME_DIR),
            })
            self.start_capture(message)
            self.log("GAME_STARTED",
                     roomId=self.entered_room_id,
                     roundNo=prop(self.pending_assignment, "roundNo"),
                     gameNo=prop(self.pending_assignment, "gameNo"))
            status("比赛开始，正在调用 strategy.py。")

        elif command_type == "refreshData":
            if not self.playing:
                return
            self.frame_count += 1
            received_at = now_ms()
            capture = self.current_capture
            if capture is not None:
                capture.append("frames.jsonl", {
                    "receivedAt": received_at,
                    "sourceTimestamp": message.get("timestamp") or message.get("timeStamp"),
                    "commandType": "refreshData",
                    "data": message.get("data") or {},
                })
                if capture.replay_recorder is not None:
                    capture.replay_recorder.frame(message, received_at)
            if now_ms() - self.last_command_at < COMMAND_INTERVAL_MS:
                return
            command = self.decide_command(message.get("data") or {})
            if await self.send(command):
                self.last_command_at = now_ms()
                self.command_count += 1
                if capture is not None:
                    capture.append("commands.jsonl", {
                        "sentAt": self.last_command_at,
                        "command": command,
                        "decision": (
                            participant_strategy.get_diagnostics()
                            if hasattr(participant_strategy, "get_diagnostics") else {}
                        ),
                    })

        elif command_type == "closeGame":
            # 服务端在收到 closeGame 之前已经关闭房间，此后任何战斗指令都会被拒绝。
            self.playing = False
            self.finish_capture()
            self.log("GAME_CLOSED", roomId=self.entered_room_id,
                     frameCount=self.frame_count, commandCount=self.command_count)

        elif command_type == "matchFinished":
            self.playing = False
            self.save_settlement(message)
            await self.request_battle_data()
            # 三局制的中间局结束后，服务端会紧接着下发下一局的 seriesGameStarted / roundStarted。
            series_continues = message.get("nextState") == "WAITING_NEXT_GAME"
            self.entered_room_id = None
            self.clear_room_retry()
            if not series_continues:
                self.pending_assignment = None
            self.log(
                "MATCH_FINISHED",
                matchCode=prop(message, "matchCode"),
                roundNo=prop(message, "roundNo"),
                gameNo=prop(message, "gameNo"),
                gamesPerTable=prop(message, "gamesPerTable"),
                resultRank=prop(message, "resultRank"),
                advancementStatus=prop(message, "advancementStatus"),
                nextState=prop(message, "nextState"),
            )
            status(
                f"本桌第 {message.get('gameNo')}/{message.get('gamesPerTable')} 局结束，等待同桌下一局开始。"
                if series_continues else "本场已结算，正在保存个人战斗数据。"
            )

        elif command_type == "myBattleData":
            await self.handle_battle_data(message)

        elif command_type == "roundFinished":
            self.pending_assignment = None
            self.clear_room_retry()
            self.log("ROUND_FINISHED",
                     roundNo=prop(message, "roundNo"),
                     resultRank=prop(message, "resultRank"),
                     advancementStatus=prop(message, "advancementStatus"),
                     nextState=prop(message, "nextState"))
            status(f"第 {message.get('roundNo')} 轮结果：{message.get('advancementStatus')}。")

        elif command_type == "roundRestarted":
            self.leave_room()
            self.pending_assignment = None
            self.log("ROUND_RESTARTED",
                     roundNo=prop(message, "roundNo"),
                     previousPairingVersion=prop(message, "previousPairingVersion"),
                     pairingVersion=prop(message, "pairingVersion"))
            status("主持人重开了本轮，等待新的分桌事件。")

        elif command_type == "botWaiting":
            self.leave_room()
            self.pending_assignment = None
            self.log("BOT_WAITING", reason=prop(message, "reason"))
            status("中控已让全部 BOT 回到大厅等待。")

        elif command_type == "botReady":
            self.log("BOT_READY", state=prop(message, "state"))
            status("战斗数据已保存，已重新进入自由赛等待队列。")

        elif command_type == "error":
            code = message.get("code")
            self.log("SERVER_ERROR", code=prop(message, "code"),
                     message=prop(message, "message"), roomId=prop(message, "roomId"))
            if code == "ROOM_NOT_OPEN":
                self.schedule_room_enter(to_number(message.get("retryAfterMs")) or RETRY_MS)
            elif code in ("BOT_NOT_ASSIGNED", "ROOM_ID_INVALID"):
                # 不是本队的房间，继续重试只会刷错误日志；保持在线等待中控重新分桌。
                self.clear_room_retry()
                self.pending_assignment = None
                status(f"服务端拒绝进入房间（{code}），保持在线等待中控重新分桌。")
            elif code == "BOT_ALREADY_ONLINE":
                status("同一 AccessKey 已有另一个进程在线，请关闭旧窗口后再启动。")

    # ---- 连接 ----

    async def connect_once(self):
        try:
            # ping_interval=None：与 Node 版一致，只靠 5 秒一次的 botHeartbeat 保活。
            socket = await websockets.connect(
                WS_URL, ping_interval=None, open_timeout=10, max_size=16 * 1024 * 1024)
        except Exception as error:
            self.log("SOCKET_ERROR", message=str(error))
            return
        self.socket = socket
        self.log("SOCKET_OPEN", wsUrl=WS_URL)
        await self.send({
            "commandType": "botConnect",
            "accessKey": ACCESS_KEY,
            "botVersion": BOT_VERSION,
            "strategyHash": STRATEGY_HASH,
        })
        try:
            async for raw in socket:
                try:
                    await self.handle_message(json.loads(raw))
                except Exception as error:
                    self.log("MESSAGE_INVALID", message=str(error))
        except ConnectionClosed:
            pass
        except Exception as error:
            self.log("SOCKET_ERROR", message=str(error))
        finally:
            await socket.close()
            self.on_socket_closed(socket)

    def on_socket_closed(self, socket):
        code = socket.close_code
        reason = socket.close_reason or ""
        self.socket = None
        self.leave_room()
        self.pending_assignment = None
        self.clear_battle_data_timer()
        self.stop_heartbeat()
        self.log("SOCKET_CLOSED", code=code, reason=reason)
        if self.shutting_down:
            return
        if code in TERMINAL_CLOSE_CODES:
            self.shutting_down = True
            self.stop_event.set()
            status(close_hint(code, reason))

    async def run(self):
        while not self.shutting_down:
            await self.connect_once()
            if self.shutting_down:
                break
            try:
                await asyncio.wait_for(self.stop_event.wait(), RECONNECT_DELAY_MS / 1000)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self):
        if self.shutting_down:
            return
        self.shutting_down = True
        self.stop_event.set()
        self.clear_room_retry()
        self.clear_battle_data_timer()
        self.stop_heartbeat()
        if self.playing:
            await self.send({"commandType": "stop"})
        socket = self.socket
        if socket is not None:
            await socket.close(1000, "Bot shutdown")


async def main():
    if not ACCESS_KEY:
        raise SystemExit(
            "缺少 CRAZY_CRASH_ACCESS_KEY。请双击启动脚本并输入 test:数字工号；"
            "环境关闭测试 AK 时再输入正式 AccessKey。")
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    bot = Bot()
    pending = []

    def request_shutdown():
        pending.append(asyncio.ensure_future(bot.shutdown()))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:
            pass  # Windows：Ctrl+C 由 KeyboardInterrupt 处理
    await bot.run()
    # 让关闭握手跑完，再退出进程。
    for task in pending:
        await task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
