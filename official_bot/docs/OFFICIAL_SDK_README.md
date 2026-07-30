# 疯狂 Geek 兔参赛 BOT 开发包（Python 版）

> 这是赛事方原始 SDK README 的归档整理版。目录路径已更新，但其中“默认基准
> 策略”的描述不再代表当前 Wolf 实现；实际入口和结构请先阅读项目根目录
> `README.md` 与 `docs/WOLF_STRATEGY.md`。

这是一个“连接能力完整、附带可运行基准策略”的参赛开发包，与 Node.js 版 `participant-bot-starter` 功能一一对应，只是换成了 Python + `websockets`。

它已经处理 WebSocket 认证、心跳、中控分桌、轮空、开始轮次后入房、正式赛同桌多局的换房、房间未开启重试、断线重连、比赛数据保存和自由赛再次就绪。默认 `strategy.py` 会在金萝卜、最近对手和地图边界之间选择目标并实际移动、转向；它是便于验证接入和录制链路的基准实现，参赛者仍应根据规则继续优化。

> 协议要点：比赛帧**不再下发任何一方的 `attackValue`**。你自己的攻击预设要在策略里自己记住，对手的投入只能靠它 `energy` 的跨帧下降量估算。详见 `OFFICIAL_RULES.md` 和 `OFFICIAL_DEVELOPMENT_GUIDE.md` 第 10 章。

## 快速开始

