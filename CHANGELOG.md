# AI Video Studio 变更记录

本文件记录已落地并有测试证据的阶段变化；规划内容写入 `NEXT_STAGE.md`，不在这里伪装成已完成。

## 0.4.0 - 2026-08-09 - 长期项目基线（Passed）

- 增加 `AGENTS.md`，固定架构、路径、显存、数据库、验收、恢复和完成协议。
- 增加 `PROJECT_STATE.md`，记录实际运行时、数据库、模型、任务和验收证据。
- 重写根 README 与 `docs` 文档，消除“数据库未配置”等旧状态，统一详细文档入口。
- 增加安全的 `config\config.example.json`；真实本地配置仍仅使用未跟踪的 `config\local.env`。
- 增加 `.gitignore`，排除密码、日志、备份、构建产物、模型、媒体和机器特定文件。
- 初始化本地 Git 仓库并在最终验收时检查 staged 文件、秘密扫描和提交内容。

## 0.3.0 - 2026-08-09 - Video QA 与发布闸门

- 增加 Technical/Shot/Episode QA、评分、问题帧、人工审核、Episode 锁定和 Master/QA 报告导出。
- 增加 QA 自动回炉上限和定向参数变更记录。
- 完成真实 3-shot Episode、QA 和 Master 导出验收。

## 0.2.0 - 2026-08-09 - Production Pipeline

- 增加剧本分析、Prompt 版本、关键帧候选、I2V、任务依赖、恢复、TTS、SRT、SFX/BGM 和 Episode 合成。
- 固定 RTX 4070 12GB 的 GPU 并发 1、显存门禁和 OOM 降参策略。

## 0.1.0 - 基础系统

- 建立 Vue 3 + Element Plus 工作台、.NET 8 API、MySQL 结构、ComfyUI/FFmpeg 本地目录和基础资产/任务管理。
