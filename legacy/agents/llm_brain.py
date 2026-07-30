# -*- coding: utf-8 -*-
"""
形态 B/C：LLM 运行时 Agent（LLMBrainAgent）
============================================
架构原则（三层兜底，永不裸奔）：
  LLM 高层决策（每 interval 秒一次，慢）
    -> 代码走位执行层（每 tick 一次，快，复用 FireflyAgent 全部走位能力）
      -> LLM 超时/解析失败/输出非法 -> 整体退化为纯状态机 FireflyAgent

LLM 只回答三个离散问题（mode / target_id / attack_power），
所有算术（清仓时机、必胜价、避障）都在代码里预先算好塞进 prompt。
绝不让 LLM 现场做数学或自由发挥。

现场接入：实现 call_llm()（官方给什么 SDK 就填什么），其余不动。
"""
import json
import math
import time
from sim.views import Observation, Action
from .statemachine import FireflyAgent

SYSTEM_PROMPT = """你是"萤火森林"对战 Agent 的战术大脑。你只做高层决策，走位由底层代码执行。
规则要点：碰撞时攻击力高者+1果实、低者-1、平局双方只耗能；能量每30秒回满1000（窗口结束时剩余能量作废）；撞障碍-1；30秒无碰撞-3；森林之心持有者10秒内碰撞0耗能且必胜；果实0出局。

决策表（严格按顺序匹配第一条命中的规则）：
1. 我持有森林之心 -> mode=RAMPAGE, target=最近对手, power=1
2. 敌方持有森林之心 -> mode=EVADE, power=最低试探价
3. 场上有心且我明显最近 -> mode=RACE
4. 我的果实<=3 -> mode=SURVIVE（只打 prompt 中标注 sure_kill=true 的目标）
5. 窗口剩余<=表中 allin_tail 秒 -> mode=FARM, target=能量最低对手, power=我的全部能量
6. 存在 sure_kill=true 的目标 -> mode=FARM, 打它, power=其 kill_price
7. 距上次碰撞>24秒 -> mode=CLOCK_RESET, target=最近对手, power=常规价
8. 其他 -> mode=FARM, target=最近对手, power=常规价（表中 suggested_bid）

只输出一个 JSON 对象，无任何其他文字：
{"mode":"...","target_id":<int或-1>,"attack_power":<int>}"""


def compact_state(obs: Observation, agent: "LLMBrainAgent") -> str:
    """把观测压缩成 LLM 友好的紧凑 JSON，预先算好一切数值。"""
    C = agent.C
    w = obs.window
    into = obs.t % w
    foes = []
    for f in obs.foes:
        if not f.alive:
            continue
        e = agent.ledger.energy_of(f) if agent.ledger else None
        kill_price = None
        sure = False
        if e is not None:
            kill_price = int(e + C["VULTURE_MARGIN"])
            sure = kill_price <= obs.me.energy - 50
        foes.append(dict(
            id=f.id, fruit=f.fruit,
            dist=round(math.hypot(f.x - obs.me.x, f.y - obs.me.y), 1),
            est_energy=int(e) if e is not None else None,
            sure_kill=sure, kill_price=kill_price,
            has_heart=f.has_heart))
    return json.dumps(dict(
        t=round(obs.t, 1),
        window_remaining=round(w - into, 1),
        allin_tail=C["ALLIN_TAIL"],
        me=dict(fruit=obs.me.fruit, energy=obs.me.energy,
                has_heart=obs.me.has_heart,
                idle_seconds=round(obs.t - obs.my_last_touch_t, 1)),
        foes=foes,
        heart_on_field=obs.heart.on_field,
        suggested_bid=int(agent.ledger.mode_bid() + C["OFFSET"]) if agent.ledger else 200,
        probe_lo=C["PROBE_LO"],
    ), ensure_ascii=False)


