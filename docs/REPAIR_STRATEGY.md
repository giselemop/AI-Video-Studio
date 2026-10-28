# 人物质量 Repair Strategy

## 触发条件

以下任一条件触发回炉或人工复核：

- 静态图出现额外眼睛、瞳孔异常、嘴唇融合、脸型明显变形、重复人物或拼贴布局。
- 视频出现身份漂移、局部彩色伪影、ghosting、frame tearing、嘴眼突然放大或相邻帧结构突变。
- CPU face proxy 的 `frameVisualArtifactProxyPercent` > 0、`minFaceSimilarityToFirstFrame` < 90、或状态为 `Rejected`。
- 技术尺寸/时长/解码不满足预设，先修参数，不进入复杂动作。

## 分级回炉

| 等级 | 处理 | 允许范围 |
| --- | --- | --- |
| R0 | 同一 Master、同一动作、只换 seed | 最多 1 次 |
| R1 | guide/reference strength 保持 0.45，`guideFrameIndex=72`，画幅锁定 320×416，73 帧，`small` 动作，固定镜头 | 最多 1 次 |
| R2 | 动作降为眨眼/呼吸，时长回到约 3 秒，换用 `12_ltx_face_stable_v3_api.json` | 最多 1 次 |
| R3 | 仍失败则标记 `NeedManualReview`，禁止自动继续增大 CFG、动作幅度或时长 | 人工决定 |

## 已实现的记录

`quality_repair_runs` 保存 shot、retry task、issue code、策略、变更参数、结果状态和指标。自动 QA 回炉的 issue code 为 `FACE_DRIFT_OR_TEMPORAL_ARTIFACT`，当前策略为 `newSeed+guide0.45+guideFrame72+portrait320x416+73frames+smallMotion`。

## 不采用的修复

- 不通过无限重试掩盖身份漂移。
- 不把 5 秒失败样片强行插帧成“稳定视频”。
- 不用失败的全身重复人物图更新 Master。
- 不在当前机器上盲目下载 24GB 级模型、LoRA、ControlNet 或 FaceDetailer 节点。

## 人工放行规则

自动检查只负责发现硬性风险；人物身份、眼睛、嘴部、表情自然度、动作语义和跨镜头一致性仍需人工看首帧/中帧/尾帧。`NeedReview` 是设计状态，不是自动通过。
