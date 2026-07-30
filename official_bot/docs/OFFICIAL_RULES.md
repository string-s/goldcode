# 战斗规则与策略输入

这个文件只说明规则、状态和合法动作，不提供可直接获胜的算法。你的主要工作是修改 `strategy.py` 中的 `choose_command(game_state, bot_id)`。

## 胜负与资源

- 单场最长 180 秒；开局只剩一只兔子仍有胡萝卜时提前结束。
- 初始胡萝卜分 `score=10`，初始总能量 `energy=1000`，默认单次碰撞投入 `attackValue=50`。
- 普通碰撞时，双方各自的有效攻击力是 `min(自己的 attackValue, 自己的 energy)`。高者获得 1 分，低者失去 1 分；相同则不改分。双方都会消耗本次有效攻击能量。
- 同一对兔子的碰撞有 1.5 秒结算冷却：贴在一起摩擦不会连续刷分，必须真正分开后再撞。
- 撞到陨石（障碍物）扣 1 分，并重置本人的 30 秒无碰撞计时。
- 连续 30 秒没有发生有效碰撞会扣 3 分，并重新开始计时。
- 每 30 秒把仍在场兔子的 `energy` 直接恢复到 1000（不是累加）。`energy=0` 不会被淘汰。
- `score` 归零时立即淘汰，`deathCount` 加 1，并且**不会复活**。
- 当前版本没有落水机制：兔子被推到场地边缘只会被强制拉回可行驶区，不会掉下去。因此正常比赛里 `deathCount` 只有 `0`（在场）或 `1`（已被淘汰）。
- 状态中的 `goldCarrot` 是“森林之心”位置，比赛第 30/90/150 秒各出现一次。拾取后 10 秒内碰撞必胜、不消耗碰撞能量、撞陨石也不扣分。

## 单桌名次

服务端结算（`matchFinished.result.ranking` 与赛事积分）的排序是：

1. `score` 降序；
2. `deathCount` 升序（等价于“没被淘汰的排在被淘汰的前面”）；
3. BOT ID 升序，保证四人桌产生唯一的第 1～4 名。

大屏结算弹窗额外会用 `survivalTime` 做展示层的次级排序，但决定积分和晋级的是上面这三个键。

正式赛一桌可能连打多局（`gamesPerTable`），每局单独结算积分，整桌名次按累计积分汇总；默认四人桌按第 1～4 名获得 `4/3/2/1` 局分。

## `refreshData.data`

传给 `choose_command` 的 `game_state` 是一个 `dict`，每一帧主要包含：

```python
{
    "rabbits": [
        {
            "id": ..., "name": ..., "active": ...,
            "position": {"x": ..., "y": ...},
            "velocity": {"x": ..., "y": ...},
            "angle": ..., "speed": ..., "angularSpeed": ...,
            "width": ..., "height": ...,
            "moveState": ..., "dirState": ...,
            "rebounding": ..., "reboundAngle": ...,
            "attacking": ..., "invincible": ...,
            "energy": ..., "score": ..., "deathCount": ..., "survivalTime": ...,
        }
    ],
    "goldCarrot": {"x": ..., "y": ...},   # 也可能是 {} 或 None
    "elapsedSeconds": ..., "remainingTime": ...,
}
```

字段名保持服务端协议原样的小驼峰，不要改成蛇形；服务端下发什么，`dict` 的键就是什么。

字段说明：

| 字段 | 描述 |
| --- | --- |
| `id` / `name` | BOT 唯一 ID 与显示名称；身份判断只使用 `id` |
| `active` | 当前是否在场可行动；`False` 表示已被淘汰，停止输出动作 |
| `position` | 碰撞体中心坐标，单位 px；x 向右、y 向下 |
| `velocity` | 当前速度向量，可预测下一位置和接近趋势 |
| `angle` | 当前朝向弧度，约在 `[-pi, pi]`，`0` 大致向右 |
| `speed` | 瞬时速度标量，包含主动移动和碰撞回弹 |
| `angularSpeed` | 当前角速度，结合 `dirState` 判断左右转 |
| `width/height` | 当前碰撞体尺寸，可估算接触距离 |
| `moveState` | `1` 前进、`0` 停止、`-1` 后退 |
| `dirState` | `1` 右转、`0` 直行、`-1` 左转 |
| `rebounding/reboundAngle` | 是否正在回弹及回弹方向；回弹方向不等于正常朝向 |
| `attacking/invincible` | 森林之心带来的必胜/无敌状态；当前实现中两者同步 |
| `energy` | 当前剩余总能量，范围 `0～1000`，不能由 BOT 直接增加 |
| `score` | 当前胡萝卜分数；归零淘汰，排名优先看它 |
| `deathCount` | 本局被淘汰次数，`0` 或 `1`；同分时越少排名越高 |
| `survivalTime` | 本局存活秒数；淘汰后停止累计 |
| `goldCarrot` | 森林之心坐标；`{}` 或 `None` 表示当前不在场 |
| `elapsedSeconds` | 本局已进行秒数，从 `0` 开始 |
| `remainingTime` | 本局剩余秒数，从 `180` 递减；不需要自己用本地时间估算 |

请始终使用 `botConnected` 返回并传入 `choose_command` 的 `bot_id` 查找自己，不要硬编码示例 ID。完整样例见 `tests/fixtures/sample-refresh-data.json`。

## 障碍物与地图（只在 `startGame` 下发）

比赛第一帧 `startGame.data` 的结构是 `{"rabbits": ..., "map": ...}`（没有 `goldCarrot`），其中 `map` 一次性给出全场静态地形：

