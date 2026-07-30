"""High-level seven-mode Wolf policy.

This module decides *what* to do.  It deliberately does not emit SDK commands;
the controller owns the one-command-per-frame constraint.
"""

import math

from .geometry import clamp_point, distance, number, position, valid_carrot
from .memory import is_invincible, rabbit_id
from .models import Intent


def _energy(rabbit):
    return max(0.0, number(rabbit.get("energy")))


def _score(rabbit):
    return int(number(rabbit.get("score")))


def _velocity(rabbit):
    velocity = rabbit.get("velocity") if isinstance(rabbit, dict) else None
    if not isinstance(velocity, dict):
        return 0.0, 0.0
    return number(velocity.get("x")), number(velocity.get("y"))


def _predicted_position(rabbit, seconds):
    current = position(rabbit)
    if current is None:
        return None
    vx, vy = _velocity(rabbit)
    return current[0] + vx * seconds * 10.0, current[1] + vy * seconds * 10.0


def _nearest(me_position, foes):
    return min(foes, key=lambda foe: distance(me_position, position(foe)))


def _rank(me, foes):
    scores = sorted([_score(me)] + [_score(foe) for foe in foes], reverse=True)
    return scores.index(_score(me)) + 1


def _advancement_gap(me, foes):
    """Score cushion over the current third-place cutoff."""
    scores = sorted([_score(me)] + [_score(foe) for foe in foes], reverse=True)
    if len(scores) < 3:
        return _score(me) - min(scores)
    return _score(me) - scores[2]


def _flee_point(me_position, threats, config):
    if not threats:
        return config.arena_width / 2, config.arena_height / 2
    fx = fy = 0.0
    for threat in threats:
        threat_position = position(threat)
        if threat_position is None:
            continue
        dx = me_position[0] - threat_position[0]
        dy = me_position[1] - threat_position[1]
        scale = 1.0 / max(1.0, dx * dx + dy * dy)
        fx += dx * scale
        fy += dy * scale
    fx += (config.arena_width / 2 - me_position[0]) * config.center_pull / 1000.0
    fy += (config.arena_height / 2 - me_position[1]) * config.center_pull / 1000.0
    magnitude = math.hypot(fx, fy)
    if magnitude < 1e-9:
        return config.arena_width / 2, config.arena_height / 2
    target = (me_position[0] + fx / magnitude * 320.0,
              me_position[1] + fy / magnitude * 320.0)
    return clamp_point(target, config.arena_width, config.arena_height, config.edge_margin)


def _farm_target(me, foes, memory, config, elapsed):
    me_position = position(me)
    held = next((foe for foe in foes if rabbit_id(foe) == memory.target_id), None)
    if (
        held is not None
        and elapsed - memory.target_selected_at < config.target_hold_seconds
        and not memory.on_collision_cooldown(
            rabbit_id(held), elapsed, config.collision_cooldown_seconds)
    ):
        return held

    def target_cost(foe):
        foe_position = position(foe)
        cost = distance(me_position, foe_position)
        if is_invincible(foe):
            cost += 10000
        cost += _energy(foe) * 0.12
        cost -= _score(foe) * 6.0
        if _score(foe) <= config.kill_score:
            cost -= 180.0
        return cost

    available = [
        foe for foe in foes
        if not memory.on_collision_cooldown(
            rabbit_id(foe), elapsed, config.collision_cooldown_seconds)
    ]
    chosen = min(available or foes, key=target_cost)
    memory.target_id = rabbit_id(chosen)
    memory.target_selected_at = elapsed
    return chosen


def _attack_for(target, me, memory, config, tail):
    my_energy = _energy(me)
    if tail:
        return int(my_energy)
    estimated = memory.estimate_attack(target, config.default_attack)
    opponent_cap = _energy(target)
    expected = min(estimated, opponent_cap)
    if memory.series_posture == "MUST_SCORE":
        reserve = config.series_aggressive_reserve
    else:
        reserve = 0 if _score(me) <= config.danger_score else config.reserve_energy
    affordable = max(0, my_energy - reserve)
    desired = min(affordable, expected + config.attack_margin)
    return int(max(0, desired))


