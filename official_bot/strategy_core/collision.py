"""Short-horizon collision prediction helpers."""

import math

from .geometry import number, position


def velocity(rabbit):
    value = rabbit.get("velocity") if isinstance(rabbit, dict) else None
    if not isinstance(value, dict):
        return 0.0, 0.0
    return number(value.get("x")), number(value.get("y"))


def body_radius(rabbit, scale=0.42):
    width = max(1.0, number(rabbit.get("width"), 70.0))
    height = max(1.0, number(rabbit.get("height"), 64.0))
    return max(width, height) * scale


def time_to_collision(left, right, scale=0.42):
    """Return predicted physics steps until two moving circles touch."""
    left_position = position(left)
    right_position = position(right)
    if left_position is None or right_position is None:
        return None
    lvx, lvy = velocity(left)
    rvx, rvy = velocity(right)
    px = right_position[0] - left_position[0]
    py = right_position[1] - left_position[1]
    vx = rvx - lvx
    vy = rvy - lvy
    radius = body_radius(left, scale) + body_radius(right, scale)
    c = px * px + py * py - radius * radius
    if c <= 0:
        return 0.0
    a = vx * vx + vy * vy
    if a < 1e-9:
        return None
    b = 2.0 * (px * vx + py * vy)
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0:
        return None
    root = math.sqrt(discriminant)
    candidates = [value for value in (
        (-b - root) / (2.0 * a),
        (-b + root) / (2.0 * a),
    ) if value >= 0]
    return min(candidates) if candidates else None
