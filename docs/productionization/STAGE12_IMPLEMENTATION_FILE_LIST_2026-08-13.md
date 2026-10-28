# 阶段1/2及阶段2.5实际修改文件清单

以下只列本轮阶段1/2安全实施和阶段2.5验收范围；工作区中其他既有修改和未跟踪路径属于用户资产，未纳入本清单。

## 新增

- `database/migrations/008_stage12_production_core.sql`
- `server/ProductionCoreModels.cs`
- `server/ProductionCoreRepository.cs`
- `server/TaskLeaseRepository.cs`
- `server/TaskArtifactService.cs`
- `server/GpuGlobalGate.cs`
- `server/FormalTaskSubmissionService.cs`
- `server/Stage12Endpoints.cs`
- `server/Stage12SchemaMigrator.cs`
- `server/Stage12SelfTest.cs`
- `server/Stage12GpuProbe.cs`
- `server/LlmEgressServices.cs`
- `server/ResourceSafetyServices.cs`
- `server/TaskSubmissionPreflightService.cs`
- `server/Stage25DatabaseHarness.cs`
- `scripts/test_stage25_races.ps1`
- `scripts/test_stage25_gpu_lock_recovery.ps1`
- `scripts/test_stage25_api_startup.ps1`
- `docs/productionization/STAGE25_DATABASE_MIGRATION_REPORT_2026-08-13.md`
- `docs/productionization/STAGE25_MIN_PRIVILEGE_REPORT_2026-08-13.md`
- `docs/productionization/STAGE25_RACE_TEST_REPORT_2026-08-13.md`
- `docs/productionization/STAGE25_SECURITY_NEGATIVE_REPORT_2026-08-13.md`
- `docs/productionization/STAGE25_ISOLATED_DB_STATUS_2026-08-13.md`
- `docs/productionization/STAGE3A_BACKUP_RESTORE_REPORT_2026-08-13.md`
- `docs/productionization/STAGE3A_FORMAL_MIGRATION_REPORT_2026-08-13.md`
- `docs/productionization/STAGE3A_FORMAL_MIN_PRIVILEGE_REPORT_2026-08-13.md`
- `docs/productionization/STAGE3A_API_SECURITY_E2E_REPORT_2026-08-13.md`
- `docs/productionization/STAGE3A_COMFYUI_PREFLIGHT_REPORT_2026-08-13.md`
- `docs/productionization/STAGE3A_SINGLE_SHOT_REPORT_2026-08-13.md`
- `scripts/test_stage12_core.ps1`
- `scripts/test_stage12_gpu_lock.ps1`
- `scripts/test_stage12_schema_static.ps1`
- `docs/productionization/STAGE12_DATA_MODEL_STATE_MACHINE_2026-08-13.md`
- `docs/productionization/STAGE12_RACE_TEST_REPORT_2026-08-13.md`
- `docs/productionization/STAGE12_ASSET_ATTEMPT_MANIFEST_2026-08-13.md`
- `docs/productionization/STAGE12_MYSQL_MIGRATION_AND_LEAST_PRIVILEGE_2026-08-13.md`
- `docs/productionization/PRODUCTION_SOP_V1_2026-08-13.md`
- `docs/productionization/RECOVERY_SOP_V1_2026-08-13.md`
- 本文件

## 修改

- `server/Database.cs`：schema opt-in、Worker opt-in、迁移链、资源保护、资产引用删除保护、旧直接状态入口收口。
- `server/Models.cs`：任务输入类型开放给统一的正式任务提交/租约入口使用。
- `server/GenerationQueue.cs`：统一租约仓储、Attempt工作区、Formal Asset ID解析、发布后成功副作用、GPU全局锁。
- `server/Program.cs`：服务注册、Worker默认关闭、LLM客户端重定向关闭、loopback自测入口。
- `server/Stage12SchemaMigrator.cs`：关联外键按information_schema幂等补齐。
- `server/ScriptAndPromptServices.cs`：LLM allowlist/预览/审计包装及重定向阻断。
- `server/MediaProductionServices.cs`：任务TTS/字幕的临时文件和非覆盖最终化。
- `server/VideoQaServices.cs`：Master任务临时准备和非覆盖报告输出。
- `server/FfmpegService.cs`、`server/ComfyUiClient.cs`：临时输出非覆盖移动。
- `config/local.env.example`：AUTO_APPLY_SCHEMA和WORKER_ENABLED默认0，数据库创建和磁盘阈值显式配置。
- `scripts/test_queue_lease_fencing.ps1`、`test_external_process_boundary.ps1`、`test_llm_egress_policy.ps1`、`test_phase0_static_evidence.ps1`：按新实现更新回归断言。
- `scripts/test_task_submission_preflight.ps1`未修改；因既有PowerShell解析错误本轮NOT RUN/BLOCKED，不计入PASS。
- 执行包外部：`03-AI-Video-Studio生产化验收标准.md`、`04-AI-Video-Studio执行结果回传模板.md`原始条目已更新，并保留阶段历史增量。

`server/AssetPathPolicy.cs`是阶段0已存在的路径边界，本轮由`AssetReferenceResolver`和正式任务提交入口复用，未重复改写；工作区中其他既有修改和未跟踪路径仍不属于本清单。

## 未做

没有Commit/Push、正式迁移、正式账户创建、依赖/模型安装、正式媒体删除或覆盖、真实GPU/视频任务、网络开放。阶段2.5按用户授权创建过隔离库和临时账户；账户已精确删除，隔离库按授权保留。阶段3A Gate 2按授权创建备份`backup/20260813_193208`和恢复库`ai_video_studio_restore_acceptance_20260813`，均按规则保留。构建生成的`bin/obj/web/dist`仅为本地构建输出，不作为业务提交或发布证据。
