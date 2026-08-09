# 架构文档入口

详细架构以 [`docs\ARCHITECTURE.md`](docs/ARCHITECTURE.md) 为唯一维护源。

本项目的固定边界是：Vue 3 工作台 → .NET 8 API → MySQL/GenerationQueue → ComfyUI/FFmpeg → `C:\install\AI\Data`。模型和工作流不复制进仓库；GPU 任务在 RTX 4070 12GB 上串行运行。

长期维护规则见 [`AGENTS.md`](AGENTS.md)，真实当前状态见 [`PROJECT_STATE.md`](PROJECT_STATE.md)。
