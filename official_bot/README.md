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
- [官方 SDK README](docs/OFFICIAL_SDK_README.md)
- [官方规则](docs/OFFICIAL_RULES.md)
- [官方开发指南](docs/OFFICIAL_DEVELOPMENT_GUIDE.md)

本地回放服务：

```bash
python3 tools/replay_server.py
```
