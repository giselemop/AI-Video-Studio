# AI Video Studio 文档索引

## 长期项目档案（中文权威入口）

| 文档 | 用途 |
| --- | --- |
| ..\\项目状态.md | 当前项目状态、完成度、风险、验证结果和 AI 恢复协议 |
| ..\\待办事项.md | P0/P1/P2、Bug、技术债和待确认事项 |
| ..\\变更记录.md | 重要历史变更与开发检查点 |
| 项目需求.md | 已确认需求、待确认需求和当前范围 |
| 系统架构.md | 中文架构摘要与真实模块关系 |
| 技术决策.md | 已采用的关键技术方案 |
| 验收标准.md | 可执行验收条件与本轮结果 |
| 开发说明.md | 换电脑后的环境恢复、启动、测试和部署 |

上述中文档案是长期开发的动态事实入口；本页下面的英文文档和历史文档作为详细技术说明或证据保留，不另维护一套相冲突的项目状态。

| 文档 | 用途 |
| --- | --- |
| `..\AGENTS.md` | Codex 接管、恢复、完成和验收规则 |
| `..\PROJECT_STATE.md` | 当前实际运行时、数据库、模型、任务和证据 |
| `..\NEXT_STAGE.md` | 带验收标准的后续 P0/P1/P2 任务 |
| `..\CHANGELOG.md` | 已落地版本变化 |
| `CONVERSATION_CONTEXT.md` | 此前对话迁移后的项目背景、决策、验收和修复摘要 |
| `ARCHITECTURE.md` | 实际模块边界与生产链路 |
| `DATABASE.md` | MySQL 表、迁移、备份和状态恢复 |
| `COMFYUI_API.md` | ComfyUI HTTP API 与工作流参数 |
| `快速入门.md` | 30 分钟首次使用路径 |
| `使用说明.md` | 日常生产、角色/场景资产和错误处理 |
| `质量验收说明.md` | Technical/Shot/Episode QA 与发布闸门 |
| `ACCEPTANCE_REPORT.md` | 最近一次强制验收结果 |
| `FIX_HISTORY.md` | 失败、原因、修复和复测记录 |

项目使用现有目录：

- `C:\install\AI\Models`：模型
- `C:\install\AI\Workflows`：ComfyUI API 工作流
- `C:\install\AI\Data`：项目、素材、输出、QA 和临时文件

文档只描述已从实际代码或运行时确认的能力。没有安装的 LoRA、IP-Adapter、ControlNet、自动导演、多 GPU 和远程管理列入 `NEXT_STAGE.md`，不在当前完成声明中。