唯一前置条件是安装 [Python 3.10 或更高版本](https://www.python.org/downloads/)。

1. 先阅读 `OFFICIAL_DEVELOPMENT_GUIDE.md`；规则速查见 `OFFICIAL_RULES.md`。
2. 直接使用 `strategy.py` 的基准策略，或修改其中的 `choose_command` 实现自己的策略。
3. 运行 `python3 check.py`，确认语法、动作格式和接入生命周期测试通过。
4. macOS 双击 `启动BOT.command`；Windows 双击 `启动BOT.cmd`。
5. 按提示输入 `test:你的数字工号`，例如 `test:123456`。输入不会显示，也不会保存到文件。
6. 看到“已上线，正在大厅等待中控台分桌”后保持窗口开启。关闭窗口即下线。

首次启动会自动在开发包目录创建 `.venv` 虚拟环境并安装 `websockets`。所有 BOT 共用 `wss://pre-young-hackathon.alibaba-inc.com/ai`。预发开发与练习推荐直接使用 `test:<数字工号>`；服务端会把该数字作为测试 BOT ID。若比赛环境关闭了测试 AK，再改用报名平台发放的正式 AccessKey。

不想用启动脚本时，也可以手动运行：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
CRAZY_CRASH_ACCESS_KEY='test:123456' ./.venv/bin/python bot.py
```

## 只修改哪里

- 主要修改：`strategy.py`
- 建议随策略补充：`tests/test_strategy.py`
- 开发手册：`OFFICIAL_DEVELOPMENT_GUIDE.md`
- 规则与数据速查：`OFFICIAL_RULES.md`、`tests/fixtures/sample-refresh-data.json`
- 不建议修改：`bot.py`、两个启动脚本

`bot.py` 负责比赛基础设施，`strategy.py` 负责目标和路线。默认 `BOT_STYLE=hunter` 会追逐目标；设置 `BOT_STYLE=runner` 会在没有金萝卜时远离最近对手。策略抛错或返回非法动作时，程序会记录 `STRATEGY_ERROR` 并退化为 `stop`。

## 红线：千万不要修改上报频率

这是本开发包唯一的硬性禁止项：**约 100ms 上报一个动作的节奏是全场统一约定，任何情况下都不允许修改。**

- 不修改 `bot.py` 里的 `COMMAND_INTERVAL_MS` 默认值和限频判断。
- 不设置 `COMMAND_INTERVAL_MS` 环境变量调快或调慢间隔（它只用于本地 `tests/test_lifecycle.py` 加速）。
- 不修改 5 秒一次的 `botHeartbeat` 心跳。
- 不在 `strategy.py` 或新增文件里自建 WebSocket、`asyncio` 定时任务、批量或连发逻辑绕过 `bot.py` 上报。
- 不在一次 `choose_command` 里返回列表或多个动作。

提高频率拿不到任何额外操作能力：移动和转向都是持续状态，一个动作会一直生效到下一个动作改变它，100ms 一次已经足够表达全部控制意图。超频上报只会被服务端限流或直接丢弃，并可能按违规处理。想赢要靠更好的决策，不是更多的指令。

## 本地检查

```bash
python3 -m pip install -r requirements.txt
python3 check.py
```

检查会验证：策略会实际移动或转向、动作格式合法、找不到本人时会停止、策略没有读取已下线的 `attackValue`、分桌后不会提前入房、正式赛同桌多局会按新房间重新入房、自由赛结算后才申请下一场、每一局的原始帧和结算数据分别落盘、AccessKey 不会写入日志。

也可以单独运行某个测试，例如 `python3 tests/test_strategy.py`。

## 战斗数据

运行后会生成 `runtime/`：

- `events.jsonl`：连接、分桌、进房和结算事件。
- `matches/<比赛>/metadata.json`：botId、比赛编号、`gameNo/gamesPerTable`、策略 hash。
- `matches/<比赛>/frames.jsonl`：原始 `startGame/refreshData/closeGame` 帧。第一条 `startGame` 是唯一带地图和陨石多边形的帧（`data.map.blocks` / `data.map.borders`），离线避障就靠它，详见 `OFFICIAL_RULES.md`。
- `matches/<比赛>/commands.jsonl`：策略实际发出的动作。
- `matches/<比赛>/replay.ccreplay.json`：游戏“回放文件”页面可以直接打开的单文件录像。
- `matches/<比赛>/settlement.json`：本局结算。
- `matches/<比赛>/battle-data.json`：个人历史和赛事排名。

正式赛一桌打多局时，每一局各占一个目录，用 `metadata.json` 里的 `gameNo` 区分先后。

回放文件只包含服务端下发的公开状态和最终排名，不包含 AccessKey、策略源码、
个人历史战绩或任何玩家的 `attackValue`。收到 `closeGame` 时会先写出
`complete=false` 的可播放文件，收到 `matchFinished` 后原子更新为完整结算版本。

回放文件格式与 Node 版完全一致，两个版本录制的 `replay.ccreplay.json` 可以互相打开。

### 本地回放

在当前目录启动零依赖回放服务：

```bash
python3 tools/replay_server.py
```

浏览器打开 `http://127.0.0.1:9998/game?mode=replay`，点击游戏内的“选择文件”，
再选择 `runtime/matches/<比赛>/replay.ccreplay.json`。如需换端口，可运行
`REPLAY_PORT=10098 python3 tools/replay_server.py`。

回放页会从
`https://dev.g.alicdn.com/pengtianshun.pts/crazy-crash/0.0.1/project.bundle.js`
加载前端，并由本地服务代理同版本的图片、音频等素材。回放 JSON 始终由浏览器在
本机读取，不会上传。也可以直接双击 `tools/replay.html` 使用；若浏览器限制本地页面
加载 CDN 资源，请改用上述 `python3 tools/replay_server.py` 方式。

`runtime/`、`.venv/`、`__pycache__/` 和 `.env` 已加入 `.gitignore`，分发时无需包含。

## 常见状态

- `BOT_CONNECTED / LOBBY`：连接成功，等待中控分桌，不是卡住。
- `BOT_ALREADY_ONLINE`：同一 AccessKey 已在另一处在线；程序会直接退出，关闭旧进程后再启动。
- `BOT_AUTH_FAILED`：先确认输入格式为 `test:<纯数字工号>`；如果格式正确，说明当前环境可能没有开启测试 AK，需要使用正式 AccessKey。程序不会反复重连。
- `ROOM_NOT_OPEN`：大屏尚未打开，程序会在同一连接上自动重试。
- `BOT_NOT_ASSIGNED`：该正式赛房间不属于本队，程序会停止重试并留在大厅。
- `ROUND_BYE`：本轮轮空，不会进入房间。
- `SERIES_GAME_STARTED`：正式赛同桌的下一局开始，程序会自动进入新房间。
- `ROUND_FINISHED`：整轮结算完毕，日志里的 `advancementStatus` 是最终晋级结论。
- `STRATEGY_ERROR`：策略返回值不合法或代码抛错，请修改 `strategy.py`。

正式 AccessKey 是密钥。无论使用测试工号还是真实 AccessKey，都不要写进源码、URL、命令参数或提交到 Git。
