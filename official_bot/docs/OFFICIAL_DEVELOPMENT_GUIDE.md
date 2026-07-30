# 疯狂 Geek 兔参赛 BOT（Python 版）：AI 立即开发指南

> 目标：让开发者或编码 AI 拿到本开发包后，以 `strategy.py` 为主完成修改，就能理解输入、控制兔子、调整碰撞投入、运行测试并根据真实比赛数据继续优化。

## 1. 先记住这 8 件事

1. 主要修改 `strategy.py`，不要重写 `bot.py` 的认证、分桌、重连和数据保存链路。
2. `choose_command(game_state, bot_id)` 约每 100ms 调用一次，每次只能返回一个动作。
3. 用 `bot_id` 找自己，绝对不要硬编码样例中的 `1001` 或兔子颜色。
4. 不能直接修改剩余总能量 `energy`；只能用 `setAttackValue` 设置下一次碰撞投入上限。
5. **协议帧里没有任何一方的 `attackValue`**。自己的预设要自己记住，对手的投入只能靠它的 `energy` 下降量估算。
6. 移动和转向是持续状态，不是按一下只走一帧。直行时通常需要显式 `steerBack` 回正。
7. 改完先运行 `python3 check.py`，真实比赛后再读 `runtime/matches/`，不要只凭肉眼猜策略效果。
8. **红线：绝对不要修改指令上报频率。** 约 100ms 一个动作是全场统一的节奏，改它是违规，不是优化。

### 红线：上报频率不可修改

这是本开发包唯一的硬性禁止项，比任何策略优化都优先：

- 不修改 `bot.py` 中的 `COMMAND_INTERVAL_MS` 默认值，也不修改它的限频判断。
- 不通过 `COMMAND_INTERVAL_MS` 环境变量把间隔调低（例如 80ms），也不调高。
- 不修改 5 秒一次的 `botHeartbeat` 心跳节奏。
- 不在 `strategy.py` 或任何新增文件里自建 WebSocket、`asyncio` 定时任务、线程、批量指令或“连发”逻辑绕过 `bot.py` 上报。
- 不在一次 `choose_command` 里返回列表或多个动作，试图折算成更高频率。

原因是提高频率**不会**带来任何收益：移动和转向都是持续状态，一个动作会一直生效到下一个动作改变它，所以每 100ms 一次已经足够表达全部控制意图（见第 13 章）。超频上报只会让服务端限流或直接丢弃你的指令，并可能按违规处理。策略的收益来自更好的决策，不是更多的指令。

`COMMAND_INTERVAL_MS` 环境变量存在的唯一目的，是让 `tests/test_lifecycle.py` 在本地模拟服务上跑得快一些。连接真实比赛服务时，任何情况下都不要设置它。

## 2. 给编码 AI 的开工提示词

把整个开发包交给编码 AI 后，可以直接发送下面这段话：

```text
你正在开发“疯狂 Geek 兔”参赛 BOT（Python 版）。

请先完整阅读 README.md、OFFICIAL_RULES.md、OFFICIAL_DEVELOPMENT_GUIDE.md、strategy.py、
tests/test_strategy.py 和 tests/fixtures/sample-refresh-data.json，再开始修改。

目标打法：<在这里写，例如“稳健发育，优先保命和森林之心，末段主动得分”>。

约束：
1. 主要修改 strategy.py，并为关键决策补充 tests/test_strategy.py 场景。
2. 不修改 bot.py 的认证、分桌、入房、重连、心跳和 AccessKey 处理。
3. 红线：绝对不修改指令上报频率。不改 bot.py 的 COMMAND_INTERVAL_MS 与限频逻辑，
   不设置 COMMAND_INTERVAL_MS 环境变量，不改 botHeartbeat 间隔，
   也不自建 WebSocket、asyncio 定时任务或连发逻辑绕过 bot.py 上报。
4. 不把 AccessKey 写入任何文件、命令参数或日志。
5. 每次 choose_command 只返回一个合法动作，不返回列表。
6. 找不到本人或本人 active=False 时必须返回 stop。
7. 协议帧里没有任何一方的 attackValue，禁止读取 rabbit["attackValue"]；
   自己的预设自己记住，对手投入必须用它 energy 的跨帧下降量估算。
8. 只使用 Python 标准库，不要为策略新增第三方依赖。
9. 先把打法翻译成可验证的决策优先级、阈值和状态机，再写代码。
10. 完成后运行 python3 check.py，报告通过的场景、仍未确认的真实比赛行为。

请先用不超过 12 行说明你的策略设计，然后直接实现和验证，不要只给建议。
```

AI 完成第一版后，把最近一场 `frames.jsonl`、`commands.jsonl`、`settlement.json` 和 `battle-data.json` 一起交给它，再发送：

```text
请复盘这场真实比赛。按“现象 -> 帧证据 -> 原因假设 -> 最小策略修改 -> 新测试”输出，
只修改有证据支持的阈值或决策，不要一次重写整个策略。修改后运行 python3 check.py。
```

## 3. 开发包里每个文件做什么

| 文件 | 用途 | 是否建议修改 |
| --- | --- | --- |
| `strategy.py` | 你的目标选择、移动、避险、能量投入和跨帧状态 | 是，主要开发文件 |
| `tests/test_strategy.py` | 用固定局面验证策略性质 | 是，随策略补充 |
| `bot.py` | WebSocket、认证、心跳、分桌、入房、重连、采集和结算 | 初次开发不要改 |
| `OFFICIAL_RULES.md` | 规则、输入和动作的快速索引 | 只读 |
| `tests/fixtures/sample-refresh-data.json` | 一帧真实形状的策略输入 | 只读，可复制到测试 |
| `tests/test_lifecycle.py` | 本地模拟比赛服务，验证接入生命周期和数据落盘 | 通常不改 |
| `tools/replay_recorder.py` / `tools/replay_server.py` | 录制单文件回放、本地回放页 | 通常不改 |
| `check.py` | 语法检查 + 全部测试 | 通常不改 |
| `runtime/` | 运行后产生的真实事件、帧、指令和结算 | 只读分析，不提交 Git |
| `启动BOT.command` / `启动BOT.cmd` | macOS / Windows 安全输入 AK 并启动 | 通常不改 |

## 4. 10 分钟完成第一次策略迭代

### 第一步：确认开发包是完整的

需要 Python 3.10 或更高版本。在开发包目录运行：

```bash
python3 -m pip install -r requirements.txt
python3 check.py
```

未修改模板时，检查通过只代表“开发包链路正常”，不代表 BOT 会赢；默认策略只是可运行的基准实现。

