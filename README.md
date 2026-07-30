# 萤火森林 Agent 挑战赛 —— 完整备赛框架

三种赛制形态全覆盖，比赛日只写一个适配层即可上场。

## 目录结构
```
firefly_forest/
├── official_bot/           # 官方 Python SDK + Wolf 真实参赛实现
├── sim/
│   ├── views.py            # 适配层协议：Observation/Action（策略层唯一依赖）
│   └── engine.py           # 规则复刻模拟器（不确定项全部做成 SimConfig 开关）
├── agents/
│   ├── base.py             # SafeAgent 安全包装（永不裸崩）+ 4 个陪练基线
│   ├── statemachine.py     # 【形态A主力】七模式状态机 + 记账 + 走位三原语
│   ├── presets.py          # aggro / balanced / turtle / vulture 一键切换
│   └── llm_brain.py        # 【形态B/C】LLM高层决策 + 代码走位 + 三层兜底
├── prompts/
│   └── battle_prompt.md    # 【形态B】"Prompt 即 Agent"直接粘贴版（含裁剪指南）
├── run_match.py            # 单场对局 + 事件日志 + 果实守恒校验
├── tournament.py           # 自博弈循环赛 + 参数网格扫描
└── adapter_guide.md        # 比赛日 15 分钟接入指南 + 侦察清单
```

## 快速开始
```bash
python3 run_match.py              # 跑一局：主力 vs 追击/龟缩/随机
python3 run_match.py --verbose    # 附完整事件日志
python3 tournament.py             # 四预设互打 + 对抗典型对手池
python3 tournament.py --sweep     # OFFSET/ALLIN_TAIL/RESERVE 网格扫描
```

## 官方 Python BOT

`official_bot/` 是当前真实参赛主线。它基于官方 Python starter，保留 SDK 的
WebSocket、认证、分桌、重连、100ms 限频、数据录制和回放能力，并将原有高层
状态机迁移为适配车辆控制与单命令约束的 Wolf 策略。

```bash
cd official_bot
python3 -m pip install -r requirements.txt
python3 check.py
```

实现结构、运行方式和当前限制见 `official_bot/docs/WOLF_STRATEGY.md`。原有 `sim/`、
`agents/` 和 `tournament.py` 暂时保留为离线研究工具，其胜率不能代替官方环境
中的真实训练结果。

## 本仓库自博弈实测结论（赛前先验，现场按侦察结果校准）
1. **对抗普通对手池**（追击流/龟缩流/固定价——大多数队伍的真实水平）：
   四个预设全部 100% 晋级率，桌冠率 92%~100%。
2. **高手互殴局**：aggro 桌冠率最高(42%)，turtle 晋级率最高(75%)
   —— 印证"晋级局求稳、决赛切激进"的赛程策略。
3. **参数扫描**：ALLIN_TAIL=9 秒的组合霸榜前三 —— **窗口尾清仓是被数据
   证实的第一优先级策略**；OFFSET≈35 最优；RESERVE 影响较小。
4. LLM 形态在 **40% 故障率注入**下仍 6/6 晋级 —— 三层兜底
   （LLM→状态机→安全游走）有效。

## 策略核心（写进代码的六个洞察）
1. 能量过期作废 -> 每个 30 秒窗口尾部全额清仓（ALLIN_TAIL）
2. 果实贵于能量 -> 压价不超杀（众数 + OFFSET + JITTER 抖动防平局）
3. 对手能量可记账 -> 秃鹫必胜价收割（Ledger，能量不可见时用胜负推断）
4. 漏分比得分致命 -> 避障硬否决 + 紧急制动 + 防 -3 优先级链
5. 森林之心 = 最大单一分源 -> RAMPAGE 连撞 / EVADE 拉距 / RACE 判定
6. 4 进 2 赛制 -> PROTECT 保排名模式 + 补刀送人头（KILL 阈值）

## 免责与校准提醒
物理参数（场地、速度、半径、心刷新节奏）是猜的，规则未明说项都做成了
`SimConfig` 开关。**结论的可信度排序：策略结构 > 参数相对关系 > 绝对数值。**
开赛侦察清单（见 adapter_guide.md）逐项确认后，模拟器与实战的差距会快速收敛。
