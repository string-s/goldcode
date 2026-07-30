# -*- coding: utf-8 -*-
"""
形态 A 主力：状态机 Agent（FireflyAgent）
=========================================
七个模式：RAMPAGE(持心连撞) / EVADE(避敌方心) / RACE(抢心) /
          SURVIVE(低分求生) / PROTECT(终盘保排名) / CLOCK_RESET(防-3) / FARM(常态)
三条铁律：
  1. 零漏分优先：避障硬否决 > 一切追击欲望
  2. 窗口尾 all-in：能量过期作废，最后几秒清仓
  3. 压价不超杀：出价 = 估计对手价 + OFFSET + 抖动
全参数集中在 CFG，Loop 时只调参不动架构。
"""
import math
import random
from sim.views import Observation, Action
from .base import BaseAgent

DEFAULT_CFG = dict(
    # 出价
    PROBE_LO=120, PROBE_HI=200,   # 试探带（现场按 1000/N 校准）
    OFFSET=35,                    # 压价加成
    JITTER=17,                    # 防整数扎堆/防平局的抖动幅度
    RESERVE=250,                  # 中段能量底仓（防被秃鹫）
    ALLIN_TAIL=7.0,               # 窗口最后 X 秒清仓
    VULTURE_MARGIN=30,            # 秃鹫必胜价余量
    # 分数阈值
    DANGER=3,                     # 果实<=此值 -> SURVIVE
    KILL=2,                       # 对手果实<=此值 -> 优先补刀
    PROTECT_LEAD=4,               # 终盘领先>=此值 -> PROTECT
    PROTECT_T=150.0,              # 终盘起始时间
    # 走位
    OB_MARGIN=1.6,                # 避障额外余量（倍于精灵半径）
    BRAKE_T=0.55,                 # 刹车预判时间（秒）
    CLUSTER_R=8.0,                # 敌群禁区半径
    FLEE_DIRS=16,                 # 逃逸采样方向数
    IDLE_SOFT=24.0,               # 超过此闲置秒数进入 CLOCK_RESET
    IDLE_HARD=28.0,               # 超过此值宁可蹭障碍(-1)也不吃-3
)


