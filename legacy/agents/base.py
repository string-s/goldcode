# -*- coding: utf-8 -*-
"""Agent 基类 + SafeAgent 包装（策略异常时兜底，绝不让引擎收到裸异常）。"""
import math
import random
from sim.views import Observation, Action


class BaseAgent:
    name = "base"

    def act(self, obs: Observation) -> Action:
        raise NotImplementedError


class SafeAgent(BaseAgent):
    """把任意 agent 包一层：异常 -> 安全游走 + 中等出价。
    比赛日务必用这个包住你的策略。AFK 螺旋(-3循环)是最蠢的死法。"""

    def __init__(self, inner: BaseAgent):
        self.inner = inner
        self.name = f"safe({inner.name})"
        self._rng = random.Random(42)
        self._wander = (1.0, 0.0)
        self._last_ok = Action(1.0, 0.0, 150)

    def act(self, obs: Observation) -> Action:
        try:
            a = self.inner.act(obs)
            assert a is not None
            self._last_ok = a
            return a
        except Exception:
            # 兜底：朝场地中心偏随机方向移动（远离边角），中等攻击力
            cx, cy = obs.arena_w / 2 - obs.me.x, obs.arena_h / 2 - obs.me.y
            jx, jy = self._rng.uniform(-1, 1), self._rng.uniform(-1, 1)
            return Action(cx * 0.02 + jx, cy * 0.02 + jy, 150)


# ---------------- 陪练基线（用来测主力，也是"对手画像"样本） ----------------

class RandomAgent(BaseAgent):
    """无脑随机：低水平队伍画像。"""
    name = "random"

    def __init__(self, seed=1):
        self.rng = random.Random(seed)
        self.dir = (1, 0)
        self.next_turn = 0

    def act(self, obs):
        if obs.t >= self.next_turn:
            ang = self.rng.uniform(0, 2 * math.pi)
            self.dir = (math.cos(ang), math.sin(ang))
            self.next_turn = obs.t + self.rng.uniform(1, 3)
        return Action(self.dir[0], self.dir[1], self.rng.choice([100, 200, 300]))


class ChaserAgent(BaseAgent):
    """无脑追最近对手 + 固定高价：激进队画像。"""
    name = "chaser"

    def __init__(self, power=300):
        self.power = power

    def act(self, obs):
        foes = [f for f in obs.foes if f.alive]
        if not foes:
            return Action(0, 0, self.power)
        tgt = min(foes, key=lambda f: (f.x - obs.me.x) ** 2 + (f.y - obs.me.y) ** 2)
        return Action(tgt.x - obs.me.x, tgt.y - obs.me.y, self.power)


class TurtleAgent(BaseAgent):
    """龟缩流：躲所有人，只在快吃 -3 时找人轻碰一下。"""
    name = "turtle"

    def act(self, obs):
        me = obs.me
        idle = obs.t - obs.my_last_touch_t
        foes = [f for f in obs.foes if f.alive]
        if idle > 24 and foes:  # 防 -3：主动去碰
            tgt = min(foes, key=lambda f: (f.x - me.x) ** 2 + (f.y - me.y) ** 2)
            return Action(tgt.x - me.x, tgt.y - me.y, 120)
        # 否则：远离所有人
        fx = fy = 0.0
        for f in foes:
            d2 = (f.x - me.x) ** 2 + (f.y - me.y) ** 2 + 1
            fx += (me.x - f.x) / d2
            fy += (me.y - f.y) / d2
        fx += (obs.arena_w / 2 - me.x) * 0.0005
        fy += (obs.arena_h / 2 - me.y) * 0.0005
        return Action(fx, fy, 60)


class FixedProbe(BaseAgent):
    """探针：全程固定出价，用来现场测全桌出价分布。"""
    name = "probe"

    def __init__(self, power=200):
        self.power = power
        self.name = f"probe{power}"

    def act(self, obs):
        foes = [f for f in obs.foes if f.alive]
        if not foes:
            return Action(0, 0, self.power)
        tgt = min(foes, key=lambda f: (f.x - obs.me.x) ** 2 + (f.y - obs.me.y) ** 2)
        return Action(tgt.x - obs.me.x, tgt.y - obs.me.y, self.power)