```python
{
    "width": 1440,
    "height": 820,
    # 水域（不可行驶区）：每个元素是一片水域，被拆成若干凸多边形
    "borders": [[[{"x": ..., "y": ...}, ...], ...], ...],
    # 陨石（场内障碍物）：每个元素是一块陨石，被拆成若干凸多边形
    "blocks": [[[{"x": ..., "y": ...}, ...], ...], ...],
}
```

字段含义：

| 字段 | 描述 |
| --- | --- |
| `width` / `height` | 画布尺寸，单位 px；可行驶区小于这个矩形 |
| `blocks` | 陨石（场内障碍物）列表；撞上扣 1 分 |
| `borders` | 水域（场地之外的不可行驶区）列表；顶点可能超出画布，出现负数或大于 `height` 的 `y` |

`blocks` 和 `borders` 都是三层数组，含义是 `blocks[障碍物序号][凸块序号][顶点序号]`：

1. 第一层是物体列表，每个元素是一块陨石或一片水域；
2. 第二层是该物体被拆出的**凸多边形**列表。物理引擎只能处理凸形，所以凹形物体会被拆成多块，遍历时必须展开这一层，只取 `blocks[i][0]` 会漏掉同一块陨石的其余部分；
3. 第三层是该凸块的顶点，`{"x": ..., "y": ...}` 是**世界绝对坐标**（已经包含物体位置，不是相对偏移），可以直接和 `rabbits[i]["position"]` 比较。

障碍物的数量、位置和形状由服务端在这一帧给出，本文档不列举具体坐标：地图可能随版本调整，硬编码坐标会在改版后静默失效。请在每次开发前从自己最近一场的 `runtime/matches/<比赛>/frames.jsonl` 第一条读取，并在运行时按上面的结构解析。

策略上的三个要点：

- **`map` 只在 `startGame` 出现一次**，`refreshData` 里没有，`choose_command` 当前也不会收到它。要用地图就先跑一场，从 `frames.jsonl` 第一条离线算好安全区、栅格或距离场，再把计算结果写进 `strategy.py`。
- 撞陨石扣 1 分，但会重置 30 秒无碰撞计时；快到 30 秒又找不到能赢的对手时，`-1` 比 `-3` 划算（无敌状态下撞陨石不扣分）。
- 陨石也是掩体：可以用它挡住高攻击力的对手，但贴着陨石绕行容易被卡住并被反复接触。

### 帧里没有的东西

- **`attackValue` 不再下发给参赛方**。任何一只兔子（包括你自己）的攻击预设都不会出现在 `startGame`、`refreshData`、`closeGame` 和结算结果里；大屏前端在发送前就把它剔除，服务端还会再过滤一次。只有独立的 `/observer` 观战通道用于现场展示。
  - 你自己的预设是你用 `setAttackValue` 设的，请在策略里自行记住。
  - 对手的预设只能估算：把上一帧到这一帧的 `energy` 下降量当作它这次实际投入的能量（森林之心状态下碰撞不耗能，估不出来）。
- `lastCollisionTime` 属于游戏引擎内部状态，不在协议帧里。需要“30 秒未碰撞”判断时，请根据分数、能量、回弹状态的跨帧变化维护自己的近似计时器。
- `forestHeartCount` 只在本局结算结果里出现，实时帧中没有。
- **地图和障碍物只在 `startGame` 下发一次**，`refreshData` 帧里没有 `map`，`choose_command` 也收不到它。详见上一节。

## 合法动作

每次调用最多返回一个动作：

```python
{"commandType": "goForward"}
{"commandType": "goBack"}
{"commandType": "turnLeft", "data": "0.08"}
{"commandType": "turnRight", "data": "0.08"}
{"commandType": "stop"}
{"commandType": "steerBack"}
{"commandType": "setAttackValue", "data": "120"}
```

- 转向速度范围是 `0.01～0.1`。
- 攻击设置范围是 `0～1000`，实际投入不会超过当前 `energy`。
- `data` 写字符串或数字都可以，`bot.py` 会统一转成协议要求的字符串再上报。
- `attack`、`addEnergy`、`defend`、`removeSkill` 对参赛 BOT 无效：服务端要么直接忽略，要么拒绝解析。
- `bot.py` 约每 100ms 调用一次策略；一个回调只能发一个动作。你需要自己设计跨帧状态机。
- **红线：这个上报频率不可修改。** 不改 `bot.py` 的 `COMMAND_INTERVAL_MS` 和限频逻辑，不设置该环境变量，不改 `botHeartbeat` 间隔，也不自建连接或定时任务绕过 `bot.py` 上报。动作是持续状态，超频拿不到额外操作能力，只会被服务端限流或丢弃，并可能按违规处理。
- 移动和转向动作会持续生效，直到另一个动作改变对应状态：`goForward/goBack` 只改行驶方向，`turnLeft/turnRight/steerBack` 只改转向，`stop` 同时停车并回正。
- 比赛未开始、已经结束或本人 `active=False` 时，不应输出战斗动作。

完整的坐标系、移动组合、能量计算、测试方法和 AI 开发提示词见 `OFFICIAL_DEVELOPMENT_GUIDE.md`。

## 你必须自己解决的问题

- 如何判断场地边缘、陨石和即将发生的碰撞。
- 如何选择追击、避让、抢森林之心或保分。
- 如何根据位置、速度与朝向预测对手。
- 如何在看不到对手 `attackValue` 的情况下，用对手 `energy` 的变化估算它的投入。
- 如何用自己的 `energy`、比分和剩余时间决定投入。
- 如何复盘 `runtime/matches/` 中保存的帧、指令和结算结果。
