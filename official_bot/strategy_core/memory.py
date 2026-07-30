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
    match_opponent_ids: set = field(default_factory=set)
    opponent_names: dict = field(default_factory=dict)
    profile_games: dict = field(default_factory=dict)
    profile_contacts: dict = field(default_factory=dict)
    series_points: int = 0
    series_results: list = field(default_factory=list)
    current_game_no: int | None = None
    games_per_table: int | None = None
    series_posture: str = "STEADY"

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
        self.match_opponent_ids = set()
        self.map_data = map_data if isinstance(map_data, dict) else {}
        self.game_context = context if isinstance(context, dict) else {}
        self.obstacle_polygons = []
        self.match_serial += 1

    def start_series_game(self, context, config):
        context = context if isinstance(context, dict) else {}
        game_no = int(number(context.get("gameNo"), 0)) or None
        games_per_table = int(number(context.get("gamesPerTable"), 0)) or None
        if game_no == 1 or (
            game_no is not None and self.current_game_no is not None
            and game_no <= self.current_game_no
        ):
            self.series_points = 0
            self.series_results = []
        self.current_game_no = game_no
        self.games_per_table = games_per_table
        played = len(self.series_results)
        average = self.series_points / played if played else 0.0
        if played and average >= config.series_protect_average_points:
            self.series_posture = "PROTECT_SERIES"
        elif played and average <= config.series_aggressive_average_points:
            self.series_posture = "MUST_SCORE"
        else:
            self.series_posture = "STEADY"

    def finish_series_game(self, rank, points, config):
        if rank is None:
            return
        rank = int(rank)
        if points is None and 1 <= rank <= len(config.series_points_by_rank):
            points = config.series_points_by_rank[rank - 1]
        points = int(points or 0)
        self.series_results.append({"rank": rank, "points": points})
        self.series_points += points

    def load_profiles(self, profiles, default_attack=50):
        for opponent_id, profile in profiles.items():
            model = self.model_for(opponent_id, default_attack)
            model.attack_ema = float(profile.get("attack_ema") or default_attack)
            model.attack_peak = float(profile.get("attack_peak") or default_attack)
            model.samples = int(profile.get("attack_samples") or 0)
            self.profile_games[opponent_id] = int(profile.get("games") or 0)
            self.profile_contacts[opponent_id] = int(profile.get("contacts") or 0)

    def export_profiles(self):
        rows = []
        for opponent_id in sorted(self.match_opponent_ids):
            model = self.model_for(opponent_id)
            rows.append({
                "opponent_id": opponent_id,
                "name": self.opponent_names.get(opponent_id),
                "games": self.profile_games.get(opponent_id, 0) + 1,
                "attack_ema": model.attack_ema,
                "attack_peak": model.attack_peak,
                "attack_samples": model.samples,
                "contacts": self.profile_contacts.get(opponent_id, 0)
                + (1 if opponent_id in self.last_contact_by_opponent else 0),
            })
        return rows

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
            self.match_opponent_ids.add(opponent_id)
            self.opponent_names[opponent_id] = rabbit.get("name")
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