### 第二步：定义打法，不要直接堆 if

先写清楚以下四项：

| 问题 | 示例答案 |
| --- | --- |
| 第一目标 | 靠近边缘时先回安全区 |
| 第二目标 | 森林之心出现且可达时争夺 |
| 第三目标 | 选择最近且不是无敌状态的对手 |
| 碰撞投入 | 估算的对手投入 + 安全余量，但保留 200 能量 |

“激进”“猥琐”“发育”必须落成阈值和优先级。例如“猥琐”不能等于永久不碰撞，因为连续 30 秒无有效碰撞会扣 3 分。

### 第三步：实现并标记

修改 `strategy.py`：

```python
STRATEGY_IMPLEMENTED = True
```

然后实现 `choose_command`。先做最小闭环：

1. 找到自己；
2. 边缘回中；
3. 选择目标；
4. 正确转向并前进；
5. 近距离时设置攻击预设；
6. 无目标时避免停在危险区。

### 第四步：补测试并检查

至少覆盖：

- 找不到本人时停止；
- 本人 `active=False` 时停止；
- 靠近边缘时不继续冲向外侧；
- 对手无敌时不主动追撞；
- 能量不足时不会设置超过规则范围的值；
- 帧里没有 `attackValue` 时策略仍能给出合法动作；
- 森林之心出现时符合你的打法优先级。

运行：

```bash
python3 check.py
```

### 第五步：上线等待

macOS 双击 `启动BOT.command`，Windows 双击 `启动BOT.cmd`。开发与练习时直接输入：

```text
test:你的数字工号
```

例如工号是 `123456`，就输入 `test:123456`。看到：

```text
已上线，正在大厅等待中控台分桌
```

表示接入成功。大厅等待不是卡死，不要自行创建房间或反复重启。

`test:` 不区分大小写，但冒号后必须是纯数字且大于 0。当前服务端会把这串数字直接作为测试 BOT ID，并不会先查询员工或 TANK 数据。如果收到 `BOT_AUTH_FAILED`，先检查格式；格式无误时说明当前环境可能关闭了测试 AK，需要改用报名平台发放的正式 AccessKey。

## 5. BOT 运行生命周期

开发包已经处理以下链路，策略开发者不需要在 `strategy.py` 重复实现：

```text
连接 /ai
  -> botConnect（仅这里发送一次 AK）
  -> botConnected（获得本连接使用的 botId）
  -> 大厅等待
  -> roundAssigned
       -> BYE：留在大厅
       -> MATCH：等待主持人
  -> roundStarted
  -> aiEnterRoom
       -> ROOM_NOT_OPEN：同一连接延迟重试
  -> roomEntered
  -> startGame
  -> refreshData * N -> choose_command * N
  -> closeGame
  -> matchFinished
       -> nextState=WAITING_NEXT_GAME：同桌还有下一局
            -> seriesGameStarted + roundStarted（新的 roomId）-> 重新 aiEnterRoom
       -> 其他：本桌打完
  -> getMyBattleData -> 保存
  -> 正式赛回大厅（roundFinished 给出晋级结论）/ 自由赛 readyForNextMatch
```

正式赛一桌可能连打多局（`gamesPerTable`，例如三局）。每一局都是独立的 `matchId` 和独立的房间：

- 中间局结束时 `matchFinished.nextState = "WAITING_NEXT_GAME"`，`advancementStatus = "PENDING"`；
- 服务端随后下发 `seriesGameStarted` 和 `roundStarted`，带着**新的 `roomId`**；
- 开发包会自动重新入房，`runtime/matches/` 里每局各生成一个目录，`metadata.json` 中的 `gameNo` / `gamesPerTable` 标识这是第几局。

服务端还会主动下发这些事件，开发包已经处理：

| 事件 | 含义 | 开发包行为 |
| --- | --- | --- |
| `seriesGameStarted` | 同桌下一局的房间已就绪 | 清掉旧房间绑定并重新入房 |
| `roundFinished` | 整轮全部赛桌结算完毕，给出最终晋级结论 | 记录 `advancementStatus`，回到大厅 |
| `roundRestarted` | 主持人重开本轮，旧成绩作废 | 清空分桌状态，等待新的 `roundAssigned` |
| `botWaiting` | 中控把全部 BOT 收回大厅 | 清空房间状态并保持在线 |

常见状态：

| 日志/错误 | 含义 | 处理 |
| --- | --- | --- |
| `BOT_CONNECTED` | 身份认证成功 | 保持进程运行 |
| `LOBBY` / `LOBBY_READY` | 等待中控或自由赛匹配 | 正常状态 |
| `ROUND_BYE` | 本轮轮空 | 不进房，继续在线 |
| `ROOM_NOT_OPEN` | 大屏房间还没开启 | 开发包自动重试 |
| `BOT_NOT_ASSIGNED` | 该正式赛房间不属于本队 | 停止重试，等待中控重新分桌 |
| `BOT_ALREADY_ONLINE` + `1008` | 同一个 AK 已有在线进程 | 关闭旧进程；开发包不会再自动重连 |
| `BOT_AUTH_FAILED` + `1007` | AK 无效或环境未开启测试 AK | 换正式 AccessKey；开发包不会再自动重连 |
| `STRATEGY_ERROR` | 策略抛错或返回非法动作 | 查看错误，BOT 会暂时退化为 `stop` |

## 6. `choose_command` 的准确契约

入口：

```python
def choose_command(game_state, bot_id):
    # game_state 是最新 refreshData.data，一个 dict
    # bot_id 是 botConnected 返回的本人 ID
    return {"commandType": "stop"}
```

重要限制：

- 约每 100ms 调用一次，具体间隔可能受网络和运行负载影响。
- 每次只能返回一个动作，不能返回列表。
- 只能返回 `dict`；`None`、字符串或异常都会被 `bot.py` 变成 `stop` 并记录 `STRATEGY_ERROR`。
- 必须是同步函数，不要写成 `async def`。策略在事件循环里被直接调用，长耗时或阻塞 I/O 会推迟整条上报链路。
- `strategy.py` 是常驻模块，模块级变量会跨帧、跨比赛保留。跨帧记忆是必需品：自己的攻击预设、对手投入估算、无碰撞计时都只能靠它。改模块级变量时记得在函数里写 `global`。
- 比赛开始前和结束后不会调用策略。
- 当前入口只把 `refreshData.data` 交给策略，不会把 `roundNo`、`matchCode`、`gameNo` 或 WebSocket 外层 `timestamp` 一并传入。
- 正式赛一桌可能连打多局，同一个进程会被复用。换局时必须重置目标、计时和对手模型，否则会把上一局的状态带进新的一局。

