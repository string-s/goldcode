"""Collision prediction, cooldown and local-navigation tests."""

from strategy import (
    choose_command,
    get_diagnostics,
    on_game_start,
    reset_strategy_for_test,
)
from strategy_core.collision import time_to_collision


def rabbit(identifier, x, y, **overrides):
    value = {
        "id": identifier,
        "active": True,
        "position": {"x": x, "y": y},
        "velocity": {"x": 0, "y": 0},
        "angle": 0,
        "speed": 5,
        "angularSpeed": 0,
        "width": 70,
        "height": 64,
        "moveState": 1,
        "dirState": 0,
        "rebounding": False,
        "attacking": False,
        "invincible": False,
        "energy": 1000,
        "score": 10,
        "survivalTime": 10,
    }
    value.update(overrides)
    return value


def state(me, *foes, elapsed=10):
    return {
        "rabbits": [me, *foes],
        "goldCarrot": None,
        "elapsedSeconds": elapsed,
        "remainingTime": 180 - elapsed,
    }


left = rabbit(1, 100, 100, velocity={"x": 5, "y": 0})
right = rabbit(2, 300, 100, velocity={"x": -5, "y": 0})
ttc = time_to_collision(left, right)
assert ttc is not None and 10 < ttc < 20, ttc
right["velocity"] = {"x": 5, "y": 0}
assert time_to_collision(left, right) is None

# Both blocks and borders are cached for the local trajectory planner.
reset_strategy_for_test()
on_game_start({
    "map": {
        "width": 1440,
        "height": 820,
        "blocks": [[[
            {"x": 600, "y": 300}, {"x": 800, "y": 300},
            {"x": 800, "y": 520}, {"x": 600, "y": 520},
        ]]],
        "borders": [[[
            {"x": 0, "y": 0}, {"x": 30, "y": 0},
            {"x": 30, "y": 820}, {"x": 0, "y": 820},
        ]]],
    },
    "rabbits": [],
}, {})
me = rabbit(1, 400, 410)
target = rabbit(2, 1000, 410)
command = choose_command(state(me, target), 1)
assert command["commandType"] in {"turnLeft", "turnRight"}, command
assert get_diagnostics()["obstacleCount"] == 2

# A detected collision triggers separation, then keeps the same pair on cooldown.
reset_strategy_for_test()
on_game_start({"map": {"blocks": [], "borders": []}, "rabbits": []}, {})
me = rabbit(1, 720, 410)
close = rabbit(2, 800, 410, energy=100)
other = rabbit(3, 1050, 410, energy=100)
choose_command(state(me, close, other, elapsed=10), 1)

me_hit = rabbit(1, 720, 410, energy=900, rebounding=True)
choose_command(state(me_hit, close, other, elapsed=10.1), 1)
assert get_diagnostics()["mode"] == "DISENGAGE"

me_after = rabbit(1, 720, 410, energy=900, rebounding=False)
choose_command(state(me_after, close, other, elapsed=11.3), 1)
assert get_diagnostics()["targetId"] == "3", get_diagnostics()

print("collision and navigation tests passed")
