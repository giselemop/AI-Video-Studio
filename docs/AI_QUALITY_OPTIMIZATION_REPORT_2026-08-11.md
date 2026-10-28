# AI Video Studio 人物质量优化实施报告（2026-08-11）

## 结论摘要

- 当前问题同时存在于静态图和 I2V，但主要生产风险在 I2V 的 5 秒动作阶段。
- 静态 SD1.5 可以生成正常人脸；文本跨构图不能稳定保持同一身份，全身构图还会出现重复人物/重影。
- 当前默认已切换为 `12_ltx_face_stable_v3_api.json`：320×416、73 帧、约 3 秒、guide 0.45，并将参考约束帧固定到尾帧前第 72 帧；锁定镜头、small motion。
- `10_ltx_face_stable_v2_api.json` 已验证不优于旧版，不作为默认。
- 20 个连续静态任务全部成功；安全增强任务 645 输出 1920×1080/24 FPS，默认不插帧、不去闪烁，首帧保留竖图内容并以补边输出。

## 已落地变更

1. 增加 `08`～`12` 版本化工作流，其中 `12` 是已验证旧版结构的稳定生产版本。
2. 角色参考图按单脸身份、三分之四侧脸、半身构图分层保存；拒绝全身失败候选进入 Master。
3. 增加 I2V Preflight：输入首帧、角色参考、可读性、静态脸部代理、工作流、画幅、帧数、时长、动作档位和 GPU 余量检查。
4. 增加质量实验、Golden Sample、Repair Run 表和 API，保存测试变量与指标。
5. 修正 Shots 查询优先返回 `final_video_path`/`video_path`，避免前端显示旧资产。
6. 修正角色参考任务使用角色 Master Workflow；场景参考仍使用场景参考工作流。
7. 结果表写入 `quality_score` 和 `qc_json`，后续推荐可基于真实输出而非空分数。
8. Enhance 默认改为安全缩放/补边/转码，`deflicker` 和 `interpolate` 显式开启才执行。
9. VideoStudio 新建镜头优先选 v3 人物 I2V，并在工作流页面展示质量预设。

## 资源回归

20 个静态人物任务：625～644。

| 指标 | 结果 |
| --- | ---: |
| 成功 | 20 |
| 失败 | 0 |
| 取消 | 0 |
| 平均耗时 | 约 6156 ms |
| 最大任务显存峰值 | 3355 MiB |
| 最低任务记录空闲显存 | 8926 MiB |
| 开始/结束 ComfyUI | 在线 / 在线 |
| 开始/结束 GPU 空闲 | 10960 / 10964 MiB（nvidia-smi） |
| 开始/结束系统可用内存 | 20329 / 19464 MiB |

磁盘抽查：C: 当前可用约 190.53 GiB；`C:\install\AI\Data` 约 3.03 GiB、807 个文件，日志约 0.01 GiB。当前未执行自动清理，避免误删历史任务、Golden Sample 或模型；后续应增加按项目/版本的保留策略。

该结果证明当前单 GPU 串行队列可以持续完成 20 个静态任务；不代表 5 秒复杂 I2V 已通过，也不代表公网/多用户部署已通过。

## 推荐工作流

```text
角色单脸 Master
  -> 静态半身/近景候选 2 张
  -> CPU Face Preflight + 人工首帧确认
  -> I2V v3 Draft（3 秒 / 73 帧 / 锁定镜头）
  -> 首帧、中帧、尾帧人工检查
  -> 通过后才尝试显式 5 秒实验档
  -> 安全 Enhance（24 FPS、补边、无默认插帧）
  -> Shot QA / Episode QA / 人工锁定
```

## 未完成或保持人工的内容

- 当前没有 FaceDetailer/ADetailer、IP-Adapter、ControlNet 或独立人脸修复模型；没有重新安装或下载。
- 5 秒转头、推镜和走路在当前 LTX 2B 配置下没有达到默认门槛；应拆成 3 秒片段或继续单变量实验。
- 全身人物工作流没有通过，先保持半身/中近景。
- CPU face proxy 不是真正的人脸 landmark/identity 模型，所有结果仍需人工复核。

## 2026-08-11 有效 I2V 回归与尾帧参考约束修复

### 发现的工程问题

- 第一轮 20 次技术回归（任务 655～674）虽然全部生成成功，但 `SamplerCustom.noise_seed` 没有被服务端覆盖，20 个视频实际重复；该批结果保留为问题证据，不作为随机种子回归结论。
- 修复 `ComfyUiClient.PatchWorkflow` 对 `SamplerCustom.noise_seed` 的注入，并在回归脚本中增加视频/中帧 SHA-256 多样性门禁；不同种子若输出重复，脚本直接失败。
- 同一种子 920501 的中点参考约束（第 36 帧）在尾帧出现明显双眼重影和脸部结构模糊；只改动作 Prompt 或把 guide 强度从 0.45 提到 0.60 都没有解决。
- 配对实验显示“无眨眼、仅呼吸”也不能修复该种子，避免把问题误判为动作 Prompt；真正有效的最小变量是参考约束帧位置。

### 配对实测

| 变量 | 任务 | 成功 | 脸部拒绝 | 平均脸部分数 | 最低脸部分数 | 唯一视频哈希 | 最大显存峰值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 中点参考 `guideFrameIndex=36` | 677～696 | 20/20 | 1 | 94.14 | 92.77 | 20/20 | 11964 MiB |
| 尾帧前参考 `guideFrameIndex=72` | 721～740 | 20/20 | 0 | 95.15 | 92.88 | 20/20 | 11988 MiB |