找自己的标准写法：

```python
rabbits = game_state.get("rabbits") or []
me = next((r for r in rabbits if str(r.get("id")) == str(bot_id)), None)

if me is None or me.get("active") is False or me.get("active") == "false":
    return {"commandType": "stop"}
```

使用 `str(...)` 比较是为了兼容服务端数字 ID 和游戏帧字符串 ID。判断 `active` 用 `is False` 而不是 `== False`，因为 Python 里 `0 == False` 会误伤。

## 7. 比赛中 AI 实际能看到什么

### 7.1 顶层字段

一帧输入的主要结构：

```python
{
    "rabbits": [...],                  # 本人和所有对手
    "goldCarrot": {"x": ..., "y": ...},  # 不在场时也可能是 {} 或 None
    "elapsedSeconds": 0,               # 本局已进行秒数
    "remainingTime": 180,              # 本局剩余秒数
}
```

`elapsedSeconds` 和 `remainingTime` 由服务端直接给出，不需要自己用 `time.time()` 估算比赛进度。它们也是判断能量恢复节点（每 30 秒）和森林之心刷新时刻（第 30/90/150 秒）最可靠的依据。

注意本局第一帧 `startGame.data` 的形状不同：它是 `{"rabbits": ..., "map": ...}`，**没有** `goldCarrot`、`elapsedSeconds` 和 `remainingTime`，但**只有它带地图和障碍物**（见第 9 章）。`choose_command` 只会收到后续的 `refreshData.data`。

判断森林之心是否存在，不要只判断对象真假：

```python
import math

def valid_point(point):
    if not isinstance(point, dict):
        return False
    try:
        x, y = float(point.get("x")), float(point.get("y"))
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and math.isfinite(y) and x > 0 and y > 0
```

### 7.2 `rabbits[]` 字段

| 字段 | 类型/单位 | 准确含义 | 策略用途与注意事项 |
| --- | --- | --- | --- |
| `id` | str/int | 本局兔子对应的 BOT ID | 必须用 `str(rabbit["id"]) == str(bot_id)` 识别本人；不要硬编码样例 ID |
| `name` | str | 战队或测试 BOT 的显示名称 | 只用于日志和复盘；名称可能重复或变化，不能作为身份主键 |
| `active` | bool | 当前物理对象是否在场且可行动 | 当前版本 `False` 就是 `score=0` 被淘汰，不会再变回 `True`；本人 `False` 时必须停止输出动作，对手 `False` 时把它从目标列表里剔除 |
| `position.x` | float/px | 兔子碰撞体中心的横坐标，向右增加 | 用于距离、边界和目标方向计算；inactive 兔可能被移到场外，不要追踪 |
| `position.y` | float/px | 兔子碰撞体中心的纵坐标，向下增加 | 屏幕坐标与数学坐标的 y 方向相反，计算方向时仍直接使用 `math.atan2(dy, dx)` |
| `velocity.x/y` | float/px·step⁻¹ | 当前物理 step 的速度向量 | 可预测短期位置、判断是否迎面接近或仍向场外移动；回弹时也会反映瞬时速度 |
| `angle` | float/rad | 当前兔子朝向，约在 `[-pi, pi]` | `0` 大致向右；和目标角做差后必须归一化到 `[-pi, pi]` |
| `speed` | float/px·step⁻¹ | 当前瞬时速度标量 | 正常前后移动通常为 5；回弹时会变化，不能只凭它判断主动前进还是被撞飞 |
| `angularSpeed` | float/rad·step⁻¹ | 当前角速度大小 | 合法控制范围为 `0.01～0.1`；结合 `dirState` 才能知道左右方向 |
| `width/height` | float/px | 服务端公开的碰撞体宽高 | 用于估算安全接触距离和碰撞时间；不要把某个样例尺寸永久写死 |
| `moveState` | int/枚举 | 行驶状态：`1` 前进、`0` 停止、`-1` 后退 | 动作会持续；`goForward/goBack` 只改变这个状态，不会自动回正方向盘 |
| `dirState` | int/枚举 | 转向状态：`1` 右转、`0` 直行、`-1` 左转 | 对准目标后若不发送 `steerBack`，兔子会继续转弯并可能绕圈 |
| `rebounding` | bool | 是否正在执行碰撞后的物理回弹 | 为 `True` 时直接移动命令不会立刻改变回弹轨迹；可先决定回弹结束后要恢复的方向；它也是“刚刚发生过碰撞”的可靠信号 |
| `reboundAngle` | float/rad | 当前回弹移动方向 | 可判断兔子正被弹向哪一侧；它不是兔子正常朝向，不能替代 `angle` |
| `attacking` | bool | 是否处于森林之心赋予的必胜碰撞状态 | 自己为 `True` 时可主动接触；只有对手为 `True` 时应优先避让 |
| `invincible` | bool | 无敌标记；当前实现与 `attacking` 同步 | 兼容不同策略命名时读取；判断无敌可用 `attacking or invincible` |
| `energy` | float/点 | 当前剩余总能量池，范围 `0～1000` | BOT 不能直接修改；普通碰撞消耗，系统每 30 秒对仍在场兔子恢复到 1000。它同时是**估算对手投入的唯一信息源** |
| `score` | int/胡萝卜 | 当前局内分数，初始 10，最低 0 | 排名第一关键字；归零淘汰，低分时应提高生存优先级 |
| `deathCount` | int/次 | 本局被淘汰次数，当前只有 `0` 或 `1` | 同分时越少排名越高；淘汰后不会复活 |
| `survivalTime` | float/秒 | 本局存活秒数，淘汰后停止累计 | 可用来近似推算比赛已进行的时间和下一次能量恢复节点 |

### 7.3 当前策略入口看不到什么

| 数据 | 是否可见 | 应对方式 |
| --- | --- | --- |
| **任何一方的 `attackValue`** | **不可见**，大屏在发送前剔除，服务端再过滤一次 | 自己的预设自己记；对手的投入用它的 `energy` 下降量估算 |
| `lastCollisionTime` | 不可见 | 自己根据分数、能量、`rebounding` 变化近似维护 |
| `forestHeartCount` | 实时帧不可见，只在结算结果里 | 需要统计时读 `settlement.json` |
| 精确剩余秒数 | **可见**，每帧的 `remainingTime` / `elapsedSeconds` | 直接读取，不要再用 `time.time()` 自己估算 |
| 本轮桌号、座位、比赛编号、第几局 | 不传给策略 | 在 `runtime/events.jsonl` 和 `metadata.json` 查看 |
| 测试工号/AccessKey | 策略不需要 | 启动时输入 `test:<数字工号>`；环境关闭测试 AK 时再输入正式 AccessKey，均不写进策略 |
| 地图多边形 | `startGame` 有，但当前 `choose_command` 不直接收到 | 从本场 `frames.jsonl` 第一条读取，离线生成静态避障参数 |

