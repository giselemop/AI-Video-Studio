# Stage 3B 本轮实际修改文件清单

日期：2026-08-13\
范围：仅记录本轮阶段3B切换、Gate 4、Gate 5预检和回传更新；阶段1/2既有文件完整清单见 `STAGE12_IMPLEMENTATION_FILE_LIST_2026-08-13.md`。

## 项目内本轮新增或修改

| 文件 | 动作 | 用途 | 说明 |
|---|---|---|---|
| `server/Stage3BFormalHarness.cs` | 新增 | 正式账户创建、最小权限、008首次/重复迁移、migrator锁定、应用切换和配置状态 | 仅接受精确正式数据库/账户边界；凭据不输出 |
| `server/Program.cs` | 修改 | 分派 `--stage3b-*` 受控验证入口 | 与既有阶段代码有交叉，未覆盖无关修改 |
| `config/appsettings.json` | 修改 | 将非敏感默认数据库用户从 root 切换为 app 用户 | 密码仍只从本机安全配置读取 |
| `config/local.env.example` | 修改 | 示例配置默认不再指向 root | 不含密码；AUTO=0、Worker=0保持 |
| `scripts/test_stage3b_api_startup.ps1` | 新增 | 127.0.0.1 API安全启动夹具 | 结束时停止进程 |
| `scripts/test_stage3b_api_security.ps1` | 新增 | API安全负向、正式app配置和Playwright E2E编排 | 不提交真实GPU任务 |
| `scripts/test_stage3b_comfyui_preflight.ps1` | 新增 | ComfyUI loopback、节点、工作流白名单和目标契约预检 | 发现契约问题后阻塞退出，不修改Workflow |
| `web/tests/episode-output.spec.js` | 最小修改 | 将实际受控媒体查询契约从过时的 `path` 对齐为 `assetPath` | 初始断言失败后修复并完整重跑5/5；未放宽断言 |
| `docs/productionization/STAGE3B_FORMAL_MIGRATION_REPORT_2026-08-13.md` | 新增 | 正式008迁移和配置切换证据 |
| `docs/productionization/STAGE3B_LEAST_PRIVILEGE_REPORT_2026-08-13.md` | 新增 | 正式app/migrator权限与负向验证 |
| `docs/productionization/STAGE3B_API_SECURITY_E2E_REPORT_2026-08-13.md` | 新增 | API安全和前端E2E证据 |
| `docs/productionization/STAGE3B_COMFYUI_PREFLIGHT_REPORT_2026-08-13.md` | 新增 | ComfyUI只读预检和Gate 5阻塞证据 |
| `docs/productionization/STAGE3B_GOLDEN_SHOT_REPORT_2026-08-13.md` | 新增 | Gate 6未运行与停止原因 |
| `docs/productionization/STAGE3B_EXECUTION_FILE_LIST_2026-08-13.md` | 新增 | 本清单 |

## 执行包外部文件

| 文件 | 动作 |
|---|---|
| `%USERPROFILE%\Desktop\AI-Video-Studio生产化执行包-v1.0\03-AI-Video-Studio生产化验收标准.md` | 直接更新B/E类原始条目和当前阶段3B快照；历史第20/22节保留 |
| `%USERPROFILE%\Desktop\AI-Video-Studio生产化执行包-v1.0\04-AI-Video-Studio执行结果回传模板.md` | 更新当前结论、数据库/配置/测试/安全/能力边界和阶段3B最新回传；历史节保留 |

## 未修改内容

本轮未修改正式迁移SQL `008_stage12_production_core.sql`、正式媒体、模型、节点、依赖或用户无关文件；未执行删除、覆盖、Commit或Push。
