# 2026-09-08 审核证据门禁续验

## 实际完成

新增 ManualQaGate，镜头和 Episode 人工通过时同时读取自动 QA JSON 中保留的 status，避免 Rejected → NeedReview → Passed 绕过上一轮只检查当前状态的实现。技术 hardFailure 无条件阻断人工覆盖；无 QA 版本、正在检查、缺失或损坏结果均拒绝通过。镜头存在 Open Critical/Error 时拒绝人工 Passed。

## 行为验证

执行 `dotnet run --project tests/VideoStudio.QualityHarness --no-restore -- --self-test`，退出码0。新增六个行为断言覆盖中间状态绕过、未验收整集、技术硬失败Override、损坏证据、QA进行中使用旧结果，以及正常待人工审核结果。

## 尚未达到验收

新增代码未替换18080现有服务；数据库端到端、并发审核竞态、结果与素材哈希绑定、严重内容问题关闭后的证据复验、前端真实审核交互仍待完成。不能把这些单元行为检查称作完整发布门禁通过。

当前真实认证结果仍为 configured=true / authenticated=false / setupAllowed=false。需用户在现有Chrome本地后台登录，才能继续受保护业务队列与真实生成。此限制来自用户原始授权中“不得绕过登录、权限或授权门禁”。

本轮GPU生成耗时0；没有新增视频、内容通过秒数或发布文件。合格成片成本尚无法测得。整体允许发布：否。