如果某个旧文档、旧策略或旧样例还在读 `rabbit["attackValue"]`，必须删除该依赖：现在它永远不存在，
`rabbit.get("attackValue") or 0` 会静默变成 `0`，让策略以为所有对手都毫无威胁。

## 8. 坐标系与移动控制

### 8.1 坐标和朝向

- 世界画布大小是 `1440 x 820`。
- 左上角约为 `(0, 0)`，x 向右增加，y 向下增加。
- `angle=0` 大致朝右。
- 指向目标的期望角度使用 `math.atan2(target_y - me_y, target_x - me_x)`。
- 必须把角度差归一化到 `[-pi, pi]`，否则跨过 `-pi/pi` 时可能绕远路。

```python
import math

def normalize_angle(angle):
    while angle > math.pi:
        angle -= math.pi * 2
    while angle < -math.pi:
        angle += math.pi * 2
    return angle

def angle_to(me, target):
    desired = math.atan2(
        float(target["y"]) - float(me["position"]["y"]),
        float(target["x"]) - float(me["position"]["x"]),
    )
    return normalize_angle(desired - float(me.get("angle") or 0))
```

角度差大于 0 时，目标在当前朝向的顺时针方向，应右转；小于 0 时左转。

### 8.2 合法动作和持续效果

| 返回值 | 效果 | 是否持续 |
| --- | --- | --- |
| `{"commandType": "goForward"}` | 以固定速度 5px/帧前进 | 是，直到 `goBack` 或 `stop` |
| `{"commandType": "goBack"}` | 以固定速度 5px/帧后退 | 是，直到 `goForward` 或 `stop` |
| `{"commandType": "turnLeft", "data": "0.08"}` | 设置左转角速度 | 是，直到 `turnRight`、`steerBack` 或 `stop` |
| `{"commandType": "turnRight", "data": "0.08"}` | 设置右转角速度 | 是，直到 `turnLeft`、`steerBack` 或 `stop` |
| `{"commandType": "steerBack"}` | 方向盘回正，不改变前进/后退状态 | 是 |
| `{"commandType": "stop"}` | 停车并回正 | 是 |
| `{"commandType": "setAttackValue", "data": "120"}` | 设置后续普通碰撞投入上限 | 持续到再次设置 |

转向值范围 `0.01～0.1`：

- `0.03～0.05`：平滑、适合远距离追踪；
- `0.06～0.08`：常用；
- `0.09～0.1`：急转，容易震荡或绕圈。

### 8.3 最容易写错的移动语义

`goForward` 只改变行驶状态，不会自动回正；`turnLeft/turnRight` 只改变转向状态，不会让停止中的兔子原地旋转。因此建议：

1. 停止状态先 `goForward`；
2. 下一帧开始转向；
3. 对准后先 `steerBack`；
4. 后续继续前进。

可复用的最小导航函数：

```python
def move_toward(me, target):
    if not target or not me.get("position"):
        return {"commandType": "stop"}

    # 停止时先启动。游戏不支持可靠的原地转向。
    if int(me.get("moveState") or 0) == 0:
        return {"commandType": "goForward"}

    diff = angle_to(me, target)
    tolerance = 0.16

    if abs(diff) > tolerance:
        turn_speed = "0.09" if abs(diff) > 0.8 else "0.05"
        return {
            "commandType": "turnRight" if diff > 0 else "turnLeft",
            "data": turn_speed,
        }

    if int(me.get("dirState") or 0) != 0:
        return {"commandType": "steerBack"}

    return {"commandType": "goForward"}
```

不要写成“未对准一直发转向，对准后只发 `goForward`”。因为之前的转向状态仍会持续，BOT 很容易围着目标画圈。

### 8.4 预测移动目标

追逐当前坐标会产生尾追。可根据速度向量预测 200～500ms 后的位置：

```python
def predict_position(rabbit, look_ahead_frames=12):
    position = rabbit.get("position") or {"x": 0, "y": 0}
    velocity = rabbit.get("velocity") or {"x": 0, "y": 0}
    return {
        "x": float(position.get("x") or 0) + float(velocity.get("x") or 0) * look_ahead_frames,
        "y": float(position.get("y") or 0) + float(velocity.get("y") or 0) * look_ahead_frames,
    }
```

`look_ahead_frames` 不是 WebSocket 帧数，而是游戏物理 step 的近似量。先从 8～12 开始，用真实回放调节。

## 9. 边界和障碍物

### 9.1 地图事实

- 画布是 `1440 x 820`，但可行驶区域不是完整矩形。
- 地图两侧是水域边界，场内还有若干静态障碍（陨石）；具体数量和位置以本场 `startGame` 下发的数据为准。
- `startGame.data.map` 包含 `width`、`height`、`borders`（水域多边形）和 `blocks`（陨石多边形）。
- 当前 `choose_command` 只接收后续 `refreshData.data`，所以策略不能直接从参数读取 `map`。
- **当前版本没有落水机制**：引擎每帧把兔子强行夹在可行驶区内（`x` 超出约 `300～1300` 会被拉回 `400 / 1190`，`y` 超出 `0～820` 会被拉回边界）。贴边不会掉下去，但会被瞬移、丢失朝向优势，并且很容易被对手在边线上反复接触。

开发包会把原始 `startGame` 保存为本场 `frames.jsonl` 第一条。第一场练习后，AI 可以读取地图多边形，离线生成点到多边形距离或若干安全区，再把计算结果写进 `strategy.py`。

### 9.2 `startGame.data.map` 的准确结构

```python
{
    "width": 1440,
    "height": 820,
    "borders": [[[{"x": ..., "y": ...}, ...], ...], ...],  # 水域（不可行驶区）
    "blocks": [[[{"x": ..., "y": ...}, ...], ...], ...],   # 陨石（场内障碍物）
}
```

| 字段 | 含义 | 解析注意 |
| --- | --- | --- |
| `width` / `height` | 画布尺寸，单位 px | 可行驶区小于这个矩形，不能当安全区用 |
| `blocks` | 陨石（场内障碍物）列表 | 三层数组，见下 |
| `borders` | 水域（场地之外的不可行驶区）列表 | 三层数组；描述的是画布之外的水，顶点会出现负的 `y` 或大于 `height` 的 `y` |

