# 阶段3A正式最小权限切换报告

状态：`BLOCKED（未创建账户）`\
日期：2026-08-13

## 当前事实

- 正式应用仍使用现有root基线；root未修改。
- 正式运行账户和正式迁移账户本轮均未创建、未授权、未切换。
- 阶段2.5临时账户已删除；其权限不延伸到正式库。

## 待确认的正式账户方案

建议沿用项目既有命名约定，但在执行前必须由用户确认精确名称：

| 账户 | 建议主机 | 计划权限 | 禁止权限 |
|---|---|---|---|
| `ai_video_studio_app` | `127.0.0.1` | 正式业务库`SELECT, INSERT, UPDATE, DELETE` | `CREATE, ALTER, DROP, GRANT, CREATE USER, FILE, PROCESS, SUPER, SYSTEM_USER, GRANT OPTION` |
| `ai_video_studio_migrator` | `127.0.0.1` | 正式业务库迁移所需`SELECT, INSERT, UPDATE, CREATE, ALTER, INDEX, REFERENCES` | 全局权限、其他数据库、`CREATE USER`、`GRANT`、管理权限 |

## 执行前需要用户确认

1. 是否采用上述精确账户名和`127.0.0.1`主机限制。
2. 迁移账户在008完成后保留、禁用还是删除。
3. 运行账户凭据的本机安全配置位置和回收窗口。
4. 正式API配置切换和Gate 4启动窗口。

本报告不包含密码或连接字符串；在确认前不执行CREATE USER、GRANT或应用配置切换。
