"""Central strategy parameters and safe external override loading.

The live strategy reads these values but never mutates them.  Keeping all
thresholds in one dataclass makes later match-to-match optimisation safe: an
LLM can propose a small config change without rewriting the control loop.
"""

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class StrategyConfig:
    arena_width: float = 1440.0
    arena_height: float = 820.0

    edge_margin: float = 145.0
    obstacle_margin: float = 62.0
    center_pull: float = 0.16

    turn_tolerance: float = 0.17
    hard_turn_tolerance: float = 0.62
    turn_speed: float = 0.055
    hard_turn_speed: float = 0.082

    default_attack: int = 50
    attack_margin: int = 35
    reserve_energy: int = 250
    danger_score: int = 3
    kill_score: int = 2
    attack_prepare_distance: float = 190.0
    attack_reissue_delta: int = 5

    all_in_tail_seconds: float = 7.0
    idle_soft_seconds: float = 24.0
    idle_hard_seconds: float = 28.0
    protect_remaining_seconds: float = 30.0
    protect_lead: int = 3

    heart_race_ratio: float = 1.06
    heart_race_slack: float = 45.0
    invincible_threat_distance: float = 360.0
    target_hold_seconds: float = 0.8
    prediction_seconds: float = 0.65

    collision_cooldown_seconds: float = 1.5
    disengage_seconds: float = 1.05
    contact_identification_distance: float = 180.0
    collision_horizon_steps: float = 18.0
    collision_body_scale: float = 0.42

    planner_steps: int = 12
    planner_step_distance: float = 22.0
    planner_turn_radians: float = 0.105
    planner_dynamic_margin: float = 30.0
    planner_edge_margin: float = 78.0
    planner_collision_penalty: float = 1_000_000.0
    planner_turn_switch_penalty: float = 35.0

    opponent_ema_alpha: float = 0.35
    opponent_min_sample: float = 5.0
    opponent_max_sample: float = 1000.0

    series_points_by_rank: tuple = (4, 3, 2, 1)
    series_aggressive_average_points: float = 2.25
    series_protect_average_points: float = 3.25
    series_aggressive_reserve: int = 100
    series_protect_gap: int = 1


TUNABLE_RANGES = {
    "attack_margin": (5, 180),
    "reserve_energy": (0, 600),
    "all_in_tail_seconds": (3.0, 12.0),
    "idle_soft_seconds": (18.0, 27.0),
    "idle_hard_seconds": (25.0, 29.5),
    "protect_remaining_seconds": (10.0, 60.0),
    "protect_lead": (0, 8),
    "heart_race_ratio": (0.75, 1.25),
    "heart_race_slack": (0.0, 160.0),
    "invincible_threat_distance": (180.0, 700.0),
    "target_hold_seconds": (0.2, 2.5),
    "prediction_seconds": (0.1, 1.5),
    "attack_prepare_distance": (80.0, 360.0),
    "collision_cooldown_seconds": (1.2, 2.0),
    "disengage_seconds": (0.4, 1.4),
    "planner_step_distance": (8.0, 45.0),
    "planner_turn_radians": (0.03, 0.22),
    "planner_dynamic_margin": (5.0, 100.0),
    "series_aggressive_reserve": (0, 300),
    "series_protect_gap": (0, 5),
}


def tunable_values(config):
    values = asdict(config)
    return {key: values[key] for key in TUNABLE_RANGES}


def validate_overrides(overrides, current=None, max_changes=4):
    if not isinstance(overrides, dict):
        raise ValueError("strategy overrides must be a JSON object")
    if len(overrides) > max_changes:
        raise ValueError(f"at most {max_changes} parameters may change at once")
    current = current or {}
    validated = {}
    for key, value in overrides.items():
        if key not in TUNABLE_RANGES:
            raise ValueError(f"parameter is not tunable: {key}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"parameter must be numeric: {key}")
        lower, upper = TUNABLE_RANGES[key]
        if not lower <= value <= upper:
            raise ValueError(f"parameter out of range: {key}={value}")
        old = current.get(key)
        if old not in (None, 0):
            relative = abs(float(value) - float(old)) / abs(float(old))
            if relative > 0.5:
                raise ValueError(f"single-step change exceeds 50%: {key}")
        validated[key] = value
    return validated


def apply_overrides(config, overrides):
    validated = validate_overrides(overrides, tunable_values(config), max_changes=len(overrides))
    field_types = {field: type(getattr(config, field)) for field in validated}
    coerced = {
        key: field_types[key](value)
        for key, value in validated.items()
    }
    return replace(config, **coerced)


def load_config_file(path, base=None):
    base = base or StrategyConfig()
    path = Path(path)
    if not path.exists():
        return base, {}
    overrides = json.loads(path.read_text(encoding="utf-8"))
    return apply_overrides(base, overrides), overrides
