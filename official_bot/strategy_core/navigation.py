"""Conservative local trajectory sampler for persistent car controls."""

import math

from .collision import body_radius, velocity
from .geometry import distance, number, path_blocking_polygon, position


def _turn_sign(command_type, me):
    if command_type == "turnLeft":
        return -1.0
    if command_type == "turnRight":
        return 1.0
    if command_type == "steerBack":
        return 0.0
    direction = int(number(me.get("dirState")))
    return -1.0 if direction < 0 else (1.0 if direction > 0 else 0.0)


def _trajectory(command_type, me, config):
    current = position(me)
    angle = number(me.get("angle"))
    turn_sign = _turn_sign(command_type, me)
    points = [current]
    for _ in range(config.planner_steps):
        angle += turn_sign * config.planner_turn_radians
        current = (
            current[0] + math.cos(angle) * config.planner_step_distance,
            current[1] + math.sin(angle) * config.planner_step_distance,
        )
        points.append(current)
    return points


def _dynamic_collision(point, step, foe, clearance, config):
    foe_position = position(foe)
    if foe_position is None:
        return False
    vx, vy = velocity(foe)
    predicted = (foe_position[0] + vx * step, foe_position[1] + vy * step)
    return distance(point, predicted) < clearance + body_radius(
        foe, config.collision_body_scale) + config.planner_dynamic_margin


def _trajectory_cost(points, target, me, obstacles, dynamic_foes, config):
    clearance = body_radius(me, config.collision_body_scale) + config.obstacle_margin
    cost = 0.0
    for step, point in enumerate(points[1:], 1):
        if not (
            config.planner_edge_margin <= point[0] <= config.arena_width - config.planner_edge_margin
            and config.planner_edge_margin <= point[1] <= config.arena_height - config.planner_edge_margin
        ):
            cost += config.planner_collision_penalty
        if path_blocking_polygon(points[step - 1], point, obstacles, clearance) is not None:
            cost += config.planner_collision_penalty
        for foe in dynamic_foes:
            if _dynamic_collision(point, step, foe, clearance, config):
                cost += config.planner_collision_penalty
    cost += distance(points[-1], target)
    return cost


def choose_navigation_command(intent, me, foes, memory, config):
    """Select the safest useful persistent steering-state change."""
    target = (intent.target_x, intent.target_y)
    avoid_target = intent.mode in {"SAFE", "EVADE", "PROTECT", "RACE"}
    dynamic_foes = [
        foe for foe in foes
        if avoid_target or str(foe.get("id")) != str(intent.target_id)
    ]
    candidates = ["steerBack", "turnLeft", "turnRight"]
    current_direction = int(number(me.get("dirState")))
    best = None
    best_cost = float("inf")
    for candidate in candidates:
        points = _trajectory(candidate, me, config)
        cost = _trajectory_cost(
            points, target, me, memory.obstacle_polygons, dynamic_foes, config)
        candidate_direction = -1 if candidate == "turnLeft" else (1 if candidate == "turnRight" else 0)
        if current_direction and candidate_direction and candidate_direction != current_direction:
            cost += config.planner_turn_switch_penalty
        if cost < best_cost:
            best = candidate
            best_cost = cost
    if best == "turnLeft":
        return {"commandType": "turnLeft", "data": f"{config.turn_speed:.3f}"}
    if best == "turnRight":
        return {"commandType": "turnRight", "data": f"{config.turn_speed:.3f}"}
    if current_direction != 0:
        return {"commandType": "steerBack"}
    return {"commandType": "goForward"}
