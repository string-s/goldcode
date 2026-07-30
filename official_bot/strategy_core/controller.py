"""Translate a high-level intent into one legal persistent SDK command."""

from .collision import time_to_collision
from .geometry import distance, number, position
from .navigation import choose_navigation_command


def _command(command_type, data=None):
    value = {"commandType": command_type}
    if data is not None:
        value["data"] = str(data)
    return value


def choose_control(intent, me, foes, memory, config):
    if intent.stop:
        return _command("stop")
    me_position = position(me)
    if me_position is None:
        return _command("stop")

    raw_target = (intent.target_x, intent.target_y)
    target_distance = distance(me_position, raw_target)

    # Some local fixtures omit moveState.  Treat an omitted value as already
    # moving, while an explicit 0 still means the car must be started first.
    move_state = int(number(me.get("moveState"), 1.0))
    if move_state == 0:
        return _command("goForward")

    desired_attack = intent.desired_attack
    target_rabbit = next(
        (foe for foe in foes if str(foe.get("id")) == str(intent.target_id)), None)
    collision_steps = (
        time_to_collision(me, target_rabbit, config.collision_body_scale)
        if target_rabbit is not None else None
    )
    attack_change = (
        desired_attack is not None
        and abs(int(desired_attack) - memory.requested_attack) >= config.attack_reissue_delta
    )
    if attack_change and (
        target_distance <= config.attack_prepare_distance
        or (collision_steps is not None and collision_steps <= config.collision_horizon_steps)
        or intent.attack_urgent
    ):
        attack = max(0, min(1000, int(desired_attack)))
        memory.requested_attack = attack
        return _command("setAttackValue", attack)

    return choose_navigation_command(intent, me, foes, memory, config)