`blocks` 和 `borders` 的三层嵌套都是 `[物体序号][凸块序号][顶点序号]`：

1. 第一层是物体列表，每个元素是一块陨石或一片水域；
2. 第二层是该物体被拆出的**凸多边形**列表。物理引擎只能处理凸形，所以凹形物体会被拆成多块；
3. 第三层是该凸块的顶点，`{"x": ..., "y": ...}` 是**世界绝对坐标**，已经包含物体位置，可以直接和 `rabbits[i]["position"]` 比较。

第二层最容易被忽略：只取 `blocks[i][0]` 会漏掉同一块陨石的其余部分，导致策略以为那半边可以通过。正确做法是把内层全部展开成凸多边形列表：

```python
def collect_polygons(groups):
    polygons = []
    for group in groups or []:
        for part in group or []:
            if isinstance(part, list) and len(part) >= 3:
                polygons.append(part)
    return polygons

block_polygons = collect_polygons(game_map.get("blocks"))
water_polygons = collect_polygons(game_map.get("borders"))
```

拿到凸多边形列表后，常见的做法是：点在多边形内判断（射线法或叉积同侧判断）、点到多边形最近距离、把整张图栅格化成通行网格再做寻路。

**本文档不列举具体的障碍物数量和坐标。** 地图会随版本调整，把坐标抄进策略后，改版时不会报错、只会静默变成错误的避障。请每次开发前从自己最近一场的 `frames.jsonl` 第一条重新读取，并在运行时按上面的结构解析——需要固化时固化的是「离线算出的安全区/网格」，而且要标注它来自哪一场录像。

读取最近一场的地图：

```python
import json

with open("runtime/matches/<比赛>/frames.jsonl", encoding="utf-8") as handle:
    first = json.loads(handle.readline())
game_map = first["data"]["map"]
```

陨石在策略里有三种用法：

- **避让**：正常导航时把陨石当禁行区，撞上扣 1 分。
- **主动利用**：快到 30 秒无碰撞惩罚、又找不到能赢的对手时，主动撞陨石把 `-3` 变成 `-1`；拿到森林之心期间撞陨石不扣分。
- **掩体**：用陨石隔开高攻击力对手。但贴着陨石绕行容易被卡住、被反复接触，收益要和风险一起算。

### 9.3 第一版可用的保守策略

还没有解析地图多边形时，可以先使用保守矩形做“回中”保护：

```python
CENTER = {"x": 760, "y": 410}
SAFE_BOX = {"min_x": 380, "max_x": 1220, "min_y": 90, "max_y": 720}

def near_unsafe_edge(me):
    position = me.get("position") or {}
    x = float(position.get("x") or 0)
    y = float(position.get("y") or 0)
    return (x < SAFE_BOX["min_x"] or x > SAFE_BOX["max_x"]
            or y < SAFE_BOX["min_y"] or y > SAFE_BOX["max_y"])
```

这个矩形是保守启发式，不是完整地图碰撞定义。真实优化应以 `startGame.data.map` 的多边形和比赛帧为证据。

障碍风险可先组合三类信号：

- `rebounding=True`：刚发生碰撞，暂时不要继续追原目标；
- 下一位置超出安全区：优先回中；
- 兔子朝向边缘且速度仍向外：提前转弯，不要等到已经被引擎拉回。

## 10. 能量与攻击预设：最重要的策略资源

### 10.1 不能直接“调能量”

比赛中有两个数：

| 数值 | 含义 | 帧里可见 | BOT 能否直接修改 |
| --- | --- | --- | --- |
| `energy` | 当前剩余总能量池 | 是，自己和所有对手 | 不能 |
| `attackValue` | 下一次普通碰撞的投入上限 | **否，任何一方都不可见** | 可以用 `setAttackValue` 调整自己的 |

不允许发送 `addEnergy`、`setEnergy` 或 `attack`。这些不是参赛指令，服务端会忽略。

设置攻击预设：

```python
{"commandType": "setAttackValue", "data": "300"}
```

合法范围是 `0～1000`。发送该动作不会立刻扣能量，只有普通兔子碰撞结算时才消耗。

### 10.2 碰撞计算

普通状态下：

```text
本人有效攻击力 = min(本人攻击预设, 本人当前 energy)
对手有效攻击力 = min(对手攻击预设, 对手当前 energy)   # 对手预设不可见，只能估算
```

高者赢得 1 分，低者失去 1 分；相同则分数不变。双方都会消耗各自本次有效攻击力。
同一对兔子 1.5 秒内只结算一次碰撞。

例如本人 `energy=220`：

| 设置值 | 本次有效攻击力 | 碰撞后最多剩余 |
| ---: | ---: | ---: |
| 50 | 50 | 170 |
| 180 | 180 | 40 |
| 500 | 220 | 0 |

### 10.3 对手投入只能估算

协议帧不再下发 `attackValue`，所以“对手这一次会投多少”必须自己建模。可用的观测只有一条：
**普通碰撞结算后，对手的 `energy` 会正好下降它本次的有效投入。**

```python
import math

opponent_models = {}
previous_rabbits = {}

def update_opponent_models(rabbits, my_id):
    for rabbit in rabbits:
        rabbit_id = str(rabbit.get("id"))
        previous = previous_rabbits.get(rabbit_id)
        if rabbit_id != str(my_id) and previous:
            spent = float(previous.get("energy") or 0) - float(rabbit.get("energy") or 0)
            # 每 30 秒的系统恢复会让 energy 上升，不是投入；森林之心状态下碰撞不耗能，采不到样本。
            if 0 < spent <= 1000 and not previous.get("attacking"):
                model = opponent_models.get(rabbit_id) or {"estimate": 50, "samples": 0, "maximum": 50}
                weight = 0.4 if model["samples"] else 0.7
                model["estimate"] = round(model["estimate"] * (1 - weight) + spent * weight)
                model["maximum"] = max(model["maximum"], spent)
                model["samples"] += 1
                opponent_models[rabbit_id] = model
        previous_rabbits[rabbit_id] = rabbit

def estimated_power(rabbit):
    if rabbit.get("attacking") or rabbit.get("invincible"):
        return math.inf
    model = opponent_models.get(str(rabbit.get("id")))
    estimate = model["estimate"] if model else 50
    # 无论它预设多少，都打不过自己剩下的能量。
    return max(0, min(float(rabbit.get("energy") or 0), estimate))
```

关键前提：

