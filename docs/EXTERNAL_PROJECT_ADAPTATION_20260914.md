# 外部开源项目借鉴与本地实施记录

日期：2026-09-14\
范围：只读检索公开 GitHub 文档，并将适合本地 ComfyUI/FFmpeg/RTX 4070 路线的设计做成增量改动。

## 参考项目

- [Story Claw](https://github.com/ZC89757/story-claw)：Windows、本地 ComfyUI/LTX、角色/场景阶段资产、配音与整集输出。
- [ComfyStudio](https://github.com/XmYx/ComfyStudio)：Shot 管理、工作流串联、版本历史、多轨时间线和 FFmpeg 导出。
- [雪风 AI 短剧工坊](https://github.com/oiuv/ai-short-drama)：中文六步工作台、角色/场景/道具参考图绑定、TAKE 和本地剪辑。
- [ComfyUI-Workflow-Studio](https://github.com/ketle-man/ComfyUI-Workflow-Studio)：工作流/模型/资产管理，以及 H3/LTX/Wan 视频参数界面。

## 本轮已实施

参考图元数据在已有 `metadata_json` 中增加：

- `stage`：角色或场景所处阶段，例如 `base`、`受伤后`、`夜间`。
- `role`：参考图职责，例如 `identity`、`outfit`、`pose`、`environment`。
- `changeReason`：为什么新增该阶段参考图。

上传接口现在会校验这些标签，角色参考图查询和新增的场景参考图查询会返回它们。已有人工审核、哈希版本和生成准入逻辑保持不变；阶段信息不会自动选择模型、工作流或绕过审核。

新增无数据库、无 GPU 的 `test_reference_metadata.ps1`，覆盖默认值、序列化往返和路径字符拒绝。

镜头制作台新增只读 `/api/shots/{id}/takes` 版本查询，以及“版本”查看面板。它按镜头聚合 ImageToVideo、Video、Enhance 任务产生的结果，展示 TAKE 编号、任务状态、工作流、尺寸、时长、种子和文件可用性；不在本轮自动选片、替换正式视频或改变发布版本。

## 暂不合并

- 不直接复制外部项目的 Electron/React/Python UI，当前 VideoStudio 的 .NET/Vue/MySQL 生产链已经存在且工作区有未提交改动。
- 不把外部项目 README 宣称的“角色一致性”当作本机验收证据；仍需真实参考集、跨动作/场景生成、人工评分和失败镜头回炉证据。
- 不引入新的模型、LoRA、云 API 或付费调用。
- TAKE 面板目前是查看证据，不等同于镜头内容质量通过；正式选用仍受人工审核、整集验收和发布候选门禁约束。
