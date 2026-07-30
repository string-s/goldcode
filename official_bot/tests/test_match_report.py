"""Verify telemetry aggregation and automatic match reports."""

import json
import tempfile
from pathlib import Path

from analysis.match_report import generate_match_report

directory = Path(tempfile.mkdtemp(prefix="wolf-report-"))
(directory / "metadata.json").write_text(json.dumps({
    "matchCode": "practice-1",
    "matchId": 1,
    "matchType": "PRACTICE",
    "botId": 1001,
    "strategyHash": "abc",
}), encoding="utf-8")
(directory / "settlement.json").write_text(json.dumps({
    "result": {"ranking": [{
        "botId": 1001, "rank": 2, "score": 12, "points": 3,
        "deathCount": 0, "forestHeartCount": 1,
    }]},
}), encoding="utf-8")
(directory / "commands.jsonl").write_text("\n".join([
    json.dumps({
        "command": {"commandType": "turnLeft", "data": "0.05"},
        "decision": {"mode": "RACE", "reason": "heart_race_winnable",
                     "targetId": "2", "idleSeconds": 10},
    }),
    json.dumps({
        "command": {"commandType": "turnRight", "data": "0.05"},
        "decision": {"mode": "FARM", "reason": "best_target_score",
                     "targetId": "2", "idleSeconds": 11},
    }),
    json.dumps({
        "command": {"commandType": "setAttackValue", "data": "120"},
        "decision": {"mode": "FARM", "reason": "best_target_score",
                     "targetId": "2", "idleSeconds": 12},
    }),
]) + "\n", encoding="utf-8")
(directory / "frames.jsonl").write_text("\n".join([
    json.dumps({"commandType": "refreshData", "data": {
        "elapsedSeconds": 1,
        "rabbits": [{"id": 1001, "energy": 1000, "score": 10,
                     "rebounding": False, "invincible": False}],
    }}),
    json.dumps({"commandType": "refreshData", "data": {
        "elapsedSeconds": 2,
        "rabbits": [{"id": 1001, "energy": 880, "score": 11,
                     "rebounding": True, "invincible": False}],
    }}),
]) + "\n", encoding="utf-8")

path = generate_match_report(directory)
report = json.loads(path.read_text(encoding="utf-8"))
assert report["result"]["rank"] == 2
assert report["decisions"]["modes"] == {"RACE": 1, "FARM": 2}
assert report["decisions"]["turnDirectionSwitches"] == 1
assert report["energy"]["averageAttackSet"] == 120
assert report["events"]["estimatedContacts"] == 1
assert (directory / "match-report.md").exists()

print("match report tests passed")
