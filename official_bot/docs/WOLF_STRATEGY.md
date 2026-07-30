# Wolf Python BOT 实现说明

本目录基于官方 `participant-bot-starter-python`，保留了认证、分桌、入房、重连、
限频、回放和数据落盘链路。在此基础上增加 Wolf 策略层。

## 运行方式

```bash
python3 -m pip install -r requirements.txt
python3 check.py
CRAZY_CRASH_ACCESS_KEY='test:你的数字工号' python3 bot.py
```

正式连接时不得设置 `COMMAND_INTERVAL_MS`，也不得修改 `bot.py` 的 100ms 限频和
5 秒心跳。

## 代码分层

```text
bot.py
  官方 Agent 外壳，增加了可选 on_game_start/on_game_end 生命周期钩子

strategy.py
  官方同步入口，只持有一个 WolfStrategy 实例

strategy_core/runtime.py
  观测、记忆、高层策略和车辆控制的编排

strategy_core/policy.py
  SAFE / RAMPAGE / EVADE / RACE / SURVIVE / PROTECT /
  CLOCK_RESET / FARM 高层模式

strategy_core/controller.py
  将目标点和期望攻击值调度成每帧唯一一条官方命令

strategy_core/memory.py
  当前攻击预设、碰撞计时、目标锁定和对手攻击投入估算

strategy_core/geometry.py
  地图多边形解析、路径碰撞检测和保守绕行点

strategy_core/navigation.py / collision.py
  车辆局部轨迹采样、动态对手避让、碰撞时间预测与接触冷却

analysis/match_report.py
  从帧、命令和结算生成结构化 JSON 与 Markdown 复盘报告

storage/profile_store.py
  在比赛边界读写 SQLite 对手画像；实时帧决策不访问磁盘
```

## 与原始策略的关系

原仓库的状态机思想被保留，但二维移动向量不再直接输出。实时链路现在是：

```text
refreshData
  -> WolfStrategy
  -> 高层 Intent(mode, target, desired_attack)
  -> 单命令控制器
  -> goForward / turnLeft / turnRight / steerBack / setAttackValue
```

对手剩余能量直接读取官方 `energy`。对手不可见的攻击预设，则根据跨帧能量下降量
维护指数移动平均；30 秒统一恢复和森林之心免能量状态不会作为普通投入样本。

## 生命周期扩展

官方 starter 的 `choose_command` 看不到只在 `startGame` 出现的地图。Wolf 对
`bot.py` 做了最小扩展：

- `startGame` 时调用 `strategy.on_game_start(start_data, context)`；
- `battle-data` 保存完成或超时后调用 `strategy.on_game_end(...)`；
- 策略 hash 同时覆盖 `strategy.py` 和 `strategy_core/*.py`。

这些扩展不修改 WebSocket、心跳、入房和指令限频行为。

## 当前边界

- 障碍绕行采用保守包围盒拐点，还不是完整导航网格。
- 轨迹规划已考虑车身半径、边界、静态多边形和非目标对手，但步长与转向模型仍需真实回放校准。
- 碰撞事件通过能量、分数和回弹状态推断，真实训练后需要校准。
- 对手攻击画像已按稳定 ID 持久化；自由赛默认更新，正式赛默认只读。
- 赛间 LLM 优化器已接入比赛边界并默认关闭；未配置 provider 时不会发起外部请求。
- 当前参数是官方规则先验，必须用自由赛数据继续调整。
- `commands.jsonl` 已记录每次决策的模式、原因、目标和攻击估计，便于真实赛后定位。

## 已确认的比赛运行方式

- 对手 ID 稳定，后续对手画像可以使用 ID 作为持久化主键。
- 自由赛允许更新代码和重启，是赛间 LLM 优化的主要阶段。
- 淘汰赛阶段不能依赖重启或热更新，策略和进程必须保持稳定。
- 进入 16 强前有约 10 分钟调整窗口，只发布已经通过测试的候选版本。
- 地图是否固定尚未确认，因此每局继续以 `startGame.data.map` 为准。

详细约束见 `COMPETITION_CONSTRAINTS.md`。

## 下一阶段

1. 使用测试 AK 收集真实地图、帧、命令和结算。
2. 根据回放校准转向阈值、碰撞准备距离和障碍余量。
3. 确认正式局分规则，并校准系列赛姿态阈值。
4. 用多场自由赛比较人工配置与 LLM 候选，验证提升后再考虑 `auto` 模式。

赛间优化流程现已实现，默认关闭。详细启用方式和安全边界见 `OPTIMIZATION.md`。

## 多局策略

每局开场会读取 `gameNo` 与 `gamesPerTable`，每局结算后累计服务端 `points`。
根据此前平均局分选择：

- `STEADY`：默认均衡风险；
- `MUST_SCORE`：降低能量底仓并提前进入窗口尾清仓；
- `PROTECT_SERIES`：已有积分优势时更早保住当前前二位置。

当前默认局分表为 `4/3/2/1`，集中在配置中；赛事方最终确认后可单点修改。