def choose_intent(game_state, me, foes, memory, config):
    elapsed = number(game_state.get("elapsedSeconds"), number(me.get("survivalTime"), 0.0))
    remaining = number(game_state.get("remainingTime"), max(0.0, 180.0 - elapsed))
    me_position = position(me)
    center = (config.arena_width / 2, config.arena_height / 2)

    near_edge = (
        me_position[0] < config.edge_margin
        or me_position[0] > config.arena_width - config.edge_margin
        or me_position[1] < config.edge_margin
        or me_position[1] > config.arena_height - config.edge_margin
    )
    if near_edge:
        memory.mode = "SAFE"
        return Intent("SAFE", center[0], center[1], reason="near_edge")

    invincible_foes = [
        foe for foe in foes
        if is_invincible(foe) and distance(me_position, position(foe)) <= config.invincible_threat_distance
    ]
    if invincible_foes and not is_invincible(me):
        memory.mode = "EVADE"
        target = _flee_point(me_position, invincible_foes, config)
        return Intent("EVADE", target[0], target[1], reason="invincible_threat")

    if is_invincible(me):
        target = _nearest(me_position, [foe for foe in foes if not is_invincible(foe)] or foes)
        predicted = _predicted_position(target, config.prediction_seconds) or position(target)
        memory.mode = "RAMPAGE"
        return Intent(
            "RAMPAGE", predicted[0], predicted[1], rabbit_id(target),
            reason="self_invincible",
        )

    recent_target = None
    for foe in foes:
        age = memory.contact_age(rabbit_id(foe), elapsed)
        if (
            rabbit_id(foe) == memory.last_contact_target_id
            and age is not None
            and age < config.disengage_seconds
        ):
            recent_target = foe
            break
    if recent_target is not None:
        target = _flee_point(me_position, [recent_target], config)
        memory.mode = "DISENGAGE"
        return Intent(
            "DISENGAGE", target[0], target[1], reason="collision_cooldown_separation")

    carrot = valid_carrot(game_state.get("goldCarrot"))
    if carrot is not None:
        my_distance = distance(me_position, carrot)
        foe_distance = min((distance(position(foe), carrot) for foe in foes), default=1e9)
        if my_distance <= foe_distance * config.heart_race_ratio + config.heart_race_slack:
            memory.mode = "RACE"
            return Intent("RACE", carrot[0], carrot[1], reason="heart_race_winnable")

    idle_seconds = max(0.0, elapsed - memory.last_contact_at)
    if idle_seconds >= config.idle_soft_seconds:
        target = min(foes, key=lambda foe: (_energy(foe), distance(me_position, position(foe))))
        predicted = _predicted_position(target, config.prediction_seconds) or position(target)
        desired = _attack_for(target, me, memory, config, tail=False)
        memory.mode = "CLOCK_RESET"
        return Intent(
            "CLOCK_RESET", predicted[0], predicted[1], rabbit_id(target), desired,
            attack_urgent=idle_seconds >= config.idle_hard_seconds,
            reason="idle_deadline",
        )

    if _score(me) <= config.danger_score:
        vulnerable = [
            foe for foe in foes
            if _energy(foe) + config.attack_margin <= _energy(me)
        ]
        if not vulnerable:
            target = _flee_point(me_position, foes, config)
            memory.mode = "SURVIVE"
            return Intent("SURVIVE", target[0], target[1], reason="low_score_no_safe_prey")
        target = min(vulnerable, key=lambda foe: distance(me_position, position(foe)))
        desired = min(int(_energy(me)), int(_energy(target) + config.attack_margin))
        predicted = _predicted_position(target, config.prediction_seconds) or position(target)
        memory.mode = "SURVIVE"
        return Intent(
            "SURVIVE", predicted[0], predicted[1], rabbit_id(target), desired,
            reason="low_score_safe_prey",
        )

    protect_gap = (
        config.series_protect_gap
        if memory.series_posture == "PROTECT_SERIES" else config.protect_lead
    )
    if (
        remaining <= config.protect_remaining_seconds
        and _rank(me, foes) <= 2
        and _advancement_gap(me, foes) >= protect_gap
    ):
        target = _flee_point(me_position, foes, config)
        memory.mode = "PROTECT"
        return Intent("PROTECT", target[0], target[1], reason="top_two_score_cushion")

    target = _farm_target(me, foes, memory, config, elapsed)
    predicted = _predicted_position(target, config.prediction_seconds) or position(target)
    into_window = elapsed % 30.0
    tail_seconds = (
        config.all_in_tail_seconds + 2.0
        if memory.series_posture == "MUST_SCORE" else config.all_in_tail_seconds
    )
    tail = into_window >= 30.0 - tail_seconds
    desired = _attack_for(target, me, memory, config, tail)
    memory.mode = "FARM"
    return Intent(
        "FARM", predicted[0], predicted[1], rabbit_id(target), desired,
        attack_urgent=tail,
        reason="window_tail_all_in" if tail else "best_target_score",
    )
