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
- 碰撞事件通过能量、分数和回弹状态推断，真实训练后需要校准。
- 对手模型当前只保存在进程内，重启后不会恢复。
- `on_game_end` 必须快速且非阻塞；赛间 LLM 优化器尚未接入。
- 当前参数是官方规则先验，必须用自由赛数据继续调整。

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
3. 增加真实比赛复盘指标与持久化对手画像。
4. 在自由赛 `readyForNextMatch` 前增加有超时和回滚保护的赛间优化流程。
