# Legacy 离线研究代码

这个目录保存官方 SDK 和真实车辆控制接口明确之前完成的第一代研究框架。保留它的
目的是追溯策略来源、运行简单自博弈，以及在需要时参考早期状态机思路；它不是正式
参赛 BOT 的依赖。

## 包含内容

- `agents/`：旧状态机、基线对手和早期 LLM 实时高层决策实验；
- `sim/`：根据早期规则假设编写的二维移动模拟器；
- `prompts/`：旧版“Prompt 即 Agent”实验提示词；
- `run_match.py`：运行一桌旧模拟比赛；
- `tournament.py`：旧模拟器的循环赛和参数扫描；
- `adapter_guide.md`：官方 SDK 尚未确定时编写的接入设想。

## 与正式实现的区别

旧代码输出二维移动向量，并依赖自行假设的物理模型。当前正式实现位于
`../official_bot/`，使用官方单指令车辆控制、真实生命周期和官方数据结构。

特别注意，`agents/llm_brain.py` 研究的是让 LLM 参与实时高层决策；当前正式方案的
LLM 只在赛间分析报告并调整白名单参数，两者没有运行时关联。

如果需要运行旧模拟器，可在仓库根目录执行：

```bash
python3 legacy/run_match.py
python3 legacy/tournament.py
python3 legacy/tournament.py --sweep
```

旧模拟结果只能作为历史参考，不能替代官方自由赛回放与真实参数校准。
