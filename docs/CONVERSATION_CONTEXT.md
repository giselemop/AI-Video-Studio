# AI Video Studio 对话上下文与接管记录

## 文档用途

本文件把此前关于本地 AI 视频项目的长期对话，转换成项目可持续使用的事实、决策、验收证据和待办事项。它不是逐字聊天备份；密码、Token、API Key、Cookie 和其他敏感值不会写入项目。

后续接管优先读取：`AGENTS.md` → `PROJECT_STATE.md` → 本文件 → `NEXT_STAGE.md` → `docs\ACCEPTANCE_REPORT.md` / `docs\FIX_HISTORY.md`。

## 1. 用户最初目标

- 在 Windows 11 上建立本地 AI 图像与视频生成学习环境。
- 学习人物生成、角色一致性、Image To Video 和短视频制作流程。
- 固定安装边界：软件使用 `C:\install\`，模型使用 `C:\install\AI\Models`，工作流使用 `C:\install\AI\Workflows`，媒体使用 `C:\install\AI\Data`。
- 不修改系统环境变量，不把模型放进 ComfyUI 目录，不重复安装已经存在的软件。
- 硬件基线：Intel i5-13600KF、RTX 4070 12GB、32GB RAM、Windows 11 64 位。

## 2. 对话中形成的关键决策

### 视频时长

最初生成结果约 2 秒，后来确定默认目标为 5 秒：LTX I2V 使用 121 帧、24 FPS，约 5 秒。3 秒和 4 秒仍保留为低负载测试档位。

### 生成路线

- 优先 Image To Video，而不是直接 Text To Video。
- 关键帧先用 SD1.5 人物/场景工作流，再送入 LTX I2V。
- RTX 4070 12GB 使用 GPU 队列并发 1、显存门禁和 OOM 降参。
- 生成源视频先使用约 512×320，最终 1080P/30 FPS 由 FFmpeg 后处理完成。

### 人物真实感与一致性

人物脸部真实感不能只靠一句 Prompt；需要高质量身份锚点、稳定的光线/构图、固定服装和发型、合理 seed，以及后续的 LoRA/IP-Adapter/ControlNet。当前项目保存参考图、固定提示词和角色资产，但实际扫描到的 LoRA 为 0，IP-Adapter/ControlNet 尚未安装，因此严格身份一致性仍属于下一阶段能力。

### 从单镜头到短剧生产

项目逐步从“生成一个视频”扩展为：

`剧本 → 项目/Episode → 角色/场景 → Shot → Prompt → 关键帧 → I2V → QA/回炉 → 音频/SRT → FFmpeg → Episode → Master`

范围包括角色资产库、场景资产库、镜头语言、动作控制、视频增强、TTS、字幕、SFX/BGM、批量生产和后续连续剧集管理。

## 3. 重要验收规则

- 开发 → 测试 → 验收 → 修复 → 重新测试 → 重新验收必须闭环。
- 失败必须记录原因分类并修复实际代码、配置、数据库、Workflow、模型、Prompt、参数或依赖；不能只写 TODO。
- AI 内容只回炉失败 Shot；已 Passed 的 Shot 不做无意义重复生成。
- 自动回炉每个 Shot 最多 2 次，每次必须改变相关因素并记录前后参数、结果和 QA 分数。
- 验收状态只使用 `Passed`、`Failed`、`Blocked`。三轮相同外部阻塞仍无法解决时才允许 `Blocked`。
- 数据库修复前先备份并使用迁移；禁止删除既有业务数据、伪造状态、Mock 结果或用空文件冒充视频。

## 4. 已落地的项目阶段

1. 本地基础环境、ComfyUI、模型目录、工作流目录、FFmpeg 和独立配置完成。
2. ComfyUI 图片生成与 Image To Video 任务接入完成。
3. 5 秒视频参数和 RTX 4070 低显存策略完成。
4. AI Video Studio 项目管理、角色、场景、Shot、Prompt 和剧本解析完成。
5. GenerationQueue、任务依赖、暂停/恢复、取消、重试和服务重启恢复完成。
6. TTS、SRT、SFX/BGM、FFmpeg 增强和 Episode 合成接入完成。
7. Technical QA、Shot QA、Episode QA、人工审核、锁定和 Master 导出完成。
8. QA 自动回炉和长期开源/本地维护基线完成。

## 5. 当前已确认状态

- 服务：`http://127.0.0.1:18080`。
- ComfyUI：`http://127.0.0.1:8188`。
- 数据库：MySQL `ai_video_studio`，凭据已在本机未跟踪配置中生效；密码不记录在本文件。
- GPU：NVIDIA GeForce RTX 4070，约 12GB；最近健康检查总显存 12281 MiB、空闲约 11018 MiB。
- 当前核心模型登记 3 个，LoRA 0 个，工作流 8 个，QA 预设 3 个。
- 当前生产核心阶段状态：`Passed`；没有未解决的 `Failed` 或 `Blocked` 核心项。
- 当前数据库中包含可识别的 `Production Pipeline Test` 回归数据；它们用于证明脚本和剧本分析链路，不应被误认为产品故障。

## 6. 关键失败与修复摘要

| 问题 | 原因 | 修复/结果 |
| --- | --- | --- |
| 视频只有约 2 秒 | 帧数参数过低 | 统一为 121 帧/24 FPS，真实结果约 5 秒 |
| 人脸与角色不稳定 | 参考图和身份控制模型不足 | 固定身份锚点/Prompt/seed；LoRA、IP-Adapter、ControlNet 列入下一阶段 |
| QA 回炉复用相同 seed | 回炉参数没有变化 | 每轮生成新 seed，记录 changed parameters，最多两轮 |
| 回炉后未再次增强/QA | 任务链不完整 | 补齐 `ShotQA → I2V → Enhance → ShotQA` |
| 生产回归首次 HTTP 404 | PowerShell API 数组未枚举 | 修复 `test_production_pipeline.ps1` 的 `Call-Api`，同一入口复测通过 |

完整记录见 `docs\FIX_HISTORY.md`；完整结果见 `docs\ACCEPTANCE_REPORT.md`。

## 7. 下一阶段方向

- 角色身份一致性：参考集版本、轻量身份控制模型、10 动作/5 场景测试。
- 场景一致性：场景参考集、场景版本和跨镜头人工 QA。
- Pose/Motion/Camera 控制：先验证 12GB 可运行的 OpenPose/ControlNet/Motion 工作流。
- TTS/字幕/混音的真实 Episode 回归。
- 资产版本、备份恢复、自动化测试项目和指标驱动的工作流推荐。

具体任务、优先级、风险和验收标准以根目录 `NEXT_STAGE.md` 为准。