- 默认预设是 50，没有样本时用 50 起步比用 0 或 1000 都稳。
- `energy` 上升说明发生了 30 秒统一恢复，不能当作投入样本。
- 对手可以在任何一帧改预设，估算值是历史行为的先验，不是承诺，务必留余量。
- 对手 `energy` 就是它投入的硬上限：`energy=80` 的对手最多只能投 80。
- `previous_rabbits[rabbit_id] = rabbit` 存的是服务端每帧新建的 `dict`，可以直接留引用；如果你自己改过帧内容，请存副本。

### 10.4 能量如何恢复

- 初始 `energy=1000`；
- 每 30 秒，仍在场的兔子恢复到 1000；
- 恢复不是“增加 1000”，而是直接回到上限 1000；
- `energy=0` 不会被淘汰，只是之后的普通碰撞必输（对手投入大于 0 时）；
- `score=0` 的淘汰兔不会恢复，也不会复活。

所以“恢复前花掉剩余能量”有潜在价值，但策略入口没有精确比赛时钟，只能本地估算，必须留出误差。
可以用所有在场兔子 `energy` 同时跳回 1000 的那一帧来对齐恢复节点。

### 10.5 合理设置攻击力

不要每帧重复设置同一个值。设置动作会占用本帧的唯一命令槽；移动状态会继续保持，但频繁设置会降低导航反应速度。

```python
requested_attack = None

def maybe_set_attack(value):
    global requested_attack
    next_value = max(0, min(1000, round(value)))
    if next_value == requested_attack:
        return None
    requested_attack = next_value
    return {"commandType": "setAttackValue", "data": str(next_value)}
```

碰撞前的基础计算：

```python
def attack_needed(me, enemy, reserve=150):
    enemy_power = estimated_power(enemy)
    if not math.isfinite(enemy_power):
        return 0   # 对手无敌，投入多少都会输
    affordable = max(0, float(me.get("energy") or 0) - reserve)
    margin = max(8, math.ceil(enemy_power * 0.15))
    return min(affordable, enemy_power + margin)
```

余量要比“能看到对手真实值”的旧版本更大：估算有误差，而且对手随时可以加码。

这只是计算积木，不是完整策略。还要判断：

- 是否真的即将碰撞；
- 对手是否可能在下一帧提高投入；
- 自己是否处于森林之心状态；
- 赢 1 分是否值得消耗这批能量；
- 距离下次恢复节点大约还有多久；
- 当前排名是否需要主动冒险。

### 10.6 森林之心

`goldCarrot` 是森林之心的兼容协议字段。当前引擎在比赛第 30、90、150 秒让道具出现；拾取后 10 秒：

- `attacking=True`、`invincible=True`；
- 与普通兔子碰撞必胜；
- 碰撞不消耗能量；
- 撞普通障碍不会扣分；
- 仍会发生物理偏转或回弹，并不是穿墙。

只有对手无敌而自己不无敌时，应优先避让。双方都无敌时，碰撞按相同无限攻击力处理，通常不改分。

## 11. 比赛规则如何影响策略

| 事件 | 结果 | 策略含义 |
| --- | --- | --- |
| 普通碰撞获胜 | `score +1` | 赢小碰撞是主要得分方式 |
| 普通碰撞失败 | `score -1` | 高分时不必追逐高风险对手 |
| 有效攻击力相同 | 分数不变但双方耗能 | 可消耗对手，但自己也付出资源 |
| 同一对兔子 1.5 秒内重复接触 | 只结算一次 | 贴脸摩擦刷不出分，撞完要分开再来 |
| 撞陨石 | `score -1`，并重置 30 秒计时 | 路线质量与攻击决策同样重要；但快到 30 秒还没碰撞时，用 `-1` 换掉 `-3` 是划算的 |
| 连续 30 秒无有效碰撞 | `score -3` | 纯躲避会被规则惩罚 |
| 被推到场地边缘 | 被引擎拉回可行驶区，不扣分 | 没有落水风险，但会丢位置和朝向，仍应避免 |
| `score=0` | 立即淘汰，`deathCount +1`，不复活 | 低分时生存优先级必须提高 |

单桌结算排序（服务端权威，决定积分与晋级）：

1. `score` 降序；
2. `deathCount` 升序（没被淘汰的排在被淘汰的前面）；
3. BOT ID 升序，保证服务端产生唯一名次。

默认四人桌按第 1～4 名获得 `4/3/2/1` 局分；正式赛一桌可能连打 `gamesPerTable` 局，按累计局分决定桌内名次，前两名晋级。策略不能只追求“单次碰撞胜率”，还应追求最终桌内名次。

## 12. 推荐的决策优先级

一个可维护的策略应按层决策，而不是把所有条件揉成一个超长函数。建议从高到低：

```text
P0 本人不存在或 active=False -> stop
P1 即将出界/危险回弹 -> 回安全区
P2 对手无敌且正在接近 -> 避让
P3 自己无敌 -> 主动追最近可接触对手
P4 森林之心存在且路线安全 -> 争夺
P5 即将与目标碰撞 -> 用估算的对手投入计算并 setAttackValue
P6 距离无碰撞惩罚过近 -> 寻找低风险有效接触
P7 根据比分、能量和阶段选择对手
P8 无高价值目标 -> 保持安全移动，不在危险区原地停留
```

### 12.1 跨帧状态

可以在 `strategy.py` 模块级维护：

```python
memory = {
    "target_id": None,
    "requested_attack": None,
    "match_started_at": 0,
    "last_frame_at": 0,
    "last_meaningful_contact_at": 0,
    "previous_rabbits": {},
    "opponent_models": {},
}
```

用 `dict` 而不是一堆模块级变量，好处是改值时不用到处写 `global`。

用途：

- 避免每帧切换追击目标；
- 避免重复发送同一个攻击值；
- 记住自己当前的攻击预设（帧里读不到）；
- 用对手 `energy` 的跨帧下降量估算它的投入；
- 本地估算比赛阶段与能量恢复节点；
- 根据 `score/energy/rebounding` 变化推断可能发生过碰撞；
- 给动作加 300～800ms 的最短持有期，减少左右抖动。

注意模块状态会跨比赛保留，正式赛同桌连打多局时尤其容易踩坑。判断新一场开始可以组合几个信号：距离上次策略调用超过 5 秒、所有兔子 `score` 同时回到 10、所有兔子 `energy` 同时是 1000、`survivalTime` 从大值跳回接近 0。命中后重置目标、计时和对手模型。这些都是近似值，应从真实日志验证。

### 12.2 目标选择评分

比“永远追最近”更稳定的方式是给每个候选目标打分：

```text
目标分 = 距离成本
       + 对手无敌惩罚
       + 估算的对手投入风险（含它的 energy 上限）
       + 靠近边缘风险
       - 对手高分价值
       - 自己无敌时的追击奖励
```

