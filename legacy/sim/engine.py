# -*- coding: utf-8 -*-
"""
萤火森林模拟器引擎
==================
规则复刻清单（对照官方文档）：
  [x] 180 秒 / 初始能量 1000 / 初始果实 10
  [x] 攻击力由策略设定，碰撞时 1:1 扣能量（clamp 到当前能量）
  [x] 精灵碰撞：高攻 +1 / 低攻 -1 / 平局不变分但都耗能
  [x] 三只及以上碰撞：汽车追尾原则，两两判定
  [x] 每 30 秒全场能量统一回满 1000
  [x] 障碍物碰撞 -1 分（神石/藤蔓/树根 -> 不同半径的圆）
  [x] 森林之心：10 秒内碰撞不扣能量、必得果实；被撞影响轨迹
  [x] 30 秒无任何碰撞 -3 分
  [x] 果实为 0 判定失败
规则未明说的点 -> SimConfig 开关（默认取保守值），现场确认后一键切换。
"""
import math
import random
from dataclasses import dataclass, field

from .views import (Observation, Action, SpiritView, ObstacleView,
                    HeartView, CollisionEvent)


@dataclass
class SimConfig:
    # --- 官方明确的规则 ---
    match_len: float = 180.0
    window: float = 30.0
    init_energy: int = 1000
    init_fruit: int = 10
    idle_penalty: int = 3
    obstacle_penalty: int = 1
    heart_duration: float = 10.0

    # --- 物理参数（现场需标定；策略层不依赖具体数值） ---
    arena_w: float = 100.0
    arena_h: float = 100.0
    tick: float = 0.1
    spirit_r: float = 2.0
    v_max: float = 12.0
    accel: float = 40.0                 # 速度趋近的最大加速度
    pair_cooldown: float = 0.8          # 同一对碰撞的再判定冷却
    obstacle_cooldown: float = 0.8
    n_obstacles: int = 6

    # --- 未明说项开关（默认保守） ---
    energy_visible: bool = False        # 对手能量是否可见
    events_visible: bool = True         # 是否提供碰撞事件流（含出价）
    bids_visible: bool = False          # 事件里是否露出双方出价
    passive_resets_timer: bool = True   # 被动被撞是否重置 30s 计时
    obstacle_resets_timer: bool = True  # 撞障碍是否重置 30s 计时（官方"也不与障碍物碰撞"暗示是）
    eliminate_at_zero: bool = True      # 果实 0 是否移出场
    heart_holder_obstacle_free: bool = False  # 心持有者撞障碍是否免扣分（保守：不免）
    heart_first_spawn: tuple = (15.0, 35.0)
    heart_respawn_gap: tuple = (15.0, 30.0)
    decision_interval: float = 0.1      # 策略决策频率（LLM 形态调大，如 2.0）

    seed: int = 0


class Spirit:
    def __init__(self, sid, x, y, cfg: SimConfig):
        self.id = sid
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.energy = cfg.init_energy
        self.fruit = cfg.init_fruit
        self.attack = 100
        self.alive = True
        self.last_touch = 0.0
        self.heart_until = -1.0
        self.death_t = 1e9   # 出局时间（活到最后=1e9）
        self.action = Action()

    def has_heart(self, t):
        return t < self.heart_until