class LLMBrainAgent(FireflyAgent):
    """LLM 决定 mode/target/power；走位、避障、紧急制动全部继承代码实现。"""

    def __init__(self, call_llm=None, interval=2.0, timeout=1.5, **kw):
        super().__init__(**kw)
        self.name = kw.get("name", "llm-brain")
        self.call_llm = call_llm            # fn(system, user) -> str
        self.interval = interval            # LLM 决策周期（秒）
        self.timeout = timeout              # 超时预算（秒）
        self._last_llm_t = -1e9
        self._intent = None                 # 缓存的高层意图

    # 覆盖计划层：优先用 LLM 意图，失败退化为父类状态机
    def _plan(self, obs, me, foes):
        if self.call_llm is not None and obs.t - self._last_llm_t >= self.interval:
            self._last_llm_t = obs.t
            intent = self._ask_llm(obs)
            if intent is not None:
                self._intent = (intent, obs.t)
        if self._intent is not None:
            intent, t0 = self._intent
            if obs.t - t0 < self.interval * 2:      # 意图未过期
                plan = self._execute_intent(intent, obs, me, foes)
                if plan is not None:
                    return plan
        return super()._plan(obs, me, foes)         # 兜底：纯状态机

    def _ask_llm(self, obs):
        try:
            t0 = time.time()
            raw = self.call_llm(SYSTEM_PROMPT, compact_state(obs, self))
            if time.time() - t0 > self.timeout:
                return None                          # 超时弃用
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").lstrip("json").strip()
            d = json.loads(raw)
            mode = str(d.get("mode", "")).upper()
            tid = int(d.get("target_id", -1))
            power = int(d.get("attack_power", 150))
            if mode not in ("RAMPAGE", "EVADE", "RACE", "SURVIVE",
                            "FARM", "CLOCK_RESET", "PROTECT"):
                return None
            return dict(mode=mode, target_id=tid,
                        power=max(0, min(power, 1000)))
        except Exception:
            return None

    def _execute_intent(self, intent, obs, me, foes):
        self.mode = intent["mode"]
        if self.mode == "EVADE":
            return None, intent["power"]
        tgt = next((f for f in foes if f.id == intent["target_id"]), None)
        if self.mode == "RACE" and obs.heart.on_field:
            return ("HEART", obs.heart.x, obs.heart.y), intent["power"]
        if tgt is None:
            return None                              # 目标非法 -> 交回状态机
        return tgt, intent["power"]


# ---------------- 本地测试用 MockLLM（离线模拟 LLM 行为与延迟） ----------------

class MockLLM:
    """规则版'假LLM'：按决策表回答，可注入延迟/故障率来测兜底链路。"""

    def __init__(self, fail_rate=0.0, latency=0.0):
        import random
        self.rng = random.Random(9)
        self.fail_rate = fail_rate
        self.latency = latency

    def __call__(self, system, user):
        if self.latency:
            time.sleep(self.latency)
        if self.rng.random() < self.fail_rate:
            return "呃，让我想想……"                  # 非法输出，触发兜底
        s = json.loads(user)
        me, foes = s["me"], s["foes"]
        if not foes:
            return json.dumps(dict(mode="FARM", target_id=-1, attack_power=100))
        nearest = min(foes, key=lambda f: f["dist"])
        if me["has_heart"]:
            return json.dumps(dict(mode="RAMPAGE", target_id=nearest["id"], attack_power=1))
        if any(f["has_heart"] for f in foes):
            return json.dumps(dict(mode="EVADE", target_id=-1, attack_power=s["probe_lo"]))
        if s["window_remaining"] <= s["allin_tail"]:
            weakest = min(foes, key=lambda f: f["est_energy"] or 1000)
            return json.dumps(dict(mode="FARM", target_id=weakest["id"],
                                   attack_power=me["energy"]))
        sure = [f for f in foes if f.get("sure_kill")]
        if sure:
            f = min(sure, key=lambda f: f["dist"])
            return json.dumps(dict(mode="FARM", target_id=f["id"],
                                   attack_power=f["kill_price"]))
        return json.dumps(dict(mode="FARM", target_id=nearest["id"],
                               attack_power=s["suggested_bid"]))


# ---------------- 现场接入示例（比赛日按官方 SDK 改这里） ----------------

ANTHROPIC_EXAMPLE = '''
# 若平台允许自带 LLM 调用（示例：Anthropic Messages API），实现 call_llm 如下：
import anthropic
client = anthropic.Anthropic()          # 按官方给的 key/endpoint 配置

def call_llm(system, user):
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",   # 实时对战选最快的模型
        max_tokens=100,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0,                        # 确定性 > 创造性
    )
    return msg.content[0].text

agent = LLMBrainAgent(call_llm=call_llm, interval=2.0, timeout=1.5)
'''
