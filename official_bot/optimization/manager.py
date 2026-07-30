"""Validate, test, version and atomically publish LLM config proposals."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from strategy_core.config import (
    TUNABLE_RANGES,
    StrategyConfig,
    load_config_file,
    tunable_values,
    validate_overrides,
)

from .providers import provider_from_env


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_json(value):
    if isinstance(value, dict):
        return value
    text = str(value).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("provider did not return a JSON object")
    return json.loads(text[start:end + 1])


class OptimizationManager:
    def __init__(
        self,
        project_dir,
        runtime_dir,
        provider=None,
        mode=None,
        phase=None,
        run_checks=True,
    ):
        self.project_dir = Path(project_dir)
        self.runtime_dir = Path(runtime_dir)
        self.directory = self.runtime_dir / "optimizer"
        self.history_dir = self.directory / "history"
        self.active_path = self.directory / "active-config.json"
        self.previous_path = self.directory / "previous-config.json"
        self.decisions_path = self.directory / "decisions.jsonl"
        self.provider = provider if provider is not None else provider_from_env()
        self.mode = mode or os.environ.get("WOLF_OPTIMIZER_MODE", "off")
        self.phase = phase or os.environ.get("WOLF_PHASE", "practice")
        self.run_checks = run_checks

    def _log(self, record):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.decisions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _current(self):
        config, overrides = load_config_file(self.active_path, StrategyConfig())
        return config, overrides

    def _prompt(self, report, current):
        return json.dumps({
            "task": "Propose zero to four numeric parameter changes supported by match evidence.",
            "rules": [
                "Return one JSON object only.",
                "Do not output Python or prose.",
                "Prefer the smallest evidence-backed change.",
                "An empty object means keep the current strategy.",
            ],
            "allowedRanges": TUNABLE_RANGES,
            "currentConfig": current,
            "matchReport": report,
        }, ensure_ascii=False)

    def _gate(self, candidate_path):
        if not self.run_checks:
            return
        env = dict(os.environ)
        env["WOLF_OPTIMIZER_MODE"] = "off"
        env["WOLF_ACTIVE_CONFIG"] = str(candidate_path)
        result = subprocess.run(
            [sys.executable, str(self.project_dir / "check.py")],
            cwd=self.project_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("candidate failed check.py: " + result.stdout[-1000:] + result.stderr[-1000:])

    def process_report(self, report_path):
        record = {"timestamp": _now(), "report": str(report_path), "mode": self.mode,
                  "phase": self.phase}
        if self.mode not in {"suggest", "auto"}:
            record["status"] = "disabled"
            self._log(record)
            return record
        if self.phase == "top16-adjust" and self.mode == "auto":
            record["status"] = "manual_promotion_required"
            self._log(record)
            return record
        if self.phase not in {"practice", "top16-adjust"}:
            record["status"] = "frozen_phase"
            self._log(record)
            return record
        if self.provider is None:
            record["status"] = "no_provider"
            self._log(record)
            return record

        try:
            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
            config, active_overrides = self._current()
            proposal = _extract_json(self.provider.propose(
                self._prompt(report, tunable_values(config))))
            validated = validate_overrides(proposal, tunable_values(config), max_changes=4)
            candidate = dict(active_overrides)
            candidate.update(validated)
            # Validate the merged file against the base config as well.
            load_candidate = self.directory / "candidate-config.json"
            self.directory.mkdir(parents=True, exist_ok=True)
            load_candidate.write_text(
                json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            load_config_file(load_candidate, StrategyConfig())
            self._gate(load_candidate)

            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            self.history_dir.mkdir(parents=True, exist_ok=True)
            history_path = self.history_dir / f"candidate-{stamp}.json"
            shutil.copy2(load_candidate, history_path)
            record.update({"candidate": candidate, "changes": validated,
                           "historyPath": str(history_path)})
            if self.mode == "auto" and validated:
                self.promote_candidate(load_candidate, log=False)
                record["status"] = "promoted"
            else:
                record["status"] = "suggested" if validated else "no_change"
            self._log(record)
            return record
        except Exception as error:
            record["status"] = "rejected"
            record["error"] = str(error)[:500]
            self._log(record)
            raise

    def promote_candidate(self, candidate_path, log=True):
        if self.phase not in {"practice", "top16-adjust"}:
            raise RuntimeError(f"config promotion is frozen in phase: {self.phase}")
        candidate_path = Path(candidate_path)
        load_config_file(candidate_path, StrategyConfig())
        self._gate(candidate_path)
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.active_path.exists():
            shutil.copy2(self.active_path, self.previous_path)
        temporary = self.directory / ".active-config.tmp"
        shutil.copy2(candidate_path, temporary)
        os.replace(temporary, self.active_path)
        if log:
            self._log({
                "timestamp": _now(),
                "status": "manually_promoted",
                "candidate": str(candidate_path),
                "phase": self.phase,
            })
        return self.active_path

    def rollback(self):
        if not self.previous_path.exists():
            return False
        temporary = self.directory / ".rollback.tmp"
        shutil.copy2(self.previous_path, temporary)
        os.replace(temporary, self.active_path)
        self._log({"timestamp": _now(), "status": "rolled_back"})
        return True
