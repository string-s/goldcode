# Goldcode / Wolf Python BOT

本仓库当前以 `official_bot/` 为唯一正式参赛主线。它基于官方 Python SDK，实现了
WebSocket 生命周期、Wolf 实时策略、轨迹规划、对手画像、自动赛后报告和安全的
赛间 LLM 参数优化。

## 快速开始

```bash
cd official_bot
python3 -m pip install -r requirements.txt
python3 check.py
CRAZY_CRASH_ACCESS_KEY='test:你的数字工号' python3 bot.py
```

## 目录

```text
goldcode/
├── official_bot/              # 正式参赛代码、测试、工具和文档
│   └── docs/source/           # 官方原始技术资料存档
└── legacy/                    # SDK 明确前的旧模拟器与早期策略研究
```

`legacy/` 不会被正式 BOT 导入，也不参与 `official_bot/check.py`。其中的模拟结果、
移动接口和 LLM 实时决策方案只用于回顾早期思路，不能当作当前比赛环境的真实结论。

## 主要文档

- [正式 BOT 使用说明](official_bot/README.md)
- [Wolf 策略实现](official_bot/docs/WOLF_STRATEGY.md)
- [比赛约束](official_bot/docs/COMPETITION_CONSTRAINTS.md)
- [赛间 LLM 参数优化](official_bot/docs/OPTIMIZATION.md)
- [旧版研究代码说明](legacy/README.md)

正式开发、测试和比赛操作都应在 `official_bot/` 中进行。
