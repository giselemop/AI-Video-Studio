# 2026-08-11 优化实施与回归记录

本文件记录基于 `BASELINE_REPORT_2026-08-11.md` 和 `AI_QUALITY_OPTIMIZATION_REPORT_2026-08-11.md` 的代码落地结果。它不把“任务成功”当成“内容通过”，而是分别记录技术成功、人工复核和正式发布门禁。

## 已落地

1. Episode 合成拆为 `Formal` 和 `Preview` 两种模式。正式模式要求所有镜头 `Passed`、Episode `Approved` 且锁定、无未关闭 Critical/Error 问题，并且每个源文件是目标分辨率的正式增强视频；否则接口返回 422 和逐镜头原因。
2. `preview=true` 只生成审核预览，输出带 `PREVIEW_` 前缀、素材类型为 `episode_preview`，不会覆盖 Episode 的正式输出路径。
3. AutoProduction 不再绕过 QA 门禁自动合成；它会等待正式质量门禁满足。
4. 人工把自动 QA `Rejected` 镜头改为 `Passed` 时必须填写复核说明。
5. 角色静态关键帧在检测到 IP-Adapter Plus、CLIP Vision 和人物参考图时自动走 `13_sd15_ipadapter_face_v1_api.json`；没有这些资产时保留原有参考图 img2img 回退。IP-Adapter 强度通过任务参数注入，ControlNet 则要求独立的 `controlImages/controlImagePath`，不会把身份参考图误当姿态图。

## 实机回归

| 项目 | 结果 |
| --- | --- |
| 任务 958/963：IP-Adapter 人物关键帧 | 成功；峰值显存 4667/4677 MiB；输出分别写入 `C:\install\AI\Data\Images\task_958_task_958_00001_.png`、`task_963_task_963_00001_.png` |
| 任务 959：IP-Adapter 关键帧 → LTX v3 I2V | 成功；320×416、73 帧、guide frame 72；峰值显存 10478 MiB；CPU 人脸代理 93.74；技术 QA Passed |
| Episode 27 正式合成门禁 | 按预期返回 422；10 个镜头均未 QA/正式增强，未被“可播放”绕过 |
| Episode 27 审核预览 | 任务 960 成功；结果类型 `episode_preview`；未覆盖原正式输出路径 |
| ControlNet 误用保护 | 任务 962 使用身份参考图调用 OpenPose 工作流时按预期失败，服务端要求独立的 `controlImages/controlImagePath` |
| 前端/后端构建 | `npm run build` 和 `dotnet build --no-restore` 均通过 |

## 仍然需要人工/后续验证

- CPU 人脸 ROI 是风险筛查代理，不是 landmark 或身份识别模型；正式发布仍需查看首帧、中帧和尾帧。
- 当前本地 LTX 2B、RTX 4070 12GB 和 SD1.5 关键帧链路能稳定完成受控的单人微动作，但不能宣称已经达到云端大模型的复杂多动作、长镜头或全身表演水平。
- ControlNet 只有在提供真实 OpenPose 姿态图后才进入正式验收；当前 loader smoke 不构成姿态控制验收。
- LoRA 目录仍为空，没有角色 LoRA 的质量结论。

## 2026-08-12 稳定性补强

- 项目页首次打开时会自动选中第一个项目并加载 Episode 输出状态，发布门禁不再依赖用户先手动点选项目。
- 任务 965：Episode 27 审核预览 V04 成功；输出路径与素材名称均为 `PREVIEW_QUALITY BASELINE VS OPTIMIZED_001_V04.mp4`，正式输出仍保持 `QUALITY BASELINE VS OPTIMIZED_001_V01.mp4`。
- 预览版本不再按内容哈希复用旧 Episode 素材记录，避免“结果路径是新版本、素材名称却是旧版本”的历史元数据错配；普通图片/视频资产仍保留哈希去重。
- 回归结果：正式合成 HTTP 422、未完成自动 QA 的人工 Passed HTTP 409；MySQL、ComfyUI、FFmpeg 健康检查均通过。
