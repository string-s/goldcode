# -*- coding: utf-8 -*-
"""单场对局：python3 run_match.py [--verbose]
默认桌型：firefly(balanced) vs chaser vs turtle vs random，含守恒校验。"""
import sys
from sim.engine import Engine, SimConfig
from agents.base import SafeAgent, RandomAgent, ChaserAgent, TurtleAgent
from agents.presets import make


def main(verbose=False, seed=0):
    agents = [
        SafeAgent(make("balanced", seed=7)),
        SafeAgent(ChaserAgent(power=300)),
        SafeAgent(TurtleAgent()),
        SafeAgent(RandomAgent(seed=3)),
    ]
    cfg = SimConfig(seed=seed, energy_visible=False, bids_visible=False)
    eng = Engine(agents, cfg)
    res = eng.run()

    names = [a.name for a in agents]
    print("=" * 60)
    print(f"seed={seed}  最终果实：")
    for rank, sid in enumerate(res["ranking"], 1):
        s = res["stats"][sid]
        tag = "" if res["alive"][sid] else " [出局]"
        print(f"  #{rank} {names[sid]:20s} 果实={res['fruits'][sid]:>3}{tag}  "
              f"胜{s['wins']} 负{s['losses']} 平{s['draws']} "
              f"障碍{s['obst']} 怠速{s['idle']} 心{s['hearts']}(心胜{s['heart_wins']})")

    # 守恒校验：总果实 = 40 - 障碍蒸发 - 怠速蒸发
    total = sum(res["fruits"].values())
    evap = sum(s["obst"] + 3 * s["idle"] for s in res["stats"].values())
    print(f"  守恒校验: 总果实 {total} + 蒸发 {evap} = {total + evap} (应为 40)")
    assert total + evap == 40, "守恒校验失败——引擎有 bug！"

    if verbose:
        print("-" * 60)
        for e in eng.log:
            print(" ", e)


if __name__ == "__main__":
    v = "--verbose" in sys.argv
    for sd in range(3):
        main(verbose=v and sd == 0, seed=sd)
