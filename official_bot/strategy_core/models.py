"""Small internal models shared by policy and controller."""

from dataclasses import dataclass


@dataclass
class Intent:
    mode: str
    target_x: float
    target_y: float
    target_id: str | None = None
    desired_attack: int | None = None
    attack_urgent: bool = False
    stop: bool = False
    reason: str = ""


@dataclass
class OpponentModel:
    attack_ema: float = 50.0
    attack_peak: float = 50.0
    samples: int = 0

    def observe_attack(self, spent: float, alpha: float) -> None:
        if self.samples == 0:
            self.attack_ema = spent
        else:
            self.attack_ema = (1.0 - alpha) * self.attack_ema + alpha * spent
        self.attack_peak = max(self.attack_peak, spent)
        self.samples += 1
