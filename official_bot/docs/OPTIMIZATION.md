# 安全的赛间 LLM 优化

优化器默认关闭，只在比赛边界运行，不会进入 100ms 实时策略循环。LLM 只能输出
白名单内的数值配置，不能修改 Python 代码。

## 实现流程

这里的 LLM 优化是“参数优化”，不是让模型直接重写策略代码。完整链路如下：

```text
一局结束
  -> analysis/match_report.py 生成 match-report.json
  -> bot.py 在自由赛的赛间边界调用 OptimizationManager
  -> LLM 读取本局报告、当前参数和允许范围
  -> LLM 返回最多四个数值参数
  -> 校验参数白名单、上下界和单次变化幅度
  -> 使用候选配置运行完整 check.py
  -> suggest 模式只保存候选；practice + auto 模式原子发布
  -> 下一局 startGame 时加载 active-config.json
```

LLM 不会参与每帧驾驶，也不会直接操作 WebSocket。调用超时、返回非法 JSON、参数
越界或测试失败时，当前稳定配置保持不变，BOT 仍会继续进入下一场。

主要实现文件：

- `optimization/manager.py`：提示词、校验、测试门禁、发布和回滚；
- `optimization/providers.py`：OpenAI-compatible API 和本地命令适配器；
- `strategy_core/config.py`：可调参数白名单及范围；
- `strategy_core/runtime.py`：下一局开场加载已发布配置；
- `bot.py`：在自由赛结算边界触发优化器。

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

具体行为：

| 阶段 | `suggest` | `auto` | 手工发布 |
| --- | --- | --- | --- |
| `practice` | 生成并测试候选 | 测试通过后发布 | 允许 |
| `elimination` | 冻结 | 冻结 | 拒绝 |
| `top16-adjust` | 生成并测试候选 | 不自动发布 | 允许 |

## LLM 接入

OpenAI-compatible 接口：

```bash
export WOLF_LLM_API_KEY='本地密钥'
export WOLF_LLM_MODEL='模型名'
export WOLF_LLM_BASE_URL='https://服务地址/v1'
export WOLF_OPTIMIZER_MODE='suggest'
export WOLF_PHASE='practice'
export WOLF_LLM_TIMEOUT_SECONDS='30'
export WOLF_OPTIMIZER_TOTAL_TIMEOUT_SECONDS='60'
```

当前 HTTP provider 请求 `${WOLF_LLM_BASE_URL}/chat/completions`，因此服务需要兼容
Chat Completions 请求和响应格式。API Key 通过 `Authorization: Bearer` 发送。

也可以用本地命令作为 provider。命令从 stdin 接收提示词，并向 stdout 输出 JSON：

```bash
export WOLF_LLM_COMMAND='python3 my_local_optimizer.py'
```

本地命令从 stdin 接收完整提示词，并向 stdout 输出一个 JSON 对象，例如：

```json
{
  "attack_margin": 42,
  "reserve_energy": 220
}
```

如果同时配置本地命令和 HTTP API，会优先使用 `WOLF_LLM_COMMAND`。

密钥不得写入配置、日志或 Git。

## 推荐首次接入步骤

先配置 provider，并保持建议模式：

```bash
export WOLF_OPTIMIZER_MODE='suggest'
export WOLF_PHASE='practice'
```

已有一场比赛报告后，可以不连接比赛平台，手动测试一次：

```bash
python3 -m optimization.cli \
  runtime/matches/<比赛>/match-report.json \
  --mode suggest \
  --phase practice
```

检查 `candidate-config.json`、`decisions.jsonl` 和命令输出，确认建议合理后再手工发布：

```bash
python3 -m optimization.cli --phase practice \
  --promote runtime/optimizer/candidate-config.json
```

建议先积累多场自由赛结果并比较候选效果，再把模式切换为 `auto`。

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

`decisions.jsonl` 中常见状态包括：

- `disabled`：优化器未启用；
- `no_provider`：没有配置 LLM provider；
- `suggested`：候选通过校验和测试，但尚未发布；
- `promoted`：自由赛自动模式已经发布；
- `frozen_phase`：当前比赛阶段禁止修改；
- `manual_promotion_required`：16 强调整窗口需要人工确认；
- `rejected`：输出、参数或测试未通过；
- `rolled_back`：已恢复上一份稳定配置。
