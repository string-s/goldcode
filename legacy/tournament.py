# -*- coding: utf-8 -*-
"""
自博弈循环赛 + 参数扫描
=======================
用法：
  python3 tournament.py            # 四预设互打 + 混桌赛（对抗基线画像）
  python3 tournament.py --sweep    # 关键参数网格扫描（OFFSET / ALLIN_TAIL / RESERVE）
产出：每预设的平均名次 / 平均果实 / 桌冠率 / 晋级率(前2)。
"""
import sys
import itertools
from collections import defaultdict
from sim.engine import Engine, SimConfig
from agents.base import SafeAgent, RandomAgent, ChaserAgent, TurtleAgent, FixedProbe
from agents.presets import make, PRESETS
from agents.statemachine import FireflyAgent


def play_table(builders, seed, sim_kw=None):
    agents = [SafeAgent(b()) for b in builders]
    cfg = SimConfig(seed=seed, **(sim_kw or {}))
    res = Engine(agents, cfg).run()
    return res, [a.name for a in agents]


def summarize(tag, rows):
    # rows: list of (name, rank, fruit)
    agg = defaultdict(lambda: dict(n=0, rank=0, fruit=0, top1=0, top2=0))
    for name, rank, fruit in rows:
        a = agg[name]
        a["n"] += 1
        a["rank"] += rank
        a["fruit"] += fruit
        a["top1"] += rank == 1
        a["top2"] += rank <= 2
    print(f"\n== {tag} ==")
    print(f"{'agent':22s} {'场次':>4s} {'均名次':>6s} {'均果实':>6s} {'桌冠率':>6s} {'晋级率':>6s}")
    for name, a in sorted(agg.items(), key=lambda kv: kv[1]['rank'] / kv[1]['n']):
        n = a["n"]
        print(f"{name:22s} {n:4d} {a['rank']/n:6.2f} {a['fruit']/n:6.1f} "
              f"{a['top1']/n:6.0%} {a['top2']/n:6.0%}")


def round_robin(n_seeds=12):
    """四预设互打（每桌四个不同预设，轮换座位）。"""
    names = list(PRESETS.keys())
    rows = []
    for seed in range(n_seeds):
        order = names[seed % 4:] + names[:seed % 4]     # 轮换出生位
        builders = [lambda p=p, s=seed: make(p, seed=100 + s) for p in order]
        res, anames = play_table(builders, seed)
        for pos, sid in enumerate(res["ranking"], 1):
            rows.append((anames[sid], pos, res["fruits"][sid]))
    summarize("预设互打 round-robin", rows)


def vs_field(n_seeds=12):
    """每个预设单独放进'典型对手池'（追击/龟缩/固定价）里测成色。"""
    rows = []
    for p in PRESETS:
        for seed in range(n_seeds):
            builders = [
                lambda p=p, s=seed: make(p, seed=200 + s),
                lambda: ChaserAgent(power=300),
                lambda: TurtleAgent(),
                lambda s=seed: FixedProbe(power=[150, 200, 250][s % 3]),
            ]
            res, anames = play_table(builders, seed)
            rank = res["ranking"].index(0) + 1      # 主测 agent 固定坐 0 号位
            rows.append((f"{p}*", rank, res["fruits"][0]))
    summarize("对抗典型对手池", rows)


def sweep(n_seeds=8):
    """关键参数网格：主力(变体) vs balanced + chaser + probe200。"""
    grid = dict(
        OFFSET=[25, 35, 50],
        ALLIN_TAIL=[5.0, 7.0, 9.0],
        RESERVE=[150, 250, 350],
    )
    keys = list(grid)
    combos = list(itertools.product(*grid.values()))
    results = []
    for combo in combos:
        cfg = dict(zip(keys, combo))
        tot_rank = tot_fruit = 0
        for seed in range(n_seeds):
            builders = [
                lambda c=cfg, s=seed: FireflyAgent(cfg=c, name="variant", seed=300 + s),
                lambda s=seed: make("balanced", seed=400 + s),
                lambda: ChaserAgent(power=300),
                lambda: FixedProbe(power=200),
            ]
            res, anames = play_table(builders, seed)
            sid = anames.index("safe(variant)")
            tot_rank += res["ranking"].index(sid) + 1
            tot_fruit += res["fruits"][sid]
        results.append((tot_rank / n_seeds, tot_fruit / n_seeds, cfg))
    results.sort(key=lambda r: (r[0], -r[1]))
    print("\n== 参数扫描（越靠上越好）==")
    for rank, fruit, cfg in results[:10]:
        print(f"均名次 {rank:.2f}  均果实 {fruit:5.1f}  {cfg}")
    print(f"...共 {len(results)} 组合")


if __name__ == "__main__":
    if "--sweep" in sys.argv:
        sweep()
    else:
        round_robin()
        vs_field()
