# 比赛日接入指南（目标：官方环境公布后 15 分钟内跑起第一版）

## 第 0 步：判断形态（前 3 分钟，看官方模板代码）
| 看到什么 | 形态 | 用哪套 |
|---|---|---|
| 让你填一个 Python/JS 策略函数（输入状态、输出动作） | A：代码 Bot | `agents/statemachine.py` 全量搬入 |
| 让你写 prompt / 自然语言策略 | B：Prompt 即 Agent | `prompts/battle_prompt.md` 直接粘贴 |
| 给你 LLM 调用配额 + 代码框架 | C：混合 | `agents/llm_brain.py`，填 `call_llm()` |

## 第 1 步：写适配层（10 分钟，只写两个函数）
策略层零改动。只需把官方接口翻译成我们的协议：

```python
# ===== 官方状态 -> Observation =====
def parse(official_state) -> Observation:
    # 必填：t, me(x,y,vx,vy,fruit,energy), foes[], obstacles[], heart
    # 拿不到的字段（如对手 energy）填 None —— 策略层已兼容
    # 没有速度就用 (本帧位置-上帧位置)/dt 自己差分
    ...

# ===== Action -> 官方指令 =====
def emit(action: Action):
    # move_x/move_y 是"期望方向"，官方要目标点就输出 me.pos + move*10
    # 官方要角度就输出 atan2(move_y, move_x)
    ...

# ===== 官方主循环里 =====
agent = SafeAgent(make("balanced"))     # 永远套 SafeAgent
def on_tick(official_state):
    return emit(agent.act(parse(official_state)))
```

## 第 2 步：开赛 15 分钟侦察清单（答案写进 SimConfig 同步校准模拟器）
逐条确认，打勾：
- [ ] 对手**能量/分数**是否可见？ -> `energy_visible`
- [ ] 有无**碰撞事件流**？含不含出价？ -> `events_visible` / `bids_visible`
- [ ] 攻击力**何时可改**（每 tick / 仅碰撞前）？能否为 0？上限是否=当前能量？
- [ ] 决策**超时的默认行为**？（静止？沿用上次？——决定 SafeAgent 兜底动作）
- [ ] **被动被撞**算不算有效互动（重置 30 秒计时）？ -> `passive_resets_timer`
- [ ] **撞障碍**算不算有效互动？ -> `obstacle_resets_timer`
- [ ] 果实为 0 是**移出场**还是原地躺尸？ -> `eliminate_at_zero`
- [ ] 心持有者**撞障碍**扣不扣分？双方**都持心**怎么判？
- [ ] 场地尺寸 / 精灵速度 / 碰撞半径 —— 目测标定，改 `arena_w/v_max/spirit_r`
- [ ] **一个 30 秒窗口物理上最多撞几次 N** -> 常规出价校准为 ~1000/N + OFFSET

## 第 3 步：练习赛 Loop 协议（按此顺序合入，每合一步跑一次榜单）
1. 笨版本先上线：会动 + 不撞障碍 + 固定价 200（能跑的笨蛋碾压跑不动的天才）
2. 合入零漏分走位（避障否决 + 紧急制动）
3. 合入窗口尾 all-in（模拟器已证明 ALLIN_TAIL=9 附近最优）
4. 合入目标选择（补刀 / 最弱者优先）
5. 合入森林之心攻防（RAMPAGE / EVADE / RACE）
6. 合入对手记账 + 秃鹫（能量可见时威力最大）
7. 放一局 FixedProbe(200) 探针局，测全桌出价分布，回来改 PROBE_LO/OFFSET

## 战术切换口诀
- 晋级局：`make("balanced")` 或 `make("vulture")`（求稳进前 2）
- 决赛：`make("aggro")`（争第一）
- 桌上全是狠人互殴：`make("turtle")`（模拟器实测高手局晋级率最高 75%）
- **赛中只改 CFG 参数，绝不动架构。**

## 五大翻车点（贴在屏幕边上）
1. 忘套 SafeAgent -> 崩溃 -> AFK -3 螺旋
2. 追击上头蹭障碍（已有硬否决，别手动关）
3. 只写了能量可见分支（本框架两条路都通，别自己改死）
4. 对练习赛 meta 过拟合（正式赛有人藏招，留 balanced 兜底）
5. 忘了窗口尾 all-in 是免费的（数据已证明这是第一大分源之一）
