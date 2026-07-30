# Wolf 官方 Python BOT

这里是实际连接比赛平台的 Python Agent。项目以官方 SDK 为基础，连接、认证、
分桌、重连、100ms 指令限频和战斗数据录制均保留官方实现；Wolf 代码主要位于
`strategy.py` 与 `strategy_core/`。

## 快速开始

```bash
python3 -m pip install -r requirements.txt
python3 check.py
CRAZY_CRASH_ACCESS_KEY='test:你的数字工号' python3 bot.py
```

macOS 也可以双击 `启动BOT.command`，Windows 可以双击 `启动BOT.cmd`。

## 目录

```text
official_bot/
├── bot.py                 # 官方 Agent 运行器；只增加策略生命周期钩子
├── strategy.py            # 官方实时策略入口
├── strategy_core/         # Wolf 状态机、记忆、几何与单指令控制器
├── analysis/              # 自动赛后报告与后续优化入口
├── storage/               # SQLite 稳定 ID 对手画像
├── tests/                 # 策略、生命周期和回放测试
│   └── fixtures/          # 官方帧样例
├── tools/                 # 回放录制器、回放服务和页面
├── docs/                  # 官方资料、Wolf 设计和比赛约束
├── check.py               # 一键语法与测试检查
└── requirements.txt
```

## 开发红线

- 不修改 `COMMAND_INTERVAL_MS` 的正式默认值和限频判断。
- 不修改 5 秒心跳，也不自建 WebSocket 或连发任务。
- `choose_command` 必须同步、快速，每帧只返回一条合法指令。
- 淘汰赛阶段不能重启进程；进入 16 强前只有约 10 分钟调整窗口。
- 正式 AccessKey 只通过安全输入或 Secret 环境变量提供，不写入仓库。

## 文档

- [Wolf 策略实现](docs/WOLF_STRATEGY.md)
- [已确认的比赛约束](docs/COMPETITION_CONSTRAINTS.md)
- [安全的赛间 LLM 优化](docs/OPTIMIZATION.md)
- [官方 SDK README](docs/OFFICIAL_SDK_README.md)
- [官方规则](docs/OFFICIAL_RULES.md)
- [官方开发指南](docs/OFFICIAL_DEVELOPMENT_GUIDE.md)

本地回放服务：

```bash
python3 tools/replay_server.py
```

每局结算后会在对应的 `runtime/matches/<比赛>/` 中生成：

- `match-report.json`：供程序和 LLM 使用的结构化指标；
- `match-report.md`：便于人工快速阅读的复盘摘要。

`commands.jsonl` 中除实际指令外，还会记录模式、目标、攻击估计和决策原因。

车辆控制器会对候选转向轨迹做短期采样，并结合车身安全半径、地图多边形、
非目标对手和边界风险选择动作；碰撞后会主动脱离，并在约 1.5 秒冷却期间避免
重复追撞同一目标。相关物理参数仍需使用真实自由赛回放校准。

稳定对手 ID 的攻击画像保存在 `runtime/wolf-profiles.sqlite3`。数据库只在比赛
开始和结算边界访问：自由赛默认读写，正式非自由赛默认只读。策略还会结合
`gameNo/gamesPerTable`、此前局分和平均局分，在 `STEADY`、`MUST_SCORE` 与
`PROTECT_SERIES` 三种系列赛姿态间切换。

画像模式可用 `WOLF_PROFILE_MODE=auto|read-write|read-only` 控制；比赛环境建议
保持默认 `auto`。

赛间优化器默认关闭。启用后也只允许调整白名单 JSON 参数，候选必须通过范围校验
和完整测试才可发布；淘汰赛阶段会冻结。配置、provider 和回滚方式见
`docs/OPTIMIZATION.md`。
