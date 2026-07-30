"""Safe config validation, promotion, freeze and rollback tests."""

import json
import tempfile
from pathlib import Path

from optimization.manager import OptimizationManager
from strategy_core.config import StrategyConfig, load_config_file, validate_overrides


class FakeProvider:
    def propose(self, prompt):
        assert "allowedRanges" in prompt
        return {"attack_margin": 42, "reserve_energy": 220}


directory = Path(tempfile.mkdtemp(prefix="wolf-optimizer-"))
project_dir = Path(__file__).resolve().parent.parent
runtime_dir = directory / "runtime"
report = directory / "match-report.json"
report.write_text(json.dumps({
    "result": {"rank": 3, "score": 6},
    "events": {"estimatedObstacleLosses": 0},
    "energy": {"energyBeforeResets": [300, 250]},
}), encoding="utf-8")

manager = OptimizationManager(
    project_dir, runtime_dir, provider=FakeProvider(), mode="auto",
    phase="practice", run_checks=False)
result = manager.process_report(report)
assert result["status"] == "promoted"
config, overrides = load_config_file(manager.active_path, StrategyConfig())
assert overrides == {"attack_margin": 42, "reserve_energy": 220}
assert config.attack_margin == 42

# A second promotion creates a rollback target.
class SecondProvider:
    def propose(self, prompt):
        return {"attack_margin": 45}


manager.provider = SecondProvider()
manager.process_report(report)
assert manager.rollback() is True
_, rolled_back = load_config_file(manager.active_path, StrategyConfig())
assert rolled_back["attack_margin"] == 42

manual = directory / "manual.json"
manual.write_text(json.dumps({"attack_margin": 44}), encoding="utf-8")
manager.promote_candidate(manual)
_, manually_promoted = load_config_file(manager.active_path, StrategyConfig())
assert manually_promoted["attack_margin"] == 44

frozen = OptimizationManager(
    project_dir, runtime_dir, provider=FakeProvider(), mode="auto",
    phase="elimination", run_checks=False)
assert frozen.process_report(report)["status"] == "frozen_phase"
try:
    frozen.promote_candidate(manual)
except RuntimeError:
    pass
else:
    raise AssertionError("elimination phase must reject manual promotion")

top16_auto = OptimizationManager(
    project_dir, runtime_dir, provider=FakeProvider(), mode="auto",
    phase="top16-adjust", run_checks=False)
assert top16_auto.process_report(report)["status"] == "manual_promotion_required"

try:
    validate_overrides({"unknown": 1}, {})
except ValueError:
    pass
else:
    raise AssertionError("unknown parameter must be rejected")

try:
    validate_overrides({"attack_margin": 500}, {"attack_margin": 35})
except ValueError:
    pass
else:
    raise AssertionError("out-of-range parameter must be rejected")

print("optimizer tests passed")