分数越低越值得追。每隔 500ms～1s 才重新选目标，除非当前目标淘汰、无敌或变得不可达。

## 13. 每帧只能发一个动作，怎么同时移动和调攻击

动作会持续，所以不需要每一帧同时发送多个命令。示例时序：

```text
t=0ms    goForward          -> 开始持续前进
t=100ms  turnRight 0.05     -> 持续右转且继续前进
t=200ms  turnRight 0.05     -> 仍在修正方向
t=300ms  steerBack          -> 回正且继续前进
t=400ms  setAttackValue 130 -> 前进状态保持，更新碰撞投入
t=500ms  goForward          -> 继续导航
```

因此策略应返回“本帧最需要改变的状态”，而不是试图描述完整控制器状态。

优先级通常是：紧急避险动作 > 碰撞前最后一次能量设置 > 常规导航。

这也是“上报频率不可修改”这条红线成立的原因（见第 1 章）：既然动作是持续状态，100ms 一次已经能表达全部控制意图，把频率调高得不到任何额外操作能力，只会触发服务端限流并按违规处理。如果你觉得“帧不够用”，需要改的是决策优先级和状态机，不是上报间隔。

## 14. 如何写不会过拟合的策略测试

`tests/test_strategy.py` 是一个直接运行的脚本，用 Python 内置 `assert` 断言，不需要 pytest：

```bash
python3 tests/test_strategy.py
```

不要只断言某一帧必须返回一个非常具体的原始动作。更有价值的是验证策略性质。

例如，边缘局面可以允许“左转回场”或“停止”，但不能继续朝场外直冲：

```python
command = choose_command(edge_state, 1001)
assert command != {"commandType": "goForward"}, "靠近场地边缘时不能继续直冲"
```

注意 `strategy.py` 的模块级状态会在同一个测试进程里累积（例如基准策略的 `_decision_count`）。断言“第 N 次调用返回什么”会很脆弱，应该断言动作性质。

建议场景表：

| 场景 | 应验证的性质 |
| --- | --- |
| 本人缺失 | 必须 `stop` |
| 本人 inactive | 必须 `stop` |
| 停止且目标在前方 | 先启动，不依赖原地转向 |
| 已在转弯且目标已对准 | 会 `steerBack`，不会持续画圈 |
| 对手无敌迎面接近 | 不主动提高攻击并追撞 |
| 自己无敌 | 不浪费帧反复设置高攻击值 |
| 自己能量 100、要求保留 50 | 设置值不能超过 50 |
| 帧中完全没有 `attackValue` 字段 | 仍返回合法动作，不把对手当成 0 攻击 |
| 连续两帧对手 `energy` 从 800 掉到 600 | 估算模型把该对手的投入调到 200 附近 |
| 全场 `energy` 同时跳回 1000 | 不把恢复误判成一次碰撞投入 |
| 森林之心不存在 `{}` / `None` | 不把 `(0,0)` 当目标 |
| 靠近安全区外沿 | 目标改为内部安全点 |
| 陨石正好挡在本人与目标之间 | 会绕行或改目标，不是直冲撞上去 |
| 对手 ID 类型变化 | int/str 均能识别本人 |

每改一个 bug，先把触发它的帧裁剪成一个小测试，再改策略。

## 15. 真实比赛数据在哪里

每场目录结构：

```text
runtime/
  events.jsonl
  matches/<matchCode-matchId>/
    metadata.json
    frames.jsonl
    commands.jsonl
    capture-summary.json
    replay.ccreplay.json
    settlement.json
    battle-data.json
```

| 文件 | 先看什么 |
| --- | --- |
| `events.jsonl` | 是否正确上线、分桌、进房、结算和再次就绪 |
| `metadata.json` | botId、比赛编号、`gameNo/gamesPerTable`、策略 hash |
| `frames.jsonl` | 每个决策时刻前的世界状态；第一条 `startGame` 含地图 |
| `commands.jsonl` | 策略实际发送了什么，不是代码理论上会发什么 |
| `capture-summary.json` | 帧数、命令数、起止时间 |
| `replay.ccreplay.json` | 可以在本地回放页直接打开的单文件录像 |
| `settlement.json` | 本局名次、分数、局分、森林之心次数和存活时间 |
| `battle-data.json` | 本人历史场次、对手、赛事排名 |

正式赛一桌打多局时，每一局是一个独立目录；靠 `metadata.json` 里的 `gameNo` 区分先后。

JSONL 是“一行一个 JSON”。编码 AI 可以直接逐行解析：

```python
import json

with open("runtime/matches/<比赛>/frames.jsonl", encoding="utf-8") as handle:
    frames = [json.loads(line) for line in handle if line.strip()]
```

人工快速检查最近目录：

```bash
ls -1dt runtime/matches/*/
```

### 15.1 推荐复盘指标

至少统计：

- 最终 `rank/score/deathCount`；
- 每场碰撞前后的自己/对手能量变化；
- `setAttackValue` 次数及重复设置比例；
- 在安全区外停留时长；
- 左右转连续切换次数；
- 森林之心出现后是否在合理时间内改变目标；
- `score -3` 的疑似无碰撞惩罚次数；
- 最后 30 秒是否根据名次改变风险偏好。

不要只用单场结果判断策略。至少比较多场的平均名次、平均分、死亡次数和对手强度。

## 16. 常见失败模式

| 症状 | 常见原因 | 修复方向 |
| --- | --- | --- |
| BOT 一直原地不动 | 没把 `STRATEGY_IMPLEMENTED` 改成 `True`，或策略一直返回 `stop` | 查看 `commands.jsonl` 和 `STRATEGY_ERROR` |
| BOT 围着目标画圈 | 对准后发 `goForward`，但没有 `steerBack` | 显式回正，增加角度容差 |
| BOT 停着转不起来 | 停止状态先发了 `turnLeft/right` | 先 `goForward`，下一帧转向 |
| 能量瞬间耗尽 | 每次碰撞设置过高，未设保留能量 | 引入 reserve 和碰撞价值判断 |
| 所有对手看起来都是 0 攻击 | 还在读已被移除的 `rabbit["attackValue"]`，`rabbit.get("attackValue") or 0` 静默变 0 | 删掉该依赖，改用 `energy` 下降量估算 |
| 估算值长期偏低 | 把 30 秒统一恢复导致的 `energy` 上升也当成样本，或对手一直没碰撞过 | 只采纳下降样本，无样本时用默认 50 起步 |
| 明明高于估算值仍输 | 对手在碰撞前临时加码，或对手拿到森林之心 | 估算只是先验，加大余量并检查 `attacking/invincible` |
| 贴着对手却一直不加分 | 同一对兔子 1.5 秒内只结算一次 | 撞完先脱离再重新接触 |
| 纯躲避却持续掉分 | 连续 30 秒无有效碰撞被扣 3 分 | 增加低风险接触阶段 |
| 把森林之心目标设为左上角 | `{}` 被误判为存在 | 校验有限且大于 0 的 x/y |
| 淘汰兔仍被当成目标 | `rabbit["active"] == False` 在 Python 里会被 `0` 命中 | 用 `is False` 判断 |
| 策略偶发失控 | 返回非法对象或抛异常，运行器退化 `stop` | 查 `STRATEGY_ERROR`，补异常场景测试 |
| 上报明显变慢或卡顿 | 策略里做了阻塞 I/O、`time.sleep` 或重计算 | 策略必须是快速的纯计算，重活离线做好再写进代码 |
| 重启后提示已在线 | 旧进程仍占有 AK | 关闭旧进程；不要修改或轮换 AK |
| 改完测试失败 | 动作数据越界或旧测试断言过死 | 保留合法动作检查，把测试改成策略性质 |
| 只看代码觉得有效，实战无提升 | 没对齐真实帧和实际发出命令 | 以 `frames + commands + settlement` 联合复盘 |

