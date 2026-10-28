<!-- character-story-20261027:start -->
> 2026-10-27：Administrator applied migrations010 and011; live type constraint, review table and foreign keys verified. No parallel story system or fake asset approvals. Verified SQL backups retained; do not shrink the constraint after new typed records exist. 详见[本轮验收](CHARACTER_STORY_ACCEPTANCE_20261027.md)。
<!-- character-story-20261027:end -->

# AI Video Studio 数据库说明

## 1. 基本信息

- 数据库：`ai_video_studio`
- 引擎/字符集：InnoDB / `utf8mb4`
- 连接默认：`127.0.0.1:3306`
- 权威来源：MySQL；任务、项目和 QA 状态不能依赖内存或临时 JSON。
- 最近核验：当前 schema 34 张表，数据库在线，既有项目/任务可读取。

真实密码只放在 `C:\install\AI\VideoStudio\config\local.env`，该文件被 `.gitignore` 排除。`config\config.example.json` 只是安全的结构模板，不是运行时秘密文件。

## 2. 表分组

| 分组 | 主要表 | 责任 |
| --- | --- | --- |
| 项目资产 | `projects`, `episodes`, `characters`, `character_references`, `scenes`, `scene_references`, `assets` | 剧本生产对象、参考图和磁盘媒体索引 |
| 生成配置 | `models`, `loras`, `workflows`, `prompt_templates`, `generation_presets` | 扫描出来的模型/工作流和 4070 参数预设 |
| 任务 | `generation_tasks`, `generation_results`, `task_dependencies`, `production_runs` | 任务生命周期、ComfyUI prompt、依赖、GPU 指标和生产进度 |
| Prompt/剧本 | `scripts`, `script_versions`, `prompt_history`, `shot_candidates` | 剧本版本、分析结果、Prompt 锁定和关键帧候选 |
| 声音 | `audio_cache`, `sound_effects`, `shot_sound_effects`, `bgm_tracks`, `episode_bgm`, `subtitles` | TTS 缓存、上传音频、BGM 绑定和字幕时间轴 |
| QA/审计 | `qa_runs`, `qa_issues`, `qa_presets`, `operation_logs` | 技术/Shot/Episode QA、问题、审核闸门和操作追踪 |

外键按业务关系使用级联或限制；删除数据库记录不会静默删除模型、视频或最终输出文件。媒体清理必须是显式、可审计的独立动作。

## 3. 初始化与迁移

初始化/升级入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\install\AI\VideoStudio\scripts\init_database.ps1
```

迁移基线：

1. `database\database.sql`：基础项目、资产、任务、模型和工作流结构。
2. `database\migrations\002_production_pipeline.sql`：剧本、Prompt、候选、依赖、声音和生产运行结构。
3. `database\migrations\003_video_qa.sql`：QA 运行、问题、预设、Shot/Episode QA 和锁定字段。

后端启动还会按 `information_schema` 做兼容性 schema 检查。脚本和迁移不得使用 `DROP DATABASE`、无确认的 `DROP TABLE` 或清空业务数据。

## 4. 备份规则

任何迁移或数据库修复前先执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\install\AI\VideoStudio\scripts\backup.ps1
```

备份写到 `C:\install\AI\VideoStudio\backup\<timestamp>`，包含数据库导出和角色/场景/工作流配置快照；不会复制大模型和大体积媒体。迁移完成后必须验证表、关键列、默认 QA 预设和现有项目/任务可读。

## 5. 一致性约束

- `generation_tasks` 的状态必须和实际 ComfyUI/FFmpeg 结果相符；禁止手工改成 `Succeeded` 或 `Passed`。
- 任务失败必须保留错误分类、错误文本、尝试次数和相关日志；重试只重排真实失败任务。
- QA 的 `Passed`、`Failed`、`Blocked` 是验收结论，不可用“基本可用”替代。
- 数据库迁移修改后，至少回归项目/Episode/Shot CRUD、任务提交/取消/重试/恢复、Timeline 和 Episode 合成。
