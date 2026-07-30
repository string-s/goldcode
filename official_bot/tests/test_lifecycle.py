"""本地模拟比赛服务，验证接入生命周期和数据落盘。

覆盖：分桌后不提前入房、正式赛同桌多局按新房间重新入房、自由赛结算后才申请下一场、
每一局的原始帧和结算数据分别落盘、AccessKey 不会出现在终端输出或运行日志里。
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
TEST_ACCESS_KEY = "test-only-access-key-must-not-leak"
GAMEPLAY_COMMANDS = {
    "goForward", "goBack", "turnLeft", "turnRight",
    "stop", "steerBack", "setAttackValue",
}
CAPTURE_FILES = [
    "metadata.json",
    "frames.jsonl",
    "commands.jsonl",
    "capture-summary.json",
    "replay.ccreplay.json",
    "settlement.json",
    "battle-data.json",
]

received = []
waiters = []
child_output = []


def now_ms():
    return int(time.time() * 1000)


def frame(**overrides):
    """真实协议下发的一帧：大屏与服务端都不再包含 attackValue。"""
    rabbit = {
        "id": 1001,
        "name": "测试参赛队",
        "active": True,
        "position": {"x": 720, "y": 410},
        "velocity": {"x": 0, "y": 0},
        "angle": 0,
        "speed": 0,
        "angularSpeed": 0,
        "width": 70,
        "height": 64,
        "moveState": 0,
        "dirState": 0,
        "rebounding": False,
        "reboundAngle": 0,
        "attacking": False,
        "invincible": False,
        "energy": 1000,
        "score": 10,
        "deathCount": 0,
        "survivalTime": 3,
    }
    rabbit.update(overrides)
    return rabbit


def receive(message):
    received.append(message)
    for waiter in list(waiters):
        predicate, future = waiter
        if not future.done() and predicate(message):
            waiters.remove(waiter)
            future.set_result(message)


async def wait_for_message(predicate, description, timeout=3.0, since=0):
    """等待一条满足条件的上行消息；since 用来只看某个时间点之后收到的消息。"""
    for message in received[since:]:
        if predicate(message):
            return message
    future = asyncio.get_running_loop().create_future()
    waiter = (predicate, future)
    waiters.append(waiter)
    try:
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError:
        if waiter in waiters:
            waiters.remove(waiter)
        raise AssertionError(f"Timed out waiting for {description}") from None


def assert_capture_files(match_dir, file_names):
    for file_name in file_names:
        assert (match_dir / file_name).exists(), f"缺少战斗文件 {match_dir}/{file_name}"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def drain(stream):
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            return
        child_output.append(chunk.decode("utf-8", "replace"))


async def main(runtime_dir):
    loop = asyncio.get_running_loop()
    connection_ready = loop.create_future()

    async def handler(connection):
        if not connection_ready.done():
            connection_ready.set_result(connection)
        try:
            async for raw in connection:
                receive(json.loads(raw))
        except ConnectionClosed:
            pass

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    child = await asyncio.create_subprocess_exec(
        sys.executable, str(PROJECT_DIR / "bot.py"),
        cwd=str(PROJECT_DIR),
        env={
            **os.environ,
            "CRAZY_CRASH_ACCESS_KEY": TEST_ACCESS_KEY,
            "CRAZY_CRASH_SERVER_URL": f"http://127.0.0.1:{port}",
            "CRAZY_CRASH_RUNTIME_DIR": str(runtime_dir),
            "COMMAND_INTERVAL_MS": "80",
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    drains = [
        asyncio.create_task(drain(child.stdout)),
        asyncio.create_task(drain(child.stderr)),
    ]

    client = await asyncio.wait_for(connection_ready, 10)

    async def send_to_bot(payload):
        await client.send(json.dumps(payload))

    connected = await wait_for_message(
        lambda message: message["commandType"] == "botConnect", "botConnect")
    assert connected["accessKey"] == TEST_ACCESS_KEY
    assert connected["botVersion"] == "participant-starter-v1"
    assert len(connected["strategyHash"]) == 64 and \
        all(character in "0123456789abcdef" for character in connected["strategyHash"])

    await send_to_bot({
        "commandType": "botConnected",
        "botId": 1001,
        "botName": "测试参赛队",
        "state": "LOBBY",
        "serverTime": now_ms(),
    })

    # ---- 正式赛：一桌三局，每一局都是独立的 matchId 和独立的房间 ----
    assignment = {
        "tournamentCode": "test-tournament",
        "tournamentName": "测试赛",
        "roundNo": 1,
        "pairingVersion": 1,
        "assignmentType": "MATCH",
        "tableNo": 1,
        "seatNo": 1,
        "roundPoints": 0,
        "gamesPerTable": 3,
        "gamesFinished": 0,
        "matchId": 77,
        "matchCode": "test-r01-t01-g01",
        "roomId": "test-r01-t01-g01",
        "gameNo": 1,
    }
    await send_to_bot({"commandType": "roundAssigned", **assignment})

    await asyncio.sleep(0.12)
    assert not any(message["commandType"] == "aiEnterRoom" for message in received), \
        "roundAssigned 后不得提前入房"

    await send_to_bot({"commandType": "roundStarted", **assignment})
    room_entry = await wait_for_message(
        lambda message: message["commandType"] == "aiEnterRoom", "aiEnterRoom")
    assert room_entry["roomId"] == "test-r01-t01-g01"
    assert "accessKey" not in room_entry

    await send_to_bot({"commandType": "roomEntered", "botId": 1001, "roomId": "test-r01-t01-g01"})
    await send_to_bot({
        "commandType": "startGame",
        "timeStamp": now_ms(),
        "data": {
            "rabbits": [frame()],
            "map": {"width": 1440, "height": 820, "borders": [], "blocks": []},
        },
    })
    await send_to_bot({
        "commandType": "refreshData",
        "timestamp": now_ms(),
        "data": {"rabbits": [frame()], "goldCarrot": {}},
    })
    gameplay_command = await wait_for_message(
        lambda message: message["commandType"] in GAMEPLAY_COMMANDS,
        "strategy gameplay command")

    # 服务端的 closeGame 只有 commandType，成绩由大屏单独上报。
    await send_to_bot({"commandType": "closeGame"})
    await send_to_bot({
        "commandType": "matchFinished",
        "matchId": 77,
        "matchCode": "test-r01-t01-g01",
        "roundNo": 1,
        "roomId": "test-r01-t01-g01",
        "gameNo": 1,
        "gamesPerTable": 3,
        "resultRank": 2,
        "advancementStatus": "PENDING",
        "nextState": "WAITING_NEXT_GAME",
        "result": {
            "seriesFinished": False,
            "ranking": [{
                "botId": 1001, "rank": 2, "score": 9, "deathCount": 0,
                "forestHeartCount": 1, "survivalTime": 180, "victoryTime": None, "points": 3,
            }],
        },
    })
    await wait_for_message(
        lambda message: message["commandType"] == "getMyBattleData", "getMyBattleData")
    await send_to_bot({
        "commandType": "myBattleData",
        "botId": 1001,
        "records": [{"matchCode": "test-r01-t01-g01", "rank": 2}],
        "tournaments": [],
    })

    await asyncio.sleep(0.12)
    assert not any(message["commandType"] == "readyForNextMatch" for message in received), \
        "正式赛结算后不得申请自由赛下一场"

    # 同一桌的第二局：房间号改变，BOT 必须重新入房。
    next_game = {
        **assignment,
        "matchId": 78,
        "matchCode": "test-r01-t01-g02",
        "roomId": "test-r01-t01-g02",
        "gameNo": 2,
        "gamesFinished": 1,
    }
    await send_to_bot({"commandType": "seriesGameStarted", **next_game})
    await send_to_bot({"commandType": "roundStarted", **next_game})
    second_room_entry = await wait_for_message(
        lambda message: (message["commandType"] == "aiEnterRoom"
                         and message["roomId"] == "test-r01-t01-g02"),
        "aiEnterRoom for the second game")
    assert second_room_entry["roomId"] == "test-r01-t01-g02"

    await send_to_bot({"commandType": "roomEntered", "botId": 1001, "roomId": "test-r01-t01-g02"})
    await send_to_bot({
        "commandType": "startGame",
        "timeStamp": now_ms(),
        "data": {
            "rabbits": [frame()],
            "map": {"width": 1440, "height": 820, "borders": [], "blocks": []},
        },
    })
    await send_to_bot({
        "commandType": "refreshData",
        "timestamp": now_ms(),
        "data": {"rabbits": [frame(energy=800)], "goldCarrot": {"x": 760, "y": 220}},
    })
    await send_to_bot({"commandType": "closeGame"})
    second_settlement_mark = len(received)
    await send_to_bot({
        "commandType": "matchFinished",
        "matchId": 78,
        "matchCode": "test-r01-t01-g02",
        "roundNo": 1,
        "roomId": "test-r01-t01-g02",
        "gameNo": 2,
        "gamesPerTable": 3,
        "resultRank": 1,
        "advancementStatus": "ADVANCED",
        "nextState": "WAITING_NEXT_ROUND",
        "result": {"seriesFinished": True, "ranking": [], "aggregateRanking": []},
    })
    await wait_for_message(
        lambda message: message["commandType"] == "getMyBattleData",
        "getMyBattleData for the second game", since=second_settlement_mark)
    await send_to_bot({
        "commandType": "myBattleData",
        "botId": 1001,
        "records": [{"matchCode": "test-r01-t01-g02", "rank": 1}],
        "tournaments": [],
    })
    await send_to_bot({
        "commandType": "roundFinished",
        "tournamentCode": "test-tournament",
        "roundNo": 1,
        "resultRank": 1,
        "advancementStatus": "ADVANCED",
        "nextState": "WAITING_NEXT_ROUND",
    })

    # ---- 自由赛：结算并保存数据后才申请下一场 ----
    practice_assignment = {
        "tournamentCode": "freeplay-test",
        "matchType": "PRACTICE",
        "sessionId": "freeplay-test",
        "batchId": "freeplay-test-b001",
        "roundNo": 1,
        "assignmentType": "MATCH",
        "tableNo": 1,
        "seatNo": 1,
        "matchId": 91,
        "matchCode": "freeplay-test-b001-t01",
        "roomId": "freeplay-test-b001-t01",
    }
    await send_to_bot({"commandType": "roundAssigned", **practice_assignment})
    await send_to_bot({"commandType": "roundStarted", **practice_assignment})
    await wait_for_message(
        lambda message: (message["commandType"] == "aiEnterRoom"
                         and message["roomId"] == "freeplay-test-b001-t01"),
        "aiEnterRoom for the practice table")
    await send_to_bot({
        "commandType": "roomEntered", "botId": 1001, "roomId": "freeplay-test-b001-t01"})
    await send_to_bot({
        "commandType": "startGame",
        "timeStamp": now_ms(),
        "data": {
            "rabbits": [frame()],
            "map": {"width": 1440, "height": 820, "borders": [], "blocks": []},
        },
    })
    await send_to_bot({
        "commandType": "refreshData",
        "timestamp": now_ms(),
        "data": {"rabbits": [frame()], "goldCarrot": None},
    })
    await send_to_bot({"commandType": "closeGame"})
    practice_settlement_mark = len(received)
    await send_to_bot({
        "commandType": "matchFinished",
        "matchId": 91,
        "matchCode": "freeplay-test-b001-t01",
        "matchType": "PRACTICE",
        "nextState": "TRAINING",
        "roomId": "freeplay-test-b001-t01",
        "result": {"ranking": [{"botId": 1001, "rank": 4, "score": 3}]},
    })
    await wait_for_message(
        lambda message: message["commandType"] == "getMyBattleData",
        "getMyBattleData for the practice match", since=practice_settlement_mark)
    await send_to_bot({
        "commandType": "myBattleData",
        "botId": 1001,
        "records": [{"matchCode": "freeplay-test-b001-t01", "rank": 4}],
        "tournaments": [],
    })
    await wait_for_message(
        lambda message: message["commandType"] == "readyForNextMatch", "readyForNextMatch")
    await send_to_bot({"commandType": "botReady", "botId": 1001, "state": "LOBBY_READY"})

    await asyncio.sleep(0.08)
    child.terminate()
    await asyncio.wait_for(child.wait(), 5)
    await asyncio.gather(*drains)
    server.close()
    await server.wait_closed()

    combined_output = "".join(child_output)
    assert TEST_ACCESS_KEY not in combined_output, "AK 不得出现在终端输出"
    event_log = (runtime_dir / "events.jsonl").read_text(encoding="utf-8")
    assert TEST_ACCESS_KEY not in event_log, "AK 不得写入运行日志"

    first_game_dir = runtime_dir / "matches" / "test-r01-t01-g01-77"
    second_game_dir = runtime_dir / "matches" / "test-r01-t01-g02-78"
    practice_dir = runtime_dir / "matches" / "freeplay-test-b001-t01-91"
    assert_capture_files(first_game_dir, CAPTURE_FILES)
    assert_capture_files(second_game_dir, CAPTURE_FILES)
    assert_capture_files(practice_dir, CAPTURE_FILES)

    first_metadata = read_json(first_game_dir / "metadata.json")
    second_metadata = read_json(second_game_dir / "metadata.json")
    assert first_metadata["gameNo"] == 1, "第一局的 gameNo 应为 1"
    assert second_metadata["gameNo"] == 2, "第二局的 gameNo 应为 2"
    assert second_metadata["gamesPerTable"] == 3, "应记录本桌总局数"

    first_settlement = read_json(first_game_dir / "settlement.json")
    assert first_settlement["matchId"] == 77, "每一局的结算必须落在自己的目录里"
    second_battle_data = read_json(second_game_dir / "battle-data.json")
    assert second_battle_data["records"][0]["matchCode"] == "test-r01-t01-g02"

    first_command_line = (first_game_dir / "commands.jsonl").read_text(
        encoding="utf-8").strip().split("\n")[0]
    assert json.loads(first_command_line)["command"] == gameplay_command

    replay = read_json(practice_dir / "replay.ccreplay.json")
    assert replay["format"] == "crazy-crash-replay"
    assert replay["version"] == 1
    assert replay["end"]["complete"] is True
    assert len(replay["frames"]) == 1
    assert replay["end"]["rankings"][0]["rank"] == 4
    serialized_replay = json.dumps(replay, ensure_ascii=False)
    assert "attackValue" not in serialized_replay, "可分享回放不得包含任何玩家的 attackValue"
    assert TEST_ACCESS_KEY not in serialized_replay, "可分享回放不得包含 AccessKey"

    print("lifecycle starter tests passed")


if __name__ == "__main__":
    directory = Path(tempfile.mkdtemp(prefix="crazy-crash-starter-"))
    try:
        asyncio.run(main(directory))
    except BaseException as error:
        print("".join(child_output), file=sys.stderr)
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
