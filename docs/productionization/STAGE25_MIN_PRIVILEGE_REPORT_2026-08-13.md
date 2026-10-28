# 阶段2.5MySQL最小权限验证报告

日期：2026-08-13。仅针对隔离数据库和用户授权的临时账户；未修改正式数据库或root。

## 1. 账户与授权

目标数据库：`ai_video_studio_stage12_acceptance_20260813`。账户主机限定为`127.0.0.1`。

| 账户 | 隔离库权限 | 全局权限 | 禁止项 |
|---|---|---|---|
| `ai_video_studio_stage12_app@127.0.0.1` | `SELECT, INSERT, UPDATE, DELETE` | 仅MySQL自动显示的`USAGE`，无对象权限 | `CREATE, ALTER, DROP, GRANT, CREATE USER, FILE, PROCESS, SUPER, SYSTEM_USER, GRANT OPTION` |
| `ai_video_studio_stage12_migrator@127.0.0.1` | `SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX, REFERENCES` | 仅`USAGE`，无对象权限 | 正式库访问、`CREATE USER`、`GRANT`、`FILE, PROCESS, SUPER, SYSTEM_USER, GRANT OPTION` |

实际`SHOW GRANTS`未输出密码、完整连接串或敏感配置；账户测试结束后已按精确名称删除。

## 2. 负向验证矩阵

| 测试 | 结果 |
|---|---|
| app读取隔离库 | PASS |
| app读取正式库 | PASS（被拒绝） |
| app执行CREATE | PASS（被拒绝） |
| app执行ALTER | PASS（被拒绝） |
| app执行DROP | PASS（被拒绝） |
| app执行GRANT | PASS（被拒绝） |
| migrator读取正式库 | PASS（被拒绝） |
| migrator执行CREATE USER | PASS（被拒绝） |
| migrator执行GRANT | PASS（被拒绝） |
| 检查全局对象权限/GRANT OPTION | PASS（未发现） |
| 现有root账户 | PASS（未修改、未删除） |

## 3. 证据命令

```text
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-privilege
dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-drop-accounts
```

`--stage25-privilege`在账户仍存在时执行真实SQL负向操作；`--stage25-drop-accounts`只对两个完整匹配的用户名和主机执行删除，并在删除后用精确`SHOW GRANTS`确认账户不存在。没有使用通配符、变量拼接或模糊对象名。

## 4. 边界

这不是正式运行账户切换验收。正式部署仍需建立独立的非root账户、逐表核对运行时DML、备份/恢复账户以及切换/回滚窗口；本轮不触碰正式账户和正式授权。
