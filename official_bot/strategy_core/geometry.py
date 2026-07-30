"""Geometry helpers for the car-like official controller."""

import math


def number(value, default=0.0):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def position(entity):
    point = entity.get("position") if isinstance(entity, dict) else None
    if not isinstance(point, dict):
        return None
    x = number(point.get("x"), None)
    y = number(point.get("y"), None)
    if x is None or y is None:
        return None
    return x, y


def distance(left, right):
    return math.hypot(left[0] - right[0], left[1] - right[1])


def normalize_angle(angle):
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def clamp_point(point, width, height, margin):
    return (
        max(margin, min(width - margin, point[0])),
        max(margin, min(height - margin, point[1])),
    )


def valid_carrot(value):
    if not isinstance(value, dict):
        return None
    x = number(value.get("x"), None)
    y = number(value.get("y"), None)
    if x is None or y is None or x <= 0 or y <= 0:
        return None
    return x, y


def flatten_polygons(groups):
    polygons = []
    if not isinstance(groups, list):
        return polygons
    for physical_object in groups:
        if not isinstance(physical_object, list):
            continue
        for convex_part in physical_object:
            if not isinstance(convex_part, list):
                continue
            polygon = []
            for point in convex_part:
                if not isinstance(point, dict):
                    continue
                x = number(point.get("x"), None)
                y = number(point.get("y"), None)
                if x is not None and y is not None:
                    polygon.append((x, y))
            if len(polygon) >= 3:
                polygons.append(polygon)
    return polygons


def _orientation(a, b, c):
    value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    if abs(value) < 1e-9:
        return 0
    return 1 if value > 0 else 2


def _on_segment(a, b, c):
    return (
        min(a[0], c[0]) - 1e-9 <= b[0] <= max(a[0], c[0]) + 1e-9
        and min(a[1], c[1]) - 1e-9 <= b[1] <= max(a[1], c[1]) + 1e-9
    )


def segments_intersect(a, b, c, d):
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and _on_segment(a, c, b))
        or (o2 == 0 and _on_segment(a, d, b))
        or (o3 == 0 and _on_segment(c, a, d))
        or (o4 == 0 and _on_segment(c, b, d))
    )


def point_in_polygon(point, polygon):
    inside = False
    x, y = point
    j = len(polygon) - 1
    for i, current in enumerate(polygon):
        previous = polygon[j]
        if ((current[1] > y) != (previous[1] > y)):
            denom = previous[1] - current[1]
            x_cross = (previous[0] - current[0]) * (y - current[1]) / (denom or 1e-12) + current[0]
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def segment_distance(point, start, end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-9:
        return distance(point, start)
    ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
    ratio = max(0.0, min(1.0, ratio))
    projection = (start[0] + ratio * dx, start[1] + ratio * dy)
    return distance(point, projection)


def segment_pair_distance(a, b, c, d):
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(
        segment_distance(a, c, d),
        segment_distance(b, c, d),
        segment_distance(c, a, b),
        segment_distance(d, a, b),
    )


def path_blocking_polygon(start, end, polygons, margin):
    for polygon in polygons:
        if point_in_polygon(start, polygon) or point_in_polygon(end, polygon):
            return polygon
        for index, edge_start in enumerate(polygon):
            edge_end = polygon[(index + 1) % len(polygon)]
            if segment_pair_distance(start, end, edge_start, edge_end) < margin:
                return polygon
    return None


def detour_target(start, target, polygons, width, height, margin):
    """Return a conservative waypoint when a polygon blocks the direct path."""
    polygon = path_blocking_polygon(start, target, polygons, margin)
    if polygon is None:
        return clamp_point(target, width, height, margin)

    min_x = min(point[0] for point in polygon) - margin
    max_x = max(point[0] for point in polygon) + margin
    min_y = min(point[1] for point in polygon) - margin
    max_y = max(point[1] for point in polygon) + margin
    candidates = [
        clamp_point((min_x, min_y), width, height, margin),
        clamp_point((min_x, max_y), width, height, margin),
        clamp_point((max_x, min_y), width, height, margin),
        clamp_point((max_x, max_y), width, height, margin),
    ]
    clear = [
        point for point in candidates
        if path_blocking_polygon(start, point, polygons, margin * 0.55) is None
    ]
    pool = clear or candidates
    return min(pool, key=lambda point: distance(start, point) + distance(point, target))
