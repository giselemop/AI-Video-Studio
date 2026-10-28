# Stage 3B Gate 4：API安全回归与前端E2E报告

日期：2026-08-13\
状态：`PASS`（loopback、Worker关闭、无真实生成）

## 命令与运行边界

```text
powershell -ExecutionPolicy Bypass -File scripts/test_stage3b_api_security.ps1 -RunE2E -SkipGpuDependentPreflight
```

退出码：`0`。脚本使用正式 app 配置启动 API，仅监听 `127.0.0.1:18080`，设置 `AUTO_APPLY_SCHEMA=0`、Worker=0，并在 finally 中停止进程。测试使用本机临时管理员凭据；密码未写入报告或日志。

## 通过项

| 场景 | 实际结果 |
|---|---|
| 匿名、错误密码、登录、session、CSRF、Origin、退出登录 | PASS |
| `/api/health`、数据库连接和运行账户 | PASS；MySQL online，运行时用户为 app，非 root |
| GPU任务离线预检 | PASS；Comfy离线时 fail-closed，非法提交在入队前拒绝 |
| 缓存清理预览 | PASS；dry-run响应，不执行正式清理 |
| CORS | PASS；允许 loopback 精确返回，未列 Origin 无 allow header |
| 媒体路径 | PASS；路径穿越、UNC、设备路径、相对盘符和ADS候选均拒绝 |
| Asset归属/用途 | PASS；跨Project Asset ID和非法用途拒绝 |
| 正式终态旁路 | PASS；普通 Shot API 不能直接设置 `Approved` |
| LLM出站负向 | PASS；非allowlist、非HTTPS和超大Prompt拒绝；无第三方请求 |
| 审计脱敏 | PASS；响应不含临时密码或被拒绝的LLM敏感值 |
| 前端E2E | PASS；真实 API 上 `5 passed` |

## 前端E2E边界

测试文件为 `web/tests/episode-output.spec.js`，覆盖真实API下的项目/Episode/Shot输出页面和受控媒体访问路径。测试未创建GPU任务，未生成或修改正式媒体。一次初始失败来自测试中已过时的 `?path=`契约，已按实际受控API改为 `?assetPath=`，随后完整重跑为5/5通过；没有降低断言或扩大忽略范围。

## 未宣称内容

- 未运行Worker领取、真实GPU生成、ComfyUI生成、音频、Episode/Master或人工视觉审核。
- 本报告不证明多角色RBAC；多角色RBAC继续为局域网开放前P0。
- API进程已停止，当前无18080监听。
