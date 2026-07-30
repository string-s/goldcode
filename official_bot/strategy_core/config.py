"""Central strategy parameters.

The live strategy reads these values but never mutates them.  Keeping all
thresholds in one dataclass makes later match-to-match optimisation safe: an
LLM can propose a small config change without rewriting the control loop.
"""

from dataclasses import dataclass


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

    opponent_ema_alpha: float = 0.35
    opponent_min_sample: float = 5.0
    opponent_max_sample: float = 1000.0
