"""Persistent opponent profiles and multi-game posture tests."""

import tempfile
from pathlib import Path

from storage import ProfileStore
from strategy_core.runtime import WolfStrategy


def rabbit(identifier, **overrides):
    value = {
        "id": identifier,
        "name": f"team-{identifier}",
        "active": True,
        "position": {"x": 720 if identifier == 1 else 900, "y": 410},
        "velocity": {"x": 0, "y": 0},
        "angle": 0,
        "moveState": 1,
        "dirState": 0,
        "width": 70,
        "height": 64,
        "energy": 1000,
        "score": 10,
        "survivalTime": 1,
    }
    value.update(overrides)
    return value


directory = Path(tempfile.mkdtemp(prefix="wolf-profiles-"))
database = directory / "profiles.sqlite3"
store = ProfileStore(database)
store.save_many([{
    "opponent_id": "2",
    "name": "known-team",
    "games": 4,
    "attack_ema": 180,
    "attack_peak": 300,
    "attack_samples": 6,
    "contacts": 8,
}])
loaded = store.load_many(["2"])
assert loaded["2"]["games"] == 4
assert loaded["2"]["attack_ema"] == 180
assert store.count() == 1

strategy = WolfStrategy(profile_db_path=database, profile_mode="read-write")
start = {
    "map": {"blocks": [], "borders": []},
    "rabbits": [rabbit(1), rabbit(2)],
}
context = {
    "botId": 1,
    "matchType": "PRACTICE",
    "gameNo": 1,
    "gamesPerTable": 3,
    "runtimeDir": str(directory),
}
strategy.on_game_start(start, context)
strategy.choose_command({
    "rabbits": [rabbit(1), rabbit(2, energy=800)],
    "elapsedSeconds": 1,
    "remainingTime": 179,
}, 1)
assert strategy.memory.estimate_attack(rabbit(2)) == 180
strategy.on_game_end({
    "result": {"ranking": [{"botId": 1, "rank": 1, "points": 4}]},
}, None)
assert store.load_many(["2"])["2"]["games"] == 5

context["gameNo"] = 2
strategy.on_game_start(start, context)
strategy.choose_command({
    "rabbits": [rabbit(1), rabbit(2)],
    "elapsedSeconds": 1,
    "remainingTime": 179,
}, 1)
diagnostics = strategy.diagnostics()
assert diagnostics["series"]["pointsBeforeGame"] == 4
assert diagnostics["series"]["posture"] == "PROTECT_SERIES"

print("profile and series tests passed")
