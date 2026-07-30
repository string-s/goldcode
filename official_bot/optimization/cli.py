"""Run the safe optimiser manually during practice or an adjustment window."""

import argparse
from pathlib import Path

from .manager import OptimizationManager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, nargs="?")
    parser.add_argument("--mode", choices=("suggest", "auto"), default="suggest")
    parser.add_argument("--phase", choices=("practice", "top16-adjust"), default="practice")
    parser.add_argument("--promote", type=Path)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    project_dir = Path(__file__).resolve().parent.parent
    runtime_dir = project_dir / "runtime"
    manager = OptimizationManager(
        project_dir, runtime_dir, mode=args.mode, phase=args.phase)
    if args.rollback:
        print({"rolledBack": manager.rollback()})
    elif args.promote:
        print({"activeConfig": str(manager.promote_candidate(args.promote))})
    elif args.report:
        print(manager.process_report(args.report))
    else:
        parser.error("provide a report, --promote, or --rollback")


if __name__ == "__main__":
    main()
