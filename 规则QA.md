# 规则宣讲&QA

# 游戏规则

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/54Lq35kaYx87gl7E/img/2b024ad0-a78c-4b65-9c08-acd54c2def23.png)

详细规则可见：[《萤火森林｜ Agent 对抗赛规则说明》](https://alidocs.dingtalk.com/i/nodes/MNDoBb60VLYDGNPytm3DMZAAJlemrZQ3?utm_scene=person_space)

# 快速开始

## 整体介绍

通过 WebSocket 连接至游戏平台，基于平台下发的数据完成策略设计，并推送指令驱动精灵行为。

### 下发信息

入房后等待服务端发送 `startGame`，不要用 `roomEntered` 作为开车信号：

```json
{
  "commandType": "startGame",
  "timeStamp": 1784614800000,
  "data": {
    "map": {
      "width": "<地图宽度>",
      "height": "<地图高度>",
      "borders": [
        [
          [
            { "x": "<坐标X>", "y": "<坐标Y>" },
            { "x": "<坐标X>", "y": "<坐标Y>" }
          ]
        ]
      ],
      "blocks": [
        [
          [
            { "x": "<坐标X>", "y": "<坐标Y>" },
            { "x": "<坐标X>", "y": "<坐标Y>" }
          ]
        ]
      ]
    },
    "rabbits": [ ]

  }
}
```

后续约每 100 ms 收到一帧：

```json
{
  "commandType": "refreshData",
  "timestamp": 1784614800100,
  "data": {
    "rabbits": [ ],

    "goldCarrot": null
  }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `rabbits` | array | 当前所有精灵状态 |
| `goldCarrot` | object/null | 森林之心； |

 **rabbits 的每个元素说明如下：**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `**id**` | **string** | **精灵/Agent 标识** |
| `name` | string | 展示名称 |
| `**position**` | `**{x,y}**` | **中心位置** |
| `velocity` | `{x,y}` | 当前速度向量 |
| `angle` | number | 朝向角 |
| `speed` | number | 移动速度 |
| `angularSpeed` | number | 转向角速度大小（标量，非二维向量） |
| `width` / `height` | number | 精灵包围尺寸 |
| `**score**` | **number** | **当前发光果实数量** |
| `**energy**` | **number** | **当前剩余能量** |
| `active` | boolean | 是否处于活动状态 |
| `moveState` | string | 移动状态 |
| `dirState` | number | 转向枚举：-1 左转、0 直行、1 右转 |
| `attacking` | boolean | 是否处于攻击/碰撞表现状态 |
| `rebounding` | boolean | 是否正在反弹 |
| `reboundAngle` | number | 反弹方向相关角度 |
| `**invincible**` | **boolean** | **是否处于森林之心增益状态** |
| `deathCount` | number | 本局淘汰次数；正常为 0 或 1 |
| `survivalTime` | number | 生存时间统计 |

示例：

```json
{
  "id": "1001",
  "name": "萤火小队",
  "position": {"x": 320.5, "y": 460.0},
  "velocity": {"x": 4.8, "y": -0.7},
  "angle": 1.42,
  "speed": 5,
  "width": 52,
  "height": 30,
  "score": 12,
  "energy": 740,
  "active": true,
  "rebounding": false,
  "invincible": false,
  "deathCount": 0
}
```

**goldCarrot（森林之心）**

```json
{
  "x": 720,
  "y": 410
}
```

goldCarrot={} 或 goldCarrot=null 表示当前没有可拾取的森林之心

### 控制指令

| commandType | 作用 | data |
| --- | --- | --- |
| `goForward` | 向车头方向前进 | 不需要 |
| `goBack` | 倒车 | 不需要 |
| `turnLeft` | 向左转向 | 可选；建议 0.01～0.1 |
| `turnRight` | 向右转向 | 可选；建议 0.01～0.1 |
| `stop` | 停止移动 | 不需要 |
| `steerBack` | 回正方向盘/停止持续转向 | 不需要 |
| `setAttackValue` | 设置下一次碰撞使用的攻击强度 | 数值字符串；不得为负数 |

示例：

```json
{"commandType":"goForward"}
{"commandType":"turnLeft","data":"0.05"}
{"commandType":"steerBack"}
{"commandType":"setAttackValue","data":"80"}
{"commandType":"stop"}
```

实现约束：

*   运动具有持续状态。一次 `goForward` 会持续生效，直到收到相反/停止指令或被碰撞状态暂时打断；转向同理。
    
*   转向量建议限制在 0.01～0.1，当前默认值为 0.05。发送异常值不会带来额外能力，可能造成行为不可控。
    
*   `setAttackValue` 设置的是期望攻击强度；实际攻击强度为“设定值与当前能量中的较小值”。例如剩余能量 30、设定 80，实际只按 30 结算并消耗 30。
    
*   不要逐帧重复发送同一指令。仅在策略状态变化时发送，可减少延迟和无意义消息。
    

[《技术细则说明》](https://alidocs.dingtalk.com/i/nodes/YMyQA2dXW7gYo6MzcZdROY0KWzlwrZgb?cid=524669617%3A4472971995&utm_source=im&utm_scene=person_space&iframeQuery=utm_medium%3Dim_card%26utm_source%3Dim&utm_medium=im_card&corpId=dingd8e1123006514592)

## 平台介绍

[https://pre-young-hackathon.alibaba-inc.com/?wsPath=%2Fscreen](https://pre-young-hackathon.alibaba-inc.com/?wsPath=%2Fscreen)

#### SDK 连接

[请至钉钉文档查看附件《SDK连接.mp4》。](https://alidocs.dingtalk.com/i/nodes/G1DKw2zgV2KnvL4kFqd9NPyxJB5r9YAn?cid=75904830226&corpId=dingd8e1123006514592&iframeQuery=anchorId%3DX02ms63hj701z5a163a4jy&utm_medium=im_card&utm_scene=person_space&utm_source=im)

#### 平台介绍

[请至钉钉文档查看附件《平台介绍.mp4》。](https://alidocs.dingtalk.com/i/nodes/G1DKw2zgV2KnvL4kFqd9NPyxJB5r9YAn?cid=75904830226&corpId=dingd8e1123006514592&iframeQuery=anchorId%3DX02ms63iigryz3ab2jhouh&utm_medium=im_card&utm_scene=person_space&utm_source=im)

#### 回放功能

[请至钉钉文档查看附件《回放功能.mp4》。](https://alidocs.dingtalk.com/i/nodes/G1DKw2zgV2KnvL4kFqd9NPyxJB5r9YAn?cid=75904830226&corpId=dingd8e1123006514592&iframeQuery=anchorId%3DX02ms63inwzkf4ic6pzhzl&utm_medium=im_card&utm_scene=person_space&utm_source=im)

## SDK

比赛方会提供 Python、JavaScript 和 Java 三种版本的参赛 SDK。大家可以选择自己熟悉的语言直接开始开发。

SDK 已经处理好比赛服务连接、身份认证、分桌、进房、断线重连和比赛数据保存。参赛人员不需要从零搭建完整的 BOT，主要关注自己的战斗策略即可。

除了使用官方 SDK，也可以把比赛规则、通信协议和 SDK 示例交给 AI，让 AI 理解整体逻辑后，使用任意编程语言开发自己的 BOT。

| JS | Python | Java |
| --- | --- | --- |
| [请至钉钉文档查看附件《participant-bot-starter.zip》。](https://alidocs.dingtalk.com/i/nodes/G1DKw2zgV2KnvL4kFqd9NPyxJB5r9YAn?cid=75904830226&corpId=dingd8e1123006514592&iframeQuery=anchorId%3DX02ms6abe24fozdsqlktk&utm_medium=im_card&utm_scene=person_space&utm_source=im) | [请至钉钉文档查看附件《participant-bot-starter-python.zip》。](https://alidocs.dingtalk.com/i/nodes/G1DKw2zgV2KnvL4kFqd9NPyxJB5r9YAn?cid=75904830226&corpId=dingd8e1123006514592&iframeQuery=anchorId%3DX02ms6abk2k6wm4jlof68q&utm_medium=im_card&utm_scene=person_space&utm_source=im) | [请至钉钉文档查看附件《participant-bot-starter-java.zip》。](https://alidocs.dingtalk.com/i/nodes/G1DKw2zgV2KnvL4kFqd9NPyxJB5r9YAn?cid=75904830226&corpId=dingd8e1123006514592&iframeQuery=anchorId%3DX02ms6abofohgarr2322gb&utm_medium=im_card&utm_scene=person_space&utm_source=im) |

# 赛程

## 整体安排

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/54Lq35kaYx87gl7E/img/7b0738a4-4f90-4e85-84c0-547b3aad23ce.png)

练习赛阶段：不实际

正式赛阶段：随机成桌，每桌 **4 支队伍。**按 **4 进 2** 规则进行，每桌 **前 2 名** 晋级下一轮。**直到最后4强，按名次决出 冠军、亚军、季军。**

## 积分规则

每组比赛 3轮，每轮按照得最终排名进行积分，第一名 积3分，第二名 积2分，第三名 积1分，第四名 0分。

总积分榜按照各小组赛每队积分进行排名

*   如总积分相同者取发光果实多者
    
*   总积分与发光果实数相同者进行随机PK（运气也是实力的一部分）
    

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/3BMqYy574jVeEqwZ/img/15d80928-d7d5-4188-856c-215198f22ec3.png)

# QA

任何疑惑，随时提问～