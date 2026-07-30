# -*- coding: utf-8 -*-
"""
适配层协议（Adapter Protocol）
=============================
核心思想：策略代码永远只认识这两个结构 —— Observation 进，Action 出。
比赛日拿到官方接口后，只需写一个 parse() 把官方状态翻译成 Observation，
一个 emit() 把 Action 翻译成官方指令。策略层一行不用改。

不确定项全部做成"可见性开关"，两种情况都能测（见 engine.SimConfig）。
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SpiritView:
    """一只精灵的可观测状态。"""
    id: int
    x: float
    y: float
    vx: float
    vy: float
    fruit: int                      # 发光果实（分数）
    energy: Optional[int] = None    # 对手能量可能不可见 -> None
    has_heart: bool = False         # 是否持有森林之心
    alive: bool = True


@dataclass
class ObstacleView:
    x: float
    y: float
    r: float


@dataclass
class HeartView:
    on_field: bool = False          # 场上是否有未拾取的心
    x: float = 0.0
    y: float = 0.0
    holder_id: Optional[int] = None # 被谁持有（None=无人）
    holder_until: float = 0.0       # 持有到期时间（若可见）


@dataclass
class CollisionEvent:
    """碰撞事件（若平台提供事件流；不提供则 events=[] ，策略需自行推断）。"""
    t: float
    kind: str                       # "spirit" | "obstacle"
    a_id: int
    b_id: int = -1                  # 障碍碰撞时为 -1
    winner_id: int = -2             # -2=平局/不适用
    a_bid: Optional[int] = None     # 出价若不可见则 None
    b_bid: Optional[int] = None


@dataclass
class Observation:
    t: float                        # 当前时间（秒）
    dt: float                       # 距上次决策的间隔
    me: SpiritView
    foes: list                      # list[SpiritView]（含已出局，alive=False）
    obstacles: list                 # list[ObstacleView]
    heart: HeartView
    events: list = field(default_factory=list)   # 自上次决策以来的事件
    arena_w: float = 100.0
    arena_h: float = 100.0
    window: float = 30.0            # 能量重置周期
    match_len: float = 180.0
    my_last_touch_t: float = 0.0    # 我上次有效互动的时间（用于防 -3）


@dataclass
class Action:
    """策略输出：期望移动方向（会被引擎归一化并限速）+ 当前攻击力设定。"""
    move_x: float = 0.0
    move_y: float = 0.0
    attack_power: int = 100
