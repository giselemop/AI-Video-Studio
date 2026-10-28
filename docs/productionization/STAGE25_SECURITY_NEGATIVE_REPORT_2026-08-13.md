# 阶段2.5安全负向验收报告

日期：2026-08-13。所有夹具均为本机受控临时对象；没有向真实第三方LLM发送Prompt或媒体。

## 1. 账户与数据库边界

| 场景 | 结果 | 证据 |
|---|---|---|
| app执行CREATE/ALTER/DROP/GRANT | PASS（均被拒绝） | `--stage25-privilege` |
| migrator读取正式库 | PASS（被拒绝） | `--stage25-privilege` |
| migrator执行CREATE USER/GRANT | PASS（均被拒绝） | `--stage25-privilege` |
| 全局权限/GRANT OPTION | PASS（未发现） | `SHOW GRANTS`摘要 |
| 正式root | PASS（未修改） | 清理命令只匹配两个临时账户 |

## 2. Asset与路径负向

`--stage25-domain`和`--stage25-path`实际验证：

- 跨Project Asset ID：拒绝。
- 错误用途和错误扩展名：拒绝。
- 相对路径越界、绝对根外路径：拒绝。
- UNC路径、设备路径和设备路径前缀：拒绝。
- ADS/非法冒号：拒绝。
- 受控临时目录中的重解析点/目录联接指向允许根外：拒绝。
- 空文件、损坏媒体、`.part`/半文件：拒绝最终化。
- 已有最终目标不能被覆盖；旧文件保持不变。

阶段2.5路径夹具共9类负向通过；既有`test_asset_path_policy.ps1`另检查1360个Data文件。

## 3. 外部进程参数

使用含命令分隔符字符的受控文件名调用真实FFprobe参数边界，未生成额外命令标记文件。参数以数组传递，未通过shell拼接。`test_external_process_boundary.ps1`通过。未运行正式媒体转换。

## 4. LLM出站负向

本机受控HTTP夹具结果：

| 场景 | 结果 |
|---|---|
| loopback allowlist | PASS |
| 非allowlist域名 | PASS（拒绝） |
| HTTP 302重定向 | PASS（拒绝，自动重定向关闭） |
| 预算/响应上限超出 | PASS（拒绝） |
| 脱敏预览和审计 | PASS；隔离库2条审计行，不含API Key、完整Prompt或敏感值 |
| 真实第三方出站 | NOT RUN（明确禁止） |

命令：`dotnet server/bin/Debug/net8.0/VideoStudio.Server.dll --stage25-llm`。

## 5. 磁盘、缓存和删除保护

- 正常磁盘空间检查：PASS。
- 强制低空间阈值：高成本任务被拒绝，PASS。
- 缓存清理dry-run：发现1个过期未引用候选，`delete-performed=false`，文件仍存在，PASS；本轮没有正式清理。
- 被Manifest/Attempt引用Asset删除：服务层拒绝；直接外键删除也被RESTRICT拒绝，PASS。
- 普通API直接把Shot改为`Completed/Approved/Published`：服务层拒绝，保留审核门禁，PASS（代码路径）。

命令：`--stage25-safety`、`--stage25-domain`。

## 6. 未运行项

`test_task_submission_preflight.ps1`因既有PowerShell源文件解析错误未运行，状态为NOT RUN/BLOCKED，不计入PASS，也没有通过降低断言或扩大忽略范围处理。ComfyUI输入运行时检查、真实视频媒体和正式项目API路径仍待后续门禁。
