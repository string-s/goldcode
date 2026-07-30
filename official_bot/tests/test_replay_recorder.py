"""验证回放文件的时间轴、原子写入和 attackValue 过滤。"""

import json
import shutil
import tempfile
from pathlib import Path

from tools.replay_recorder import (
    REPLAY_FILE_NAME,
    REPLAY_FORMAT,
    REPLAY_VERSION,
    ReplayRecorder,
)

directory = Path(tempfile.mkdtemp(prefix="crazy-crash-replay-"))

try:
    recorder = ReplayRecorder(
        directory=directory,
        meta={
            "matchCode": "test-r01-t01",
            "matchId": 77,
            "roomId": "test-r01-t01",
            "recorderBot": {"id": 1001, "name": "测试参赛队", "attackValue": 999},
        },
    )

    recorder.start({
        "commandType": "startGame",
        "timeStamp": 1000,
        "data": {
            "rabbits": [{"id": 1001, "position": {"x": 720, "y": 410}, "attackValue": 50}],
            "map": {"width": 1440, "height": 820},
        },
    }, 1100)
    recorder.frame({
        "commandType": "refreshData",
        "timestamp": 1100,
        "data": {
            "rabbits": [{
                "id": 1001,
                "position": {"x": 725, "y": 410},
                "energy": 950,
                "score": 10,
                "attackValue": 50,
            }],
            "remainingTime": 180,
            "elapsedSeconds": 0,
        },
    }, 1210)
    recorder.frame({
        "commandType": "refreshData",
        "timestamp": 1200,
        "data": {
            "rabbits": [{
                "id": 1001,
                "position": {"x": 730, "y": 410},
                "energy": 900,
                "score": 11,
                "nested": {"attackValue": 700},
            }],
            "remainingTime": 179,
            "elapsedSeconds": 1,
        },
    }, 1320)

    replay_path = Path(recorder.close(1500))
    assert replay_path.name == REPLAY_FILE_NAME
    assert not Path(str(replay_path) + ".tmp").exists(), "atomic temp file must be renamed"

    incomplete = json.loads(replay_path.read_text(encoding="utf-8"))
    assert incomplete["format"] == REPLAY_FORMAT
    assert incomplete["version"] == REPLAY_VERSION
    assert incomplete["end"]["complete"] is False
    assert [frame["atMs"] for frame in incomplete["frames"]] == [100, 200]
    assert "attackValue" not in json.dumps(incomplete)

    recorder.settle({
        "commandType": "matchFinished",
        "result": {"ranking": [{"botId": 1001, "rank": 1, "score": 11, "attackValue": 1000}]},
    })
    complete = json.loads(replay_path.read_text(encoding="utf-8"))
    assert complete["end"]["complete"] is True
    assert complete["end"]["rankings"][0]["rank"] == 1
    assert "attackValue" not in json.dumps(complete)

    print("replay recorder tests passed")
finally:
    shutil.rmtree(directory, ignore_errors=True)
