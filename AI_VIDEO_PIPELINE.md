# AI Video Studio 生产流水线

## 当前定位

本项目在现有本地 ComfyUI、MySQL 和 FFmpeg 之上提供 AI 短剧生产管理，不复制模型、不重装环境、不用模拟结果。当前核心链路已经通过真实本地验收，详细证据见 `docs\ACCEPTANCE_REPORT.md`。

## 生产链路

```text
项目/Episode
  ↓
角色/场景资产与参考图
  ↓
剧本版本与 Shot 拆分
  ↓
Prompt 生成、人工编辑、锁定
  ↓
SD1.5 关键帧候选 → 选定关键帧
  ↓
LTX 2B FP8 Image To Video
  ↓
Technical/Shot QA → 失败 Shot 定向回炉（最多2次）
  ↓
FFmpeg 去闪烁/插帧/超分/1080P
  ↓
Windows TTS/SRT/SFX/BGM（按需要）
  ↓
Episode 合成 → Episode QA → 人工 Approved/锁定
  ↓
Master + 封面 + QA_REPORT
```

GPU 队列固定并发 1；源视频优先 512×320、24 FPS、73/97/121 帧（约 3/4/5 秒），最终输出 1920×1080、30 FPS。RTX 4070 12GB 不直接承载 1080P 视频生成。

## 当前实现模块

- 项目、Episode、角色、场景、Shot、参考图和素材 CRUD。
- 剧本保存/版本/本地规则解析/可选 LLM 分析。
- Prompt 七段组合、编辑、锁定、历史和回滚。
- ComfyUI 工作流、模型、LoRA 扫描和真实 HTTP 任务。
- GenerationQueue：GPU 门禁、依赖、暂停/恢复、取消、重试、OOM 降参、服务重启恢复。
- Technical/Shot/Episode QA、问题记录、人工审核、Approved 锁、Master 导出。
- Windows TTS、音频缓存、SRT、SFX/BGM 上传、FFmpeg 混音和字幕。

## 当前模型基线

当前登记模型 3 个、LoRA 0 个；核心工作流为 `01_portrait_quality_api.json`、`02_ltx_i2v_quality_api.json`、`06_scene_keyframe_quality_api.json` 和 `07_cinematic_shot_presets.json`。IP-Adapter、ControlNet 和角色 LoRA 尚未安装，严格身份一致性列入 `NEXT_STAGE.md`，不能作为当前保证。

## 验收原则

- 任务必须真实提交 ComfyUI 并下载真实输出；不能写假状态或空文件。
- 技术 QA 的硬失败不能由平均分掩盖；人物一致性、动作语义、连续性和电影感需要人工复核。
- 失败只重做失败 Shot；已 Passed Shot 禁止无意义重复生成。
- 自动回炉最多 2 次；每次改变相关 Prompt、seed、Reference、LoRA 或 Workflow 参数并记录。
- 代码修复后必须跑受影响功能和相关回归；数据库修复先备份再迁移。

## 日常入口

- 启动：`C:\install\AI\VideoStudio\start.bat`
- 停止：`C:\install\AI\VideoStudio\stop.bat`
- 快速入门：`docs\快速入门.md`
- 使用说明：`docs\使用说明.md`
- 质量验收：`docs\质量验收说明.md`
- 当前状态：`PROJECT_STATE.md`
- 下一阶段：`NEXT_STAGE.md`
