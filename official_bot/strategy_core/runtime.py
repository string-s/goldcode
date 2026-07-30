"""Orchestrates observation, memory, policy and controller."""

import copy
import os
from pathlib import Path

from storage import ProfileStore

from .collision import time_to_collision
from .config import StrategyConfig
from .controller import choose_control
from .geometry import flatten_polygons, number, position
from .memory import StrategyMemory, is_active, rabbit_id
from .policy import choose_intent


class WolfStrategy:
    def __init__(self, config=None, profile_db_path=None, profile_mode=None):
        self.config = config or StrategyConfig()
        self.memory = StrategyMemory(requested_attack=self.config.default_attack)
        self.memory.reset_match(self.config.default_attack)
        self.last_diagnostics = {}
        self.profile_db_path = profile_db_path
        self.profile_mode = profile_mode or os.environ.get("WOLF_PROFILE_MODE", "auto")
        self.profile_store = None
        self.profile_write_enabled = False

    def on_game_start(self, start_data, context=None):
        map_data = start_data.get("map") if isinstance(start_data, dict) else None
        self.memory.reset_match(self.config.default_attack, map_data, context)
        self.memory.start_series_game(context, self.config)
        blocks = map_data.get("blocks") if isinstance(map_data, dict) else []
        borders = map_data.get("borders") if isinstance(map_data, dict) else []
        self.memory.obstacle_polygons = flatten_polygons(blocks) + flatten_polygons(borders)
        context = context if isinstance(context, dict) else {}
        runtime_dir = Path(context.get("runtimeDir") or "runtime")
        database_path = Path(
            self.profile_db_path
            or os.environ.get("WOLF_PROFILE_DB")
            or runtime_dir / "wolf-profiles.sqlite3"
        )
        self.profile_store = ProfileStore(database_path)
        bot_id = str(context.get("botId"))
        rabbits = start_data.get("rabbits") if isinstance(start_data, dict) else []
        opponent_ids = [
            rabbit_id(rabbit) for rabbit in rabbits or []
            if rabbit_id(rabbit).removeprefix("ai:") != bot_id
        ]
        self.memory.load_profiles(
            self.profile_store.load_many(opponent_ids), self.config.default_attack)
        match_type = context.get("matchType")
        self.profile_write_enabled = (
            self.profile_mode == "read-write"
            or (self.profile_mode == "auto" and match_type == "PRACTICE")
        )

    def on_game_end(self, settlement=None, battle_data=None):
        context = self.memory.game_context
        bot_id = str(context.get("botId"))
        result = settlement.get("result") if isinstance(settlement, dict) else None
        rankings = result.get("ranking") if isinstance(result, dict) else None
        row = next((
            item for item in rankings or [] if str(item.get("botId")) == bot_id
        ), {})
        rank = row.get("rank") if row else (
            settlement.get("resultRank") if isinstance(settlement, dict) else None)
        self.memory.finish_series_game(rank, row.get("points") if row else None, self.config)
        if self.profile_write_enabled and self.profile_store is not None:
            self.profile_store.save_many(self.memory.export_profiles())

    def reset_for_test(self):
        self.memory.opponent_models.clear()
        self.memory.reset_match(self.config.default_attack)
        self.last_diagnostics = {}

    def diagnostics(self):
        return copy.deepcopy(self.last_diagnostics)

    def _find_me(self, rabbits, bot_id):
        expected = str(bot_id)
        for rabbit in rabbits:
            identifier = rabbit_id(rabbit)
            if identifier == expected or identifier == "ai:" + expected:
                return rabbit
        return None

    def _maybe_detect_new_match(self, me, elapsed):
        survival = number(me.get("survivalTime"), elapsed)
        time_restarted = elapsed + 2 < self.memory.last_elapsed
        survival_restarted = survival + 2 < self.memory.last_elapsed
        if self.memory.last_elapsed > 5 and (time_restarted or survival_restarted):
            polygons = self.memory.obstacle_polygons
            self.memory.reset_match(
                self.config.default_attack, self.memory.map_data, self.memory.game_context)
            self.memory.obstacle_polygons = polygons

    def choose_command(self, game_state, bot_id):
        rabbits = game_state.get("rabbits") if isinstance(game_state, dict) else None
        if not isinstance(rabbits, list):
            rabbits = []
        me = self._find_me(rabbits, bot_id)
        if me is None or not is_active(me) or position(me) is None:
            return {"commandType": "stop"}

        elapsed = number(
            game_state.get("elapsedSeconds"), number(me.get("survivalTime"), 0.0))
        self._maybe_detect_new_match(me, elapsed)
        self.memory.update(rabbits, bot_id, elapsed, self.config)
        foes = [
            rabbit for rabbit in rabbits
            if rabbit is not me and is_active(rabbit) and position(rabbit) is not None
        ]
        if not foes:
            center_x = self.config.arena_width / 2
            center_y = self.config.arena_height / 2
            from .models import Intent
            intent = Intent("SAFE", center_x, center_y, reason="no_active_opponents")
        else:
            intent = choose_intent(game_state, me, foes, self.memory, self.config)
        command = choose_control(intent, me, foes, self.memory, self.config)
        target = next(
            (foe for foe in foes if rabbit_id(foe) == intent.target_id), None)
        elapsed = number(
            game_state.get("elapsedSeconds"), number(me.get("survivalTime"), 0.0))
        predicted_collision = (
            time_to_collision(me, target, self.config.collision_body_scale)
            if target is not None else None
        )
        target_contact_age = (
            self.memory.contact_age(intent.target_id, elapsed)
            if intent.target_id is not None else None
        )
        self.last_diagnostics = {
            "matchSerial": self.memory.match_serial,
            "elapsedSeconds": round(elapsed, 3),
            "mode": intent.mode,
            "reason": intent.reason,
            "targetId": intent.target_id,
            "target": {"x": round(intent.target_x, 3), "y": round(intent.target_y, 3)},
            "desiredAttack": intent.desired_attack,
            "requestedAttack": self.memory.requested_attack,
            "estimatedTargetAttack": (
                round(self.memory.estimate_attack(target, self.config.default_attack), 3)
                if target is not None else None
            ),
            "predictedCollisionSteps": (
                round(predicted_collision, 3) if predicted_collision is not None else None
            ),
            "targetContactAge": (
                round(target_contact_age, 3) if target_contact_age is not None else None
            ),
            "rebounding": bool(me.get("rebounding")),
            "series": {
                "gameNo": self.memory.current_game_no,
                "gamesPerTable": self.memory.games_per_table,
                "pointsBeforeGame": self.memory.series_points,
                "previousResults": list(self.memory.series_results),
                "posture": self.memory.series_posture,
            },
            "myEnergy": number(me.get("energy")),
            "myScore": int(number(me.get("score"))),
            "idleSeconds": round(max(0.0, elapsed - self.memory.last_contact_at), 3),
            "obstacleCount": len(self.memory.obstacle_polygons),
            "command": dict(command),
        }
        return command