## 17. 安全和比赛边界

- **红线：不修改指令上报频率。** 不改 `bot.py` 的 `COMMAND_INTERVAL_MS` 和限频逻辑，不设置该环境变量，不改 `botHeartbeat` 间隔，不自建连接或定时任务绕过 `bot.py` 上报。超频指令会被服务端限流或丢弃，并可能按违规处理。
- 开发与练习优先在启动脚本输入 `test:<数字工号>`，不要把固定工号写进策略代码。
- 正式 AccessKey 只通过启动脚本安全输入，或由部署系统 Secret 环境变量注入。
- 不把正式 AccessKey 写进 `.env`、源码、README、截图、命令参数或日志。
- 同一个 `test:工号` 或正式 AccessKey 同时只能有一个 WebSocket 在线。
- BOT 不自行注册 TANK、不自行选择正式赛房间、不创建对手、不推进赛事轮次。
- 只在 `startGame` 后发送战斗动作。服务端在下发 `closeGame` 之前已经关闭房间，之后任何战斗指令都会被拒绝，开发包也不会再发。
- 正式赛等待中控，轮空时保持在线即可；同桌多局之间只需保持连接，开发包会自动进入下一局的房间。
- 自由赛结算和数据保存完成后，开发包会发送 `readyForNextMatch`。

## 18. 交付前检查表

### 静态与本地检查

- [ ] 上报频率未被改动：`bot.py` 的 `COMMAND_INTERVAL_MS`、限频判断和 `botHeartbeat` 间隔保持默认，且没有设置 `COMMAND_INTERVAL_MS` 环境变量
- [ ] 没有新增 WebSocket、`asyncio` 定时任务或连发逻辑绕过 `bot.py` 上报
- [ ] `STRATEGY_IMPLEMENTED is True`
- [ ] 找不到自己或 `active=False` 时返回 `stop`
- [ ] 所有分支都返回一个合法动作 `dict`
- [ ] `choose_command` 是同步函数，没有阻塞 I/O
- [ ] 转向速度在 `0.01～0.1`
- [ ] 攻击设置在 `0～1000`
- [ ] 代码里没有任何地方读取 `rabbit["attackValue"]`
- [ ] 自己的攻击预设由策略自己记录，对手投入靠 `energy` 变化估算
- [ ] 没有硬编码本人 BOT ID、房间 ID 或 AccessKey
- [ ] 已为边缘、无敌、低能量、无道具等场景补测试
- [ ] `python3 check.py` 通过

### 在线接入检查

- [ ] 收到 `BOT_CONNECTED`，且测试身份的 botId 等于数字工号，或正式身份对应预期 TANK
- [ ] 大厅等待时没有自行进房
- [ ] `ROUND_BYE` 时没有进房
- [ ] `roundStarted` 后才能进入指定房间
- [ ] `ROOM_NOT_OPEN` 会自动重试
- [ ] 没有 `BOT_ALREADY_ONLINE` 的重复进程

### 真实比赛检查

- [ ] 事件顺序是 `startGame -> refreshData -> closeGame -> matchFinished`
- [ ] `frames.jsonl` 里的 `rabbits[]` 确实没有 `attackValue`
- [ ] 多局制正式赛里，每一局都有独立目录且 `gameNo` 递增
- [ ] `frames.jsonl` 和 `commands.jsonl` 均有内容
- [ ] `settlement.json` 与 `battle-data.json` 已保存
- [ ] 至少复盘一场边缘、一次碰撞和一次能量设置
- [ ] 用多场平均名次验证优化，不只看一场胜负

本地检查通过只证明开发包和策略契约可运行；在线接入成功只证明 BOT 已被比赛服务识别；只有真实比赛数据才能证明策略是否有效。这三层结论必须分开。

## 19. 与 Node.js 版的对应关系

两个开发包功能一一对应，协议、数据落盘目录结构和回放文件格式完全相同，可以自由选一个使用。

| Node.js 版 | Python 版 |
| --- | --- |
| `strategy.cjs` / `chooseCommand` | `strategy.py` / `choose_command` |
| `bot.cjs` | `bot.py` |
| `replay-recorder.cjs` | `tools/replay_recorder.py` |
| `replay-server.cjs` | `tools/replay_server.py` |
| `strategy.test.cjs` | `tests/test_strategy.py` |
| `lifecycle.test.cjs` | `tests/test_lifecycle.py` |
| `npm install` | `python3 -m pip install -r requirements.txt` |
| `npm run check` | `python3 check.py` |
| `npm run replay` | `python3 tools/replay_server.py` |
| `npm start` | `python3 bot.py` |
| 依赖 `ws` | 依赖 `websockets` |

环境变量完全一致：`CRAZY_CRASH_ACCESS_KEY`、`CRAZY_CRASH_SERVER_URL`、`CRAZY_CRASH_WS_URL`、`CRAZY_CRASH_RUNTIME_DIR`、`BOT_VERSION`、`BOT_STYLE`、`ROOM_RETRY_MS`、`COMMAND_INTERVAL_MS`、`BATTLE_DATA_TIMEOUT_MS`、`REPLAY_PORT`。

策略返回值也一致：JS 的 `{ commandType: 'turnLeft', data: '0.05' }` 对应 Python 的 `{"commandType": "turnLeft", "data": "0.05"}`。协议字段名保持小驼峰，不要改成蛇形。
