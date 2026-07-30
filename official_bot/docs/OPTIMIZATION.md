# 安全的赛间 LLM 优化

优化器默认关闭，只在比赛边界运行，不会进入 100ms 实时策略循环。LLM 只能输出
白名单内的数值配置，不能修改 Python 代码。

## 模式与阶段

```text
WOLF_OPTIMIZER_MODE=off       默认，不调用 LLM
WOLF_OPTIMIZER_MODE=suggest   生成并测试候选，不自动启用
WOLF_OPTIMIZER_MODE=auto      自由赛中测试通过后原子启用

WOLF_PHASE=practice           允许 suggest/auto
WOLF_PHASE=elimination        完全冻结
WOLF_PHASE=top16-adjust       只允许 suggest，候选需人工确认后发布
```

每次最多修改四个参数，必须在 `strategy_core/config.py` 的范围内，单次变化不得超过
当前值的 50%。候选会先运行完整 `check.py`，失败时保持当前版本。

## LLM 接入

OpenAI-compatible 接口：

```bash
export WOLF_LLM_API_KEY='本地密钥'
export WOLF_LLM_MODEL='模型名'
export WOLF_LLM_BASE_URL='https://服务地址/v1'
export WOLF_OPTIMIZER_MODE='suggest'
```

也可以用本地命令作为 provider。命令从 stdin 接收提示词，并向 stdout 输出 JSON：

```bash
export WOLF_LLM_COMMAND='python3 my_local_optimizer.py'
```

密钥不得写入配置、日志或 Git。

## 文件

```text
runtime/optimizer/
├── active-config.json       下一局开场加载
├── previous-config.json     上一稳定配置
├── candidate-config.json    最近候选
├── decisions.jsonl          完整优化审计日志
└── history/                 历史候选
```

## 手动操作

根据一场报告生成建议：

```bash
python3 -m optimization.cli runtime/matches/<比赛>/match-report.json --mode suggest
```

16 强调整窗口人工检查后发布候选：

```bash
python3 -m optimization.cli --phase top16-adjust \
  --promote runtime/optimizer/candidate-config.json
```

回滚：

```bash
python3 -m optimization.cli --rollback
```

自由赛自动模式会在报告生成后、发送 `readyForNextMatch` 前运行；超时、无 provider、
非法输出或测试失败都会继续使用当前稳定配置。
