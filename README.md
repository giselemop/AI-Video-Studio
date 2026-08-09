# AI Video Studio

AI Video Studio 是运行在现有本地 ComfyUI 之上的 AI 短剧生产管理系统。它管理剧本、角色、场景、Shot、Prompt、GPU 任务、视频 QA、声音和 Episode 输出；不会重新安装或复制 ComfyUI、模型、Python、Git 或 FFmpeg。

## 当前结论

- 核心生产链已通过真实本地验收：剧本 → Shot → 关键帧/I2V → QA/定向重试 → FFmpeg → Episode → Master。
- 当前服务地址：`http://127.0.0.1:18080`；ComfyUI：`http://127.0.0.1:8188`。
- 当前硬件基线：RTX 4070 12GB，GPU 任务并发 1；视频源优先 512×320、24 FPS、3-5 秒，最终由 FFmpeg 输出 1080P/30 FPS。
- 当前模型目录没有 LoRA、IP-Adapter、ControlNet 资产，严格角色一致性仍是下一阶段增强项，不能把它写成现有能力。
- 当前项目状态、真实测试证据和已知限制见 [PROJECT_STATE.md](PROJECT_STATE.md)。

## 目录

```text
C:\install\AI\VideoStudio
├─ server       .NET 8 API、GenerationQueue、ComfyUI/FFmpeg/QA 服务
├─ web          Vue 3 + Element Plus 源码
├─ database     基线结构和迁移
├─ scripts      发布、初始化、备份、扫描和真实回归脚本
├─ config       appsettings.json、local.env.example、config.example.json
├─ docs         详细架构、数据库、ComfyUI、使用和验收说明
└─ .gitignore   排除秘密、备份、日志、模型、媒体和构建产物
```

外部目录：

- 模型：`C:\install\AI\Models`
- 工作流：`C:\install\AI\Workflows`
- 媒体/输出/QA：`C:\install\AI\Data`
- ComfyUI：`C:\install\AI\ComfyUI`
- FFmpeg：`C:\install\FFmpeg`

## 启动与恢复

首次配置只需把 `config\local.env.example` 复制为未跟踪的 `config\local.env`，填入现有 MySQL 密码，然后执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\install\AI\VideoStudio\scripts\init_database.ps1
C:\install\AI\VideoStudio\start.bat
```

浏览器打开 `http://127.0.0.1:18080`。停止管理服务运行 `C:\install\AI\VideoStudio\stop.bat`；电脑重启后再次运行 `start.bat`，遗留 Running 任务会恢复为 Pending。

密码只放在 `config\local.env`，不放进 `appsettings.json`、源码、报告、日志或 Git。详细操作见 [docs\快速入门.md](docs/快速入门.md) 和 [docs\使用说明.md](docs/使用说明.md)。

## 真实生产链

```text
角色/场景资产 → 项目/Episode → Shot/Prompt → 关键帧 → I2V
       → 技术/Shot/Episode QA → TTS/SRT/音频 → FFmpeg → Master
```

服务通过 ComfyUI 的 `/prompt`、`/history/{prompt_id}`、`/view`、`/interrupt` 处理真实任务，不模拟完成状态。详细设计见 [docs\ARCHITECTURE.md](docs/ARCHITECTURE.md)、[docs\DATABASE.md](docs/DATABASE.md) 和 [docs\COMFYUI_API.md](docs/COMFYUI_API.md)。

## 常用验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\install\AI\VideoStudio\scripts\test_production_pipeline.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File C:\install\AI\VideoStudio\scripts\qa_test.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File C:\install\AI\VideoStudio\scripts\backup.ps1
```

`test_production_pipeline.ps1 -RunRealGeneration` 才会占用 GPU 生成真实视频；正常回归不重复生成已通过的 Shot。严格验收规则、状态和证据见 [docs\质量验收说明.md](docs/质量验收说明.md)、[docs\ACCEPTANCE_REPORT.md](docs/ACCEPTANCE_REPORT.md) 和 [docs\FIX_HISTORY.md](docs/FIX_HISTORY.md)。

## 长期维护

开始新会话先读 [AGENTS.md](AGENTS.md)、[PROJECT_STATE.md](PROJECT_STATE.md) 和 [NEXT_STAGE.md](NEXT_STAGE.md)。任何失败都必须记录原因、做最小修复、重新测试并回归相关链路；只有 `Passed` 才能继续，三轮相同外部阻塞才允许标记 `Blocked`。