- 两轮使用同一输入、同一模型、同一画幅/帧数/Prompt/种子（920500～920519），仅改变参考约束帧位置。
- 任务 678 的尾帧眼部重影在任务 722 的对应尾帧中消失；抽帧人工检查与 CPU 代理结果一致。
- 默认 I2V、QA 自动回炉、前端排队参数、预设和工作流文件均已切换到 `guideFrameIndex=72`；不引入新模型、不重新安装环境。
- 服务重启后的默认烟囱任务 741 通过：Preflight 通过、`noise_seed=920801`、ComfyUI 实际 `frame_idx=72`、脸部代理 95.50、无拒绝。

### 当前执行边界

- 该修复确认了 3 秒锁定镜头 Draft 的主要 I2V 尾帧风险，但不等于 5 秒转头、推镜或走路已通过。
- 仍需人工查看首帧/中帧/尾帧；CPU face proxy 不能替代 landmark/identity 模型。

### 2026-08-11 继续优化：5 秒复杂动作、身份矩阵与身份控制模型

- 5 秒 `controlled-complex` 边界实测未通过：任务 745 的脸部代理 88.58、身份漂移代理 11.18；任务 746 的脸部代理 91.25、身份漂移代理 8.28。抽帧显示手部穿脸、服装/手部幻觉和局部结构伪影。当前 RTX 4070 12GB + LTX 2B 的安全上限仍是 5 秒单一克制动作、锁定镜头、手部不经过脸部；复杂多动作应拆成 3 秒片段。
- 有效的 10 动作 × 5 场景静态身份基线已重建：报告为 `logs/identity_consistency_matrix_20260811_232134_final.json`，任务 802～851，50/50 成功、0 脸部代理拒绝、参考相似度代理均值 95.82、最低 94.65、50 个唯一输出哈希；10 个动作各 5 个单元，5 个场景各 10 个单元。该基线使用 `09_character_master_reference_v2` 的人物锚点 img2img；场景参考图已记录但尚未注入。
- 已接入 ComfyUI 官方 IP-Adapter Plus 节点目录 `ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus`，新增 `13_sd15_ipadapter_face_v1_api.json`。实际任务 902 使用工作流 712，ComfyUI 节点包含 `IPAdapterUnifiedLoader` 和 `IPAdapter`，参考相似度代理 97.32，显存峰值 4742 MiB；前端使用的 camelCase `workflowId` 绑定也已修复并验证。
- 已接入 SD1.5 OpenPose ControlNet 模型和 `14_sd15_controlnet_openpose_v1_api.json`。任务 903 使用工作流 713，节点包含 `ControlNetLoader` 和 `ControlNetApplyAdvanced`，显存峰值 4150 MiB；任务 904 在没有 `controlImages/controlImagePath` 时被服务端阻断，没有回退到普通生成。任务 903 使用人物图作 loader smoke，不能替代真实 OpenPose 姿态图验收。
- LoRA 入口已接入：模型目录扫描会登记 `Models/loras`，任务可通过 `loraIds`、`loraName/loraNames` 和 `loraStrengthModel/loraStrengthClip` 选择；服务端会动态串接 `LoraLoader`，找不到真实 LoRA 文件时阻断。当前本机 LoRA 目录为空，因此尚无真实 LoRA 质量结论，也没有重新安装环境。

### IP-Adapter 完整身份矩阵结果

- IP-Adapter Plus 版本的完整 10 动作 × 5 场景结果：`logs/identity_consistency_matrix_20260811_233807_final.json`，任务 905～954，全部绑定工作流 712。
- 50/50 成功、0 脸部代理拒绝、平均脸部代理 100、参考相似度代理均值 97.17、最低 96.44、50 个唯一输出哈希；10 个动作各 5 个单元，5 个场景各 10 个单元全部完成。
- 与同输入/同画幅/同动作集合的 `09_character_master_reference_v2` 基线相比，参考相似度代理均值提高 1.35，最低值提高 1.79；这只证明静态关键帧阶段的代理指标改善，不等于 IP-Adapter 进入 I2V 后的 5 秒复杂动作已通过。
- 当前已校验模型文件：`ip-adapter-plus-face_sd15.safetensors` SHA-256=`1C9EDC21AF6F737DC1D6E0E734190E976CFACF802D6B024B77AA3BE922F7569B`；`CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` SHA-256=`6CA9667DA1CA9E0B0F75E46BB030F7E011F44F86CBFB8D5A36590FCD7507B030`；`control_v11p_sd15_openpose.pth` SHA-256=`DB97BECD92CD19AFF71352A60E93C2508DECBA3DEE64F01F686727B9B406A9DD`。
- 推荐生产链：先用工作流 13 生成并人工确认静态人物关键帧，再进入已验证的 `12_ltx_face_stable_v3_api.json`；ControlNet 只在提供真实 OpenPose 姿态图时启用，LoRA 只在本地目录出现经过筛选的角色 LoRA 后启用。

### 最终 3 秒 I2V 烟囱回归

- 任务 957 使用默认 `12_ltx_face_stable_v3_api.json`、320×416、73 帧、guide 72、small motion，技术成功，脸部代理 96.02、身份漂移代理 3.60、参考相似度代理 95.91、帧视觉伪影代理 0%、显存峰值 10728 MiB。
- 首帧/中帧/尾帧已抽取到 `C:\install\AI\Data\QA\quality-v3-i2v-20260811_234239\task_957`；中帧仍需人工关注嘴部细节，但没有触发硬性拒绝。该结果支持 3 秒 Draft 生产门禁，不支持 5 秒复杂动作自动放行。
