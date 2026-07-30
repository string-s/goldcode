"""Cross-frame and cross-match strategy memory."""

from dataclasses import dataclass, field

from .geometry import distance, number, position
from .models import OpponentModel


def rabbit_id(rabbit):
    return str(rabbit.get("id"))


def is_active(rabbit):
    active = rabbit.get("active")
    return active is not False and active != "false"


def is_invincible(rabbit):
    return bool(rabbit.get("attacking") or rabbit.get("invincible"))


@dataclass
class StrategyMemory:
    requested_attack: int = 50
    mode: str = "FARM"
    target_id: str | None = None
    target_selected_at: float = -1e9
    last_contact_at: float = 0.0
    last_elapsed: float = -1.0
    last_remaining: float = 180.0
    match_serial: int = 0
    game_context: dict = field(default_factory=dict)
    map_data: dict = field(default_factory=dict)
    obstacle_polygons: list = field(default_factory=list)
    previous_rabbits: dict = field(default_factory=dict)
    opponent_models: dict = field(default_factory=dict)
    last_contact_by_opponent: dict = field(default_factory=dict)
    last_contact_target_id: str | None = None

    def reset_match(self, default_attack=50, map_data=None, context=None):
        self.requested_attack = default_attack
        self.mode = "FARM"
        self.target_id = None
        self.target_selected_at = -1e9
        self.last_contact_at = 0.0
        self.last_elapsed = -1.0
        self.last_remaining = 180.0
        self.previous_rabbits = {}
        self.last_contact_by_opponent = {}
        self.last_contact_target_id = None
        self.map_data = map_data if isinstance(map_data, dict) else {}
        self.game_context = context if isinstance(context, dict) else {}
        self.obstacle_polygons = []
        self.match_serial += 1

    def model_for(self, opponent_id, default_attack=50.0):
        model = self.opponent_models.get(opponent_id)
        if model is None:
            model = OpponentModel(default_attack, default_attack, 0)
            self.opponent_models[opponent_id] = model
        return model

    def update(self, rabbits, my_id, elapsed, config):
        """Update contact timers and infer opponent attack samples."""
        crossed_reset = (
            self.last_elapsed >= 0
            and int(self.last_elapsed // 30) != int(elapsed // 30)
        )
        current = {rabbit_id(rabbit): rabbit for rabbit in rabbits if isinstance(rabbit, dict)}
        me = current.get(str(my_id)) or current.get("ai:" + str(my_id))
        previous_me = None
        if me is not None:
            previous_me = self.previous_rabbits.get(rabbit_id(me))
        if previous_me is not None:
            energy_drop = number(previous_me.get("energy")) - number(me.get("energy"))
            score_delta = number(me.get("score")) - number(previous_me.get("score"))
            rebound_started = bool(me.get("rebounding")) and not bool(previous_me.get("rebounding"))
            if energy_drop > 0 or abs(score_delta) == 1 or rebound_started:
                self.last_contact_at = elapsed
                me_position = position(me)
                candidates = [
                    rabbit for opponent_id, rabbit in current.items()
                    if opponent_id != rabbit_id(me) and is_active(rabbit)
                    and position(rabbit) is not None
                ]
                if me_position is not None and candidates:
                    nearest = min(candidates, key=lambda rabbit: distance(
                        me_position, position(rabbit)))
                    if distance(me_position, position(nearest)) <= config.contact_identification_distance:
                        target_id = rabbit_id(nearest)
                        self.last_contact_target_id = target_id
                        self.last_contact_by_opponent[target_id] = elapsed

        for opponent_id, rabbit in current.items():
            if me is not None and opponent_id == rabbit_id(me):
                continue
            previous = self.previous_rabbits.get(opponent_id)
            if previous is None or crossed_reset:
                continue
            before = number(previous.get("energy"))
            after = number(rabbit.get("energy"))
            spent = before - after
            if (
                config.opponent_min_sample <= spent <= config.opponent_max_sample
                and not is_invincible(previous)
                and not is_invincible(rabbit)
            ):
                self.model_for(opponent_id, config.default_attack).observe_attack(
                    spent, config.opponent_ema_alpha)

        self.previous_rabbits = {
            key: dict(value) for key, value in current.items()
        }
        self.last_elapsed = elapsed

    def estimate_attack(self, rabbit, default_attack=50):
        model = self.model_for(rabbit_id(rabbit), default_attack)
        return model.attack_ema

    def contact_age(self, opponent_id, elapsed):
        contacted_at = self.last_contact_by_opponent.get(str(opponent_id))
        return None if contacted_at is None else max(0.0, elapsed - contacted_at)

    def on_collision_cooldown(self, opponent_id, elapsed, cooldown_seconds):
        age = self.contact_age(opponent_id, elapsed)
        return age is not None and age < cooldown_seconds
