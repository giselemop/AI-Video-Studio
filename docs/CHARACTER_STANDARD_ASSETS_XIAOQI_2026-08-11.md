# 小七角色标准资产与脸部稳定性基线

更新时间：2026-08-11

## 角色固定信息

- 角色：小七 / Xiaoqi
- 年龄：17 岁
- 脸部：清瘦少年脸，鼻梁有晒斑
- 发型：蓬松深棕短发
- 服装：褪色橙色连帽衫，深蓝背包，护膝
- 体型：清瘦、敏捷
- 主身份规则：所有正式镜头优先复用单脸 `identity-front` 锚点；全身图只作为身体比例、服装和构图参考，不覆盖脸部锚点。

## 标准资产

| 用途 | 文件 |
|---|---|
| 清晰脸部 / 正面身份锚点 | `C:\install\AI\Data\Characters\8\standard\face_closeup.png` |
| 正面身份锚点副本 | `C:\install\AI\Data\Characters\8\standard\identity_front.png` |
| 正面半身 | `C:\install\AI\Data\Characters\8\standard\front_half_body.png` |
| 正面全身构图 | `C:\install\AI\Data\Characters\8\standard\front_full_body.png` |

数据库中的角色参考图已更新为：

`C:\install\AI\Data\Characters\8\ref_20260811_092034_8f43f975.png`

历史三张拼图/多脸参考图保留用于审计，但不再作为角色锚点。角色参考路径查询已改为“单脸锚点优先、最新锚点优先”。当镜头同时存在场景参考和角色参考时，I2V 的唯一 Guide 位优先给角色参考，避免场景图覆盖脸部身份。

## 固定生成配置

- 静态图模型：`v1-5-pruned-emaonly-fp16.safetensors`
- 静态图工作流：`C:\install\AI\Workflows\01_portrait_quality_api.json`
- 角色参考重绘工作流：`C:\install\AI\Workflows\06_character_standard_reference_api.json`
- I2V 身份锁定工作流：`C:\install\AI\Workflows\03_ltx_character_lock_api.json`
- I2V 视频模型：`ltxv-2b-0.9.8-distilled-fp8.safetensors`
- 文本编码器：`t5xxl_fp8_e4m3fn_scaled.safetensors`
- LoRA：当前没有已扫描的角色 LoRA，保持 0 个，不叠加随机 LoRA
- 默认静态 Seed：`810811`
- 静态图基线：`640x832`、30 steps、CFG 5.5～6.0、单人正面半身/中近景
- I2V Draft 基线：`320x416`、73 帧、24 fps、约 3 秒、锁定镜头、一次眨眼/轻微呼吸/小于 8° 慢转头

## 固定正向 Prompt 核心

`single subject, preserve the exact face, eye shape, natural eyelids and pupils, nose, lips, jawline, hairstyle and clothing from the input image, 17-year-old East Asian boy, slim youthful face, small freckles across the bridge of the nose, fluffy dark brown short hair, faded orange hoodie, dark blue backpack straps, knee pads, photorealistic live-action film still, stable facial identity`

## 固定 Negative Prompt 核心

`multiple people, duplicate person, split screen, collage, contact sheet, extra face, extra eyes, asymmetrical eyes, crossed eyes, malformed pupils, deformed eyelids, warped mouth, fused lips, distorted jaw, cropped face, face occlusion, identity drift, face morphing, changing hairstyle, changing clothing, flicker, jitter, ghosting, motion smear, frame tearing, fast zoom, pan, orbit, camera shake, low quality, cartoon, CGI, text, watermark`

## 生产门禁

1. Draft 静态候选：生成 2～4 张，先看脸，不以文件尺寸通过代替视觉复核。
2. 关键帧 QA：拼图/分屏/多脸、眼睛明显不对称、嘴部/脸型变形、目标身份明显变化直接拒绝；正常候选仍标记 `NeedReview`，必须人工选图。
3. Draft I2V：只允许角色参考优先、3～5 秒、小动作、低镜头运动。
4. 视频 QA：检查画幅匹配、首帧相似度、最低帧相似度、相邻帧相似度、身份漂移代理值、脸部结构突变和异常帧。
5. Draft 通过后才进入 Final；失败重试必须改变参考图优先级、动作幅度、时长或 I2V 参数，不能只随机换 Seed。

## 本机验证记录

- 任务 592/593：两张正面候选均生成 `640x832`，候选状态为 `NeedReview`，脸部 QA 信息已写入 `qcJson`。
- 任务 590：同一张小七脸图 + LTX 角色参考，3 秒 Draft；脸部相似度代理 `97.07%`，最低 `93.91%`，身份漂移 `2.93%`，异常帧 `0`。
- 任务 591：同一张输入但 Wan 无角色参考；中后段出现明显彩色/结构伪影，脸部 QA 判为 `Rejected`。
- 任务 594：场景参考排在角色参考前，出现中段眼睛放大、末段脸部消失；用于确认参考顺序问题。
- 任务 597：角色参考优先 + 稳定 Prompt + 3 秒 Draft；实际 `320x416`、约 `3.32s`，脸部相似度代理 `95.11%`，最低 `91.8%`，身份漂移 `4.89%`，异常帧 `0`，Shot 46 质量分 `94.47`。

当前没有 FaceDetailer、ADetailer、IP-Adapter 或现成角色 LoRA，因此 CPU QA 代理不能替代真正的人脸关键点/身份模型；所有候选和视频仍保留人工复核门禁。这是本机 RTX 4070 12GB 下不扩容模型的安全取舍。