class Ledger:
    """对手能量记账。能量可见 -> 直接读；不可见 -> 事件推断区间。"""

    def __init__(self, window):
        self.window = window
        self.est = {}          # id -> 估计已花费能量（本窗口）
        self.bid_ema = {}      # id -> 对手出价的指数均值
        self.win_start = 0.0

    def on_window_reset(self, t):
        self.win_start = t
        self.est = {k: 0 for k in self.est}

    def observe(self, obs: Observation, my_id):
        # 窗口切换检测
        w = obs.window
        if int(obs.t // w) != int(self.win_start // w):
            self.on_window_reset(obs.t - (obs.t % w))
        for f in obs.foes:
            self.est.setdefault(f.id, 0)
            self.bid_ema.setdefault(f.id, 200.0)
        for ev in obs.events:
            if ev.kind != "spirit":
                continue
            for pid, bid in ((ev.a_id, ev.a_bid), (ev.b_id, ev.b_bid)):
                if pid == my_id or pid < 0:
                    continue
                if bid is not None:                     # 出价可见
                    self.est[pid] = self.est.get(pid, 0) + bid
                    self.bid_ema[pid] = 0.6 * self.bid_ema.get(pid, bid) + 0.4 * bid
                else:                                   # 不可见 -> 用胜负推断
                    my_bid = ev.a_bid if ev.b_id == pid else ev.b_bid
                    inc = 180.0                         # 默认估计
                    if my_bid is not None:
                        if ev.winner_id == pid:
                            inc = my_bid * 1.35         # 他赢了我 -> 高于我
                        elif ev.winner_id == -2:
                            inc = my_bid
                        else:
                            inc = my_bid * 0.55         # 他输给我 -> 低于我
                    self.est[pid] = self.est.get(pid, 0) + inc
                    self.bid_ema[pid] = 0.7 * self.bid_ema.get(pid, inc) + 0.3 * inc

    def energy_of(self, f, init_energy=1000):
        if f.energy is not None:
            return f.energy
        return max(0, init_energy - self.est.get(f.id, 0))

    def mode_bid(self):
        if not self.bid_ema:
            return 180.0
        vals = sorted(self.bid_ema.values())
        return vals[len(vals) // 2]                     # 中位数当"众数"代理


class FireflyAgent(BaseAgent):
    def __init__(self, cfg=None, name="firefly", seed=7):
        self.C = dict(DEFAULT_CFG)
        if cfg:
            self.C.update(cfg)
        self.name = name
        self.rng = random.Random(seed)
        self.ledger = None
        self.mode = "FARM"

    # ================= 主入口 =================
    def act(self, obs: Observation) -> Action:
        C = self.C
        if self.ledger is None:
            self.ledger = Ledger(obs.window)
        self.ledger.observe(obs, obs.me.id)

        me = obs.me
        foes = [f for f in obs.foes if f.alive]
        if not foes:
            # 对手全出局：唯一扣分威胁是 -3，主动周期性蹭障碍(-1)止损
            idle = obs.t - obs.my_last_touch_t
            if idle > self.C["IDLE_SOFT"] and obs.obstacles:
                o = min(obs.obstacles,
                        key=lambda o: (o.x - me.x) ** 2 + (o.y - me.y) ** 2)
                return Action(o.x - me.x, o.y - me.y, 0)
            return Action(obs.arena_w / 2 - me.x, obs.arena_h / 2 - me.y, 0)

        self.mode = self._decide_mode(obs, me, foes)
        target, bid = self._plan(obs, me, foes)
        mvx, mvy = self._steer(obs, me, foes, target)
        # 紧急制动：被弹飞/惯性冲向障碍时，覆盖一切意图先脱险
        if not (isinstance(target, tuple) and target and target[0] == "OBSTACLE"):
            sp = math.hypot(me.vx, me.vy)
            if sp > 1.0 and self._blocked(obs, me, me.vx / sp, me.vy / sp):
                ex, ey = self._flee(obs, me, foes, None)
                mvx, mvy = ex - me.vx * 0.15, ey - me.vy * 0.15
        bid = max(0, min(int(bid), me.energy))
        return Action(mvx, mvy, bid)

    # ================= 模式判定 =================
    def _decide_mode(self, obs, me, foes):
        C = self.C
        t = obs.t
        if me.has_heart:
            return "RAMPAGE"
        holder = next((f for f in foes if f.has_heart), None)
        if holder is not None:
            return "EVADE"
        if obs.heart.on_field and self._win_heart_race(obs, me, foes):
            return "RACE"
        if me.fruit <= C["DANGER"]:
            return "SURVIVE"
        idle = t - obs.my_last_touch_t
        if idle > C["IDLE_SOFT"]:
            return "CLOCK_RESET"
        if t >= C["PROTECT_T"]:
            lead = me.fruit - max(f.fruit for f in foes)
            if lead >= C["PROTECT_LEAD"]:
                return "PROTECT"
        return "FARM"

    def _win_heart_race(self, obs, me, foes):
        hx, hy = obs.heart.x, obs.heart.y
        my_d = math.hypot(me.x - hx, me.y - hy)
        foe_d = min(math.hypot(f.x - hx, f.y - hy) for f in foes)
        return my_d < foe_d * 0.92 + 1.0     # 明显更近才去抢，别白跑

    # ================= 目标 & 出价 =================
    def _plan(self, obs, me, foes):
        C = self.C
        m = self.mode
        w = obs.window
        into_window = obs.t % w
        tail = into_window >= w - C["ALLIN_TAIL"]
        init_e = 1000

        if m == "RAMPAGE":
            # 免费必胜期：连撞最近目标链，出价 1（反正不扣能量）
            return self._nearest(me, foes), 1

        if m == "RACE":
            return ("HEART", obs.heart.x, obs.heart.y), self._farm_bid(tail, me)

        if m == "EVADE":
            return None, C["PROBE_LO"]          # 只逃，不主动碰

        if m == "SURVIVE":
            # 低分求生：只打必胜局（秃鹫），否则游走等窗口尾
            prey = self._vulture_prey(me, foes, init_e)
            if prey is not None:
                need = self.ledger.energy_of(prey, init_e) + C["VULTURE_MARGIN"]
                return prey, need
            if tail:
                return self._weakest(foes, init_e), me.energy
            return None, C["PROBE_LO"]

        if m == "PROTECT":
            # 领先保排名：避战为主，窗口尾仍收割一次稳固优势
            if tail:
                return self._weakest(foes, init_e), me.energy
            return None, C["PROBE_LO"]

        if m == "CLOCK_RESET":
            idle = obs.t - obs.my_last_touch_t
            prey = self._vulture_prey(me, foes, init_e)
            if prey is not None:
                need = self.ledger.energy_of(prey, init_e) + C["VULTURE_MARGIN"]
                return prey, need
            if idle > C["IDLE_HARD"]:
                return ("OBSTACLE",), 0          # 宁 -1 不 -3
            return self._nearest(me, foes), self._farm_bid(tail, me)

        # ---- FARM 常态 ----
        # 1) 补刀：对手果实极低 -> 送出局，减少一个威胁
        dying = [f for f in foes if f.fruit <= C["KILL"]]
        if dying:
            tgt = min(dying, key=lambda f: self._d2(me, f))
            return tgt, self._farm_bid(tail, me)
        # 2) 秃鹫必胜局
        prey = self._vulture_prey(me, foes, init_e)
        if prey is not None:
            need = self.ledger.energy_of(prey, init_e) + C["VULTURE_MARGIN"]
            return prey, need
        # 3) 窗口尾清仓 all-in：能量过期作废
        if tail:
            return self._weakest(foes, init_e), me.energy
        # 4) 常规：压价打最近目标
        return self._nearest(me, foes), self._farm_bid(tail, me)

    def _farm_bid(self, tail, me):
        C = self.C
        if tail:
            return me.energy
        base = self.ledger.mode_bid() + C["OFFSET"]
        base += self.rng.uniform(-C["JITTER"], C["JITTER"])
        base = max(C["PROBE_LO"], min(base, me.energy - C["RESERVE"]))
        return max(60, base)

    def _vulture_prey(self, me, foes, init_e):
        C = self.C
        best, best_d = None, 1e18
        for f in foes:
            e = self.ledger.energy_of(f, init_e)
            need = e + C["VULTURE_MARGIN"]
            if need <= me.energy - (0 if me.fruit <= C["DANGER"] else C["RESERVE"] * 0.4):
                d = self._d2(me, f)
                if d < best_d:
                    best, best_d = f, d
        return best

    def _nearest(self, me, foes):
        return min(foes, key=lambda f: self._d2(me, f))

    def _weakest(self, foes, init_e):
        return min(foes, key=lambda f: self.ledger.energy_of(f, init_e))

    @staticmethod
    def _d2(a, b):
        return (a.x - b.x) ** 2 + (a.y - b.y) ** 2

    # ================= 走位 =================
    def _steer(self, obs, me, foes, target):
        C = self.C
        # EVADE / 无目标 -> 逃逸采样
        if self.mode == "EVADE":
            holder = next((f for f in foes if f.has_heart), None)
            return self._flee(obs, me, foes, threat=holder)
        if target is None:
            return self._flee(obs, me, foes, threat=None)
        # 特殊目标
        if isinstance(target, tuple) and target[0] == "HEART":
            return self._goto(obs, me, target[1], target[2])
        if isinstance(target, tuple) and target[0] == "OBSTACLE":
            o = min(obs.obstacles, key=lambda o: (o.x - me.x) ** 2 + (o.y - me.y) ** 2)
            return (o.x - me.x, o.y - me.y)      # 故意蹭：唯一豁免避障否决
        # 拦截：瞄预测位置
        lead = min(1.2, math.sqrt(self._d2(me, target)) / 12.0)
        px, py = target.x + target.vx * lead, target.y + target.vy * lead
        return self._goto(obs, me, px, py, avoid_cluster=(self.mode == "FARM"))

    def _goto(self, obs, me, px, py, avoid_cluster=False):
        """朝 (px,py)，但候选方向先过避障硬否决；被否决则绕行。"""
        C = self.C
        dx, dy = px - me.x, py - me.y
        base = math.atan2(dy, dx)
        # 依次尝试：直行、±22.5°、±45°、±67.5°、±90°
        for off in (0, 0.4, -0.4, 0.8, -0.8, 1.2, -1.2, 1.6, -1.6):
            a = base + off
            vx, vy = math.cos(a), math.sin(a)
            if self._blocked(obs, me, vx, vy):
                continue
            if avoid_cluster and self._into_cluster(obs, me, vx, vy):
                continue
            return vx, vy
        return self._flee(obs, me, [f for f in obs.foes if f.alive], None)

    def _blocked(self, obs, me, vx, vy):
        """刹车距离内会撞障碍/出界 -> 硬否决。"""
        C = self.C
        look = 12.0 * C["BRAKE_T"] + 2.0
        px, py = me.x + vx * look, me.y + vy * look
        r = 2.0 * C["OB_MARGIN"]
        for o in obs.obstacles:
            # 点到线段距离
            if _seg_dist(me.x, me.y, px, py, o.x, o.y) < o.r + r:
                return True
        m = 2.5
        if not (m < px < obs.arena_w - m and m < py < obs.arena_h - m):
            return True
        return False

    def _into_cluster(self, obs, me, vx, vy):
        C = self.C
        foes = [f for f in obs.foes if f.alive]
        if len(foes) < 2:
            return False
        px, py = me.x + vx * 8, me.y + vy * 8
        near = sum(1 for f in foes
                   if (f.x - px) ** 2 + (f.y - py) ** 2 < C["CLUSTER_R"] ** 2)
        return near >= 2

    def _flee(self, obs, me, foes, threat):
        """方向采样打分：远离威胁 + 不进障碍 + 不贴边 + 轻微向心。"""
        C = self.C
        best, best_s = (0.0, 0.0), -1e18
        for k in range(C["FLEE_DIRS"]):
            a = 2 * math.pi * k / C["FLEE_DIRS"]
            vx, vy = math.cos(a), math.sin(a)
            if self._blocked(obs, me, vx, vy):
                continue
            px, py = me.x + vx * 10, me.y + vy * 10
            s = 0.0
            if threat is not None:
                s += math.hypot(px - threat.x, py - threat.y) * 3.0
            else:
                for f in foes:
                    s += math.hypot(px - f.x, py - f.y)
            s -= 0.35 * math.hypot(px - obs.arena_w / 2, py - obs.arena_h / 2)
            if s > best_s:
                best, best_s = (vx, vy), s
        return best


def _seg_dist(x1, y1, x2, y2, px, py):
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 < 1e-9:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
