"""Behavioural tests for the Wolf strategy layers."""

import math

from strategy import choose_command, on_game_start, reset_strategy_for_test


def rabbit(identifier, x, y, **overrides):
    value = {
        "id": identifier,
        "name": f"bot-{identifier}",
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
        "reboundAngle": 0,
        "attacking": False,
        "invincible": False,
        "energy": 1000,
        "score": 10,
        "deathCount": 0,
        "survivalTime": 10,
    }
    value.update(overrides)
    return value


def state(me, *foes, elapsed=10, remaining=170, carrot=None):
    return {
        "rabbits": [me, *foes],
        "goldCarrot": carrot,
        "elapsedSeconds": elapsed,
        "remainingTime": remaining,
    }


def fresh(map_data=None):
    reset_strategy_for_test()
    on_game_start({
        "rabbits": [],
        "map": map_data or {"width": 1440, "height": 820, "blocks": [], "borders": []},
    }, {"matchCode": "test"})


# A stopped car must start moving before steering can affect its path.
fresh()
me = rabbit(1, 720, 410, moveState=0)
foe = rabbit(2, 900, 410)
assert choose_command(state(me, foe), 1) == {"commandType": "goForward"}

# The single-command scheduler spends the imminent-collision frame on attack setup.
fresh()
me = rabbit(1, 720, 410)
foe = rabbit(2, 820, 410)
command = choose_command(state(me, foe), 1)
assert command == {"commandType": "setAttackValue", "data": "85"}, command

# Opponent energy drops update its estimated attack, capped by its current energy.
fresh()
me = rabbit(1, 720, 410)
far_foe = rabbit(2, 1100, 410, energy=300)
choose_command(state(me, far_foe, elapsed=10), 1)
near_foe = rabbit(2, 820, 410, energy=100, rebounding=True)
command = choose_command(state(me, near_foe, elapsed=10.1), 1)
assert command == {"commandType": "setAttackValue", "data": "135"}, command

# An invincible opponent on the right causes an evasive turn instead of a charge.
fresh()
me = rabbit(1, 720, 410)
danger = rabbit(2, 900, 410, attacking=True, invincible=True)
command = choose_command(state(me, danger), 1)
assert command["commandType"] in {"turnLeft", "turnRight"}, command

# Our own invincibility avoids wasting a frame on attack setup.
fresh()
me = rabbit(1, 720, 410, attacking=True, invincible=True)
foe = rabbit(2, 820, 410)
command = choose_command(state(me, foe), 1)
assert command["commandType"] != "setAttackValue", command

# Near an edge, a rabbit facing outward must turn back toward the safe centre.
fresh()
me = rabbit(1, 80, 410, angle=math.pi)
foe = rabbit(2, 40, 410)
command = choose_command(state(me, foe), 1)
assert command["commandType"] in {"turnLeft", "turnRight"}, command

# The startGame map is cached and a blocking polygon forces a detour.
fresh({
    "width": 1440,
    "height": 820,
    "borders": [],
    "blocks": [[[
        {"x": 600, "y": 300},
        {"x": 800, "y": 300},
        {"x": 800, "y": 520},
        {"x": 600, "y": 520},
    ]]],
})
me = rabbit(1, 400, 410)
foe = rabbit(2, 1000, 410)
command = choose_command(state(me, foe), 1)
assert command["commandType"] in {"turnLeft", "turnRight"}, command

# A lifecycle reset restores the default attack request for the next game.
fresh()
me = rabbit(1, 720, 410)
foe = rabbit(2, 820, 410)
assert choose_command(state(me, foe), 1)["commandType"] == "setAttackValue"
fresh()
assert choose_command(state(me, foe), 1)["commandType"] == "setAttackValue"

print("wolf strategy tests passed")
