# Stage 3B Gate 3：正式最小权限验证报告

日期：2026-08-13\
状态：`PASS`

## 账户与授权范围

目标数据库严格为 `ai_video_studio`，主机严格为 `127.0.0.1`。本轮未修改 root，未创建其他账户，未授予全局权限。

| 账户 | 授权 | 用途 | 当前状态 |
|---|---|---|---|
| `ai_video_studio_app@127.0.0.1` | `SELECT, INSERT, UPDATE, DELETE` on `ai_video_studio`.* | API运行时 | 保留并作为有效应用账户 |
| `ai_video_studio_migrator@127.0.0.1` | `SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX, REFERENCES` on `ai_video_studio`.* | 显式迁移 | 008完成后 `ACCOUNT LOCK` |

两账户均无 `GRANT OPTION`、`CREATE USER`、`FILE`、`PROCESS`、`SUPER`、`SYSTEM_USER` 或其他管理权限。密码仅保存在本机受限安全文件，不在报告中记录。

## 实际验证

命令：

```text
dotnet .\server\bin\Debug\net8.0\VideoStudio.Server.dll --stage3b-setup
dotnet .\server\bin\Debug\net8.0\VideoStudio.Server.dll --stage3b-privilege
```

结果：均退出码 `0`；`--stage3b-privilege` 输出 `checks=14`。

### app账户

- `SELECT`成功。
- `INSERT/UPDATE/DELETE`在事务中执行并回滚，成功。
- `CREATE TEMPORARY TABLE`、`ALTER`、`DROP`、`GRANT`、`CREATE USER`均被拒绝。
- 访问恢复库 `ai_video_studio_restore_acceptance_20260813` 被拒绝。

### migrator账户

- 目标库 `SELECT`成功。
- `DELETE`、`DROP`、`CREATE USER`、`GRANT`均被拒绝。
- 访问恢复库 `ai_video_studio_restore_acceptance_20260813` 被拒绝。
- `SHOW GRANTS`校验只允许目标数据库级授权，没有全局或其他数据库授权。

## 应用切换验证

`--stage3b-config-status`退出码 `0`，确认有效运行配置为 app@127.0.0.1、`AI_VIDEO_STUDIO_AUTO_APPLY_SCHEMA=0`、Worker=0，并使用 app 账户连接目标数据库成功。API安全回归进一步确认运行时设置不再使用 root。

## 边界

这是正式账户和显式008迁移的本机验证，不是局域网/公网发布授权；多角色RBAC仍是局域网开放前P0。未启动Worker，未执行真实任务，未改变正式媒体。