class Engine:
    def __init__(self, agents, cfg: SimConfig = None):
        """agents: list of objects with .act(Observation) -> Action"""
        self.cfg = cfg or SimConfig()
        self.rng = random.Random(self.cfg.seed)
        self.agents = agents
        n = len(agents)
        c = self.cfg
        self.spirits = []
        # 出生点：四角内缩，避免开局即撞
        corners = [(0.2, 0.2), (0.8, 0.2), (0.2, 0.8), (0.8, 0.8),
                   (0.5, 0.15), (0.5, 0.85), (0.15, 0.5), (0.85, 0.5)]
        for i in range(n):
            fx, fy = corners[i % len(corners)]
            self.spirits.append(Spirit(i, fx * c.arena_w, fy * c.arena_h, c))
        self.obstacles = self._gen_obstacles()
        self.t = 0.0
        self.heart_pos = None
        self.heart_next_spawn = self.rng.uniform(*c.heart_first_spawn)
        self.pair_cd = {}
        self.obs_cd = {}
        self.events_buf = {i: [] for i in range(n)}
        self.log = []
        self.last_decision = {i: -1e9 for i in range(n)}
        self.stats = {i: dict(wins=0, losses=0, draws=0, obst=0, idle=0,
                              hearts=0, heart_wins=0) for i in range(n)}

    # ---------- 场景生成 ----------
    def _gen_obstacles(self):
        c = self.cfg
        obs, tries = [], 0
        radii = [3.0, 3.5, 2.5, 4.0, 3.0, 2.8, 3.2, 3.6]
        while len(obs) < c.n_obstacles and tries < 500:
            tries += 1
            r = radii[len(obs) % len(radii)]
            x = self.rng.uniform(0.18, 0.82) * c.arena_w
            y = self.rng.uniform(0.18, 0.82) * c.arena_h
            if all((x - o.x) ** 2 + (y - o.y) ** 2 > (r + o.r + 8) ** 2 for o in obs):
                # 别堵出生点
                if min((x - s.x) ** 2 + (y - s.y) ** 2 for s in self.spirits) > 15 ** 2:
                    obs.append(ObstacleView(x, y, r))
        return obs

    # ---------- 观测构造 ----------
    def _view_of(self, s: Spirit, viewer_is_self: bool):
        c = self.cfg
        return SpiritView(
            id=s.id, x=s.x, y=s.y, vx=s.vx, vy=s.vy, fruit=s.fruit,
            energy=s.energy if (viewer_is_self or c.energy_visible) else None,
            has_heart=s.has_heart(self.t), alive=s.alive)

    def _observe(self, i):
        c = self.cfg
        me = self.spirits[i]
        heart = HeartView()
        if self.heart_pos is not None:
            heart.on_field = True
            heart.x, heart.y = self.heart_pos
        for s in self.spirits:
            if s.alive and s.has_heart(self.t):
                heart.holder_id = s.id
                heart.holder_until = s.heart_until
        ev = self.events_buf[i] if c.events_visible else []
        self.events_buf[i] = []
        return Observation(
            t=self.t, dt=self.t - max(self.last_decision[i], 0.0),
            me=self._view_of(me, True),
            foes=[self._view_of(s, False) for s in self.spirits if s.id != i],
            obstacles=list(self.obstacles), heart=heart, events=ev,
            arena_w=c.arena_w, arena_h=c.arena_h, window=c.window,
            match_len=c.match_len, my_last_touch_t=me.last_touch)

    # ---------- 主循环 ----------
    def run(self, verbose=False):
        c = self.cfg
        steps = int(c.match_len / c.tick)
        next_reset = c.window
        for _ in range(steps):
            self.t = round(self.t + c.tick, 6)
            # 1) 决策（按各自频率）
            for s in self.spirits:
                if not s.alive:
                    continue
                if self.t - self.last_decision[s.id] >= c.decision_interval - 1e-9:
                    try:
                        s.action = self.agents[s.id].act(self._observe(s.id))
                    except Exception as e:  # 策略崩溃 -> 保持上一动作（模拟真实风险）
                        self._log("CRASH", s.id, str(e)[:80])
                    self.last_decision[s.id] = self.t
                s.attack = max(0, min(int(s.action.attack_power), s.energy))
            # 2) 移动
            self._move_all()
            # 3) 精灵-精灵碰撞（两两判定 = 汽车追尾原则）
            self._spirit_collisions()
            # 4) 障碍碰撞
            self._obstacle_collisions()
            # 5) 森林之心 拾取/刷新
            self._heart_tick()
            # 6) 30 秒统一回能
            if self.t >= next_reset - 1e-9:
                for s in self.spirits:
                    if s.alive:
                        s.energy = c.init_energy
                self._log("ENERGY_RESET")
                next_reset += c.window
            # 7) 超时 -3
            self._idle_check()
            # 8) 出局
            for s in self.spirits:
                if s.alive and s.fruit <= 0:
                    s.fruit = 0
                    if c.eliminate_at_zero:
                        s.alive = False
                        s.death_t = self.t
                        self._log("ELIMINATED", s.id)
        return self.result()

    # ---------- 物理 ----------
    def _move_all(self):
        c = self.cfg
        for s in self.spirits:
            if not s.alive:
                continue
            mx, my = s.action.move_x, s.action.move_y
            m = math.hypot(mx, my)
            tx, ty = (0.0, 0.0) if m < 1e-9 else (mx / m * c.v_max, my / m * c.v_max)
            dvx, dvy = tx - s.vx, ty - s.vy
            dv = math.hypot(dvx, dvy)
            cap = c.accel * c.tick
            if dv > cap:
                dvx, dvy = dvx / dv * cap, dvy / dv * cap
            s.vx += dvx
            s.vy += dvy
            s.x += s.vx * c.tick
            s.y += s.vy * c.tick
            # 边界反弹
            r = c.spirit_r
            if s.x < r:
                s.x, s.vx = r, abs(s.vx)
            if s.x > c.arena_w - r:
                s.x, s.vx = c.arena_w - r, -abs(s.vx)
            if s.y < r:
                s.y, s.vy = r, abs(s.vy)
            if s.y > c.arena_h - r:
                s.y, s.vy = c.arena_h - r, -abs(s.vy)

    def _spirit_collisions(self):
        c = self.cfg
        alive = [s for s in self.spirits if s.alive]
        for i in range(len(alive)):
            for j in range(i + 1, len(alive)):
                a, b = alive[i], alive[j]
                d = math.hypot(a.x - b.x, a.y - b.y)
                if d > 2 * c.spirit_r:
                    continue
                key = (min(a.id, b.id), max(a.id, b.id))
                if self.t - self.pair_cd.get(key, -9) < c.pair_cooldown:
                    self._separate(a, b, d)
                    continue
                self.pair_cd[key] = self.t
                self._resolve(a, b)
                self._bounce(a, b, d)

    def _resolve(self, a: Spirit, b: Spirit):
        c = self.cfg
        ah, bh = a.has_heart(self.t), b.has_heart(self.t)
        bid_a = 0 if ah else min(a.attack, a.energy)
        bid_b = 0 if bh else min(b.attack, b.energy)
        if not ah:
            a.energy -= bid_a
        if not bh:
            b.energy -= bid_b
        # 胜负：心持有者必胜；双持心 -> 平
        if ah and not bh:
            winner, loser = a, b
        elif bh and not ah:
            winner, loser = b, a
        elif bid_a > bid_b:
            winner, loser = a, b
        elif bid_b > bid_a:
            winner, loser = b, a
        else:
            winner = loser = None
        if winner is not None:
            winner.fruit += 1
            loser.fruit -= 1
            self.stats[winner.id]["wins"] += 1
            self.stats[loser.id]["losses"] += 1
            if winner.has_heart(self.t):
                self.stats[winner.id]["heart_wins"] += 1
        else:
            self.stats[a.id]["draws"] += 1
            self.stats[b.id]["draws"] += 1
        # 互动计时
        a.last_touch = self.t
        if c.passive_resets_timer:
            b.last_touch = self.t
        else:
            # 主动性无法在物理上区分，这里双方都算主动参与
            b.last_touch = self.t
        ev = CollisionEvent(
            t=self.t, kind="spirit", a_id=a.id, b_id=b.id,
            winner_id=(winner.id if winner else -2),
            a_bid=bid_a if c.bids_visible else None,
            b_bid=bid_b if c.bids_visible else None)
        for buf in self.events_buf.values():
            buf.append(ev)
        self._log("HIT", a.id, b.id, bid_a, bid_b,
                  winner.id if winner else "draw")

    def _bounce(self, a, b, d):
        # 弹性交换法线分量 + 位置分离（心持有者"被撞影响轨迹"由此体现）
        if d < 1e-6:
            d = 1e-6
        nx, ny = (b.x - a.x) / d, (b.y - a.y) / d
        va = a.vx * nx + a.vy * ny
        vb = b.vx * nx + b.vy * ny
        a.vx += (vb - va) * nx
        a.vy += (vb - va) * ny
        b.vx += (va - vb) * nx
        b.vy += (va - vb) * ny
        # 追加分离冲量：真实对局中碰撞后应明显弹开，避免贴身连环碰
        kick = 6.0
        a.vx -= nx * kick
        a.vy -= ny * kick
        b.vx += nx * kick
        b.vy += ny * kick
        self._separate(a, b, d)

    def _separate(self, a, b, d):
        c = self.cfg
        overlap = 2 * c.spirit_r - d
        if overlap <= 0:
            return
        if d < 1e-6:
            nx, ny = 1.0, 0.0
        else:
            nx, ny = (b.x - a.x) / d, (b.y - a.y) / d
        a.x -= nx * overlap / 2
        a.y -= ny * overlap / 2
        b.x += nx * overlap / 2
        b.y += ny * overlap / 2

    def _obstacle_collisions(self):
        c = self.cfg
        for s in self.spirits:
            if not s.alive:
                continue
            for k, o in enumerate(self.obstacles):
                d = math.hypot(s.x - o.x, s.y - o.y)
                if d > c.spirit_r + o.r:
                    continue
                key = (s.id, k)
                if self.t - self.obs_cd.get(key, -9) >= c.obstacle_cooldown:
                    self.obs_cd[key] = self.t
                    if not (s.has_heart(self.t) and c.heart_holder_obstacle_free):
                        s.fruit -= c.obstacle_penalty
                        self.stats[s.id]["obst"] += 1
                    if c.obstacle_resets_timer:
                        s.last_touch = self.t
                    ev = CollisionEvent(t=self.t, kind="obstacle", a_id=s.id)
                    for buf in self.events_buf.values():
                        buf.append(ev)
                    self._log("OBST", s.id)
                # 反弹推出
                if d < 1e-6:
                    d = 1e-6
                nx, ny = (s.x - o.x) / d, (s.y - o.y) / d
                s.x = o.x + nx * (c.spirit_r + o.r + 0.05)
                s.y = o.y + ny * (c.spirit_r + o.r + 0.05)
                vn = s.vx * nx + s.vy * ny
                if vn < 0:
                    s.vx -= 2 * vn * nx
                    s.vy -= 2 * vn * ny

    def _heart_tick(self):
        c = self.cfg
        holder = any(s.alive and s.has_heart(self.t) for s in self.spirits)
        if self.heart_pos is None and not holder and self.t >= self.heart_next_spawn:
            for _ in range(50):
                x = self.rng.uniform(0.15, 0.85) * c.arena_w
                y = self.rng.uniform(0.15, 0.85) * c.arena_h
                if all(math.hypot(x - o.x, y - o.y) > o.r + 5 for o in self.obstacles):
                    self.heart_pos = (x, y)
                    self._log("HEART_SPAWN", round(x, 1), round(y, 1))
                    break
        if self.heart_pos is not None:
            hx, hy = self.heart_pos
            grab = [s for s in self.spirits if s.alive and
                    math.hypot(s.x - hx, s.y - hy) < c.spirit_r + 1.5]
            if grab:
                g = min(grab, key=lambda s: math.hypot(s.x - hx, s.y - hy))
                g.heart_until = self.t + c.heart_duration
                self.stats[g.id]["hearts"] += 1
                self.heart_pos = None
                self.heart_next_spawn = self.t + c.heart_duration + \
                    self.rng.uniform(*c.heart_respawn_gap)
                self._log("HEART_TAKEN", g.id)

    def _idle_check(self):
        c = self.cfg
        for s in self.spirits:
            if s.alive and self.t - s.last_touch >= c.window - 1e-9:
                s.fruit -= c.idle_penalty
                s.last_touch = self.t
                self.stats[s.id]["idle"] += 1
                self._log("IDLE-3", s.id)

    # ---------- 输出 ----------
    def _log(self, *args):
        self.log.append((round(self.t, 1),) + args)

    def result(self):
        # 排名：活着 > 果实多 > 活得久（多人出局按存活时长定序，对应'生存大师'逻辑）
        order = sorted(self.spirits,
                       key=lambda s: (s.alive, s.fruit, s.death_t),
                       reverse=True)
        return {
            "fruits": {s.id: s.fruit for s in self.spirits},
            "alive": {s.id: s.alive for s in self.spirits},
            "ranking": [s.id for s in order],
            "stats": self.stats,
        }
