"""Translate a high-level intent into one legal persistent SDK command."""

import math

from .geometry import detour_target, distance, normalize_angle, number, position


def _command(command_type, data=None):
    value = {"commandType": command_type}
    if data is not None:
        value["data"] = str(data)
    return value


def choose_control(intent, me, memory, config):
    if intent.stop:
        return _command("stop")
    me_position = position(me)
    if me_position is None:
        return _command("stop")

    raw_target = (intent.target_x, intent.target_y)
    target = detour_target(
        me_position,
        raw_target,
        memory.obstacle_polygons,
        config.arena_width,
        config.arena_height,
        config.obstacle_margin,
    )
    target_distance = distance(me_position, raw_target)

    # Some local fixtures omit moveState.  Treat an omitted value as already
    # moving, while an explicit 0 still means the car must be started first.
    move_state = int(number(me.get("moveState"), 1.0))
    if move_state == 0:
        return _command("goForward")

    desired_attack = intent.desired_attack
    attack_change = (
        desired_attack is not None
        and abs(int(desired_attack) - memory.requested_attack) >= config.attack_reissue_delta
    )
    if attack_change and (
        target_distance <= config.attack_prepare_distance or intent.attack_urgent
    ):
        attack = max(0, min(1000, int(desired_attack)))
        memory.requested_attack = attack
        return _command("setAttackValue", attack)

    desired_angle = math.atan2(target[1] - me_position[1], target[0] - me_position[0])
    current_angle = number(me.get("angle"))
    delta = normalize_angle(desired_angle - current_angle)
    dir_state = int(number(me.get("dirState")))

    if abs(delta) > config.turn_tolerance:
        speed = config.hard_turn_speed if abs(delta) > config.hard_turn_tolerance else config.turn_speed
        return _command("turnRight" if delta > 0 else "turnLeft", f"{speed:.3f}")

    if dir_state != 0:
        return _command("steerBack")
    return _command("goForward")
