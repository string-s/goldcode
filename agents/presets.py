# -*- coding: utf-8 -*-
"""四个战术预设：同一架构，不同参数。晋级局用 balanced/vulture，决赛切 aggro。"""
from .statemachine import FireflyAgent

PRESETS = {
    # 激进：高频高价，决赛抢分用
    "aggro": dict(PROBE_LO=180, PROBE_HI=280, OFFSET=55, RESERVE=120,
                  ALLIN_TAIL=9.0, KILL=3, PROTECT_LEAD=99),   # 永不龟缩
    # 均衡：默认晋级配置
    "balanced": dict(),
    # 龟缩偷袭：避战 + 窗口尾偷分，测试"苟分流"上限
    "turtle": dict(PROBE_LO=80, OFFSET=25, RESERVE=400, ALLIN_TAIL=5.0,
                   CLUSTER_R=12.0, PROTECT_T=0.0, PROTECT_LEAD=-99),
    # 秃鹫：记账猎杀权重拉满
    "vulture": dict(VULTURE_MARGIN=25, RESERVE=320, OFFSET=30,
                    ALLIN_TAIL=6.0, PROBE_LO=100),
}


def make(preset: str, seed=7) -> FireflyAgent:
    return FireflyAgent(cfg=PRESETS[preset], name=preset, seed=seed)
