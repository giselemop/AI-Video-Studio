# 新生成效果预览（2026-09-11）

## 结论

技术生成完成，内容验收 Failed，允许发布 Blocked。本轮是新生成的约3.3秒人物近景，不是30–45秒剧情成片。未使用H3。用户已确认部署在中国、平台不限；全球发布许可仍需分平台核查。

## 现场与运行

- 接管时VideoStudio与ComfyUI未运行，MySQL在线。使用已有ComfyUI venv和当前Debug服务启动，回环监听18080/8188；未重装。
- 原配置Worker=0，AutoApplySchema=0，AllowDatabaseCreate=0。本次只为新服务进程启用Worker，保留禁迁移与禁建库；未修改系统环境变量或运行配置。
- 按先前授权再次通过维护命令重置admin并正常登录；凭据只存在工具内存，未归档。维护检查确认无Pending/Running任务。
- 新项目22：新生成能力预览_窗边来信_20260911。全部生成通过业务队列，无手工改任务状态。

## 新任务与真实输出

| 任务 | 工作流 | 结果 | 耗时 | 记录峰值显存 |
| --- | --- | --- | --- | --- |
| 1089 | 2 / SD1.5 portrait | 新关键帧640×832 | 6.624秒 | 3309MiB |
| 1090 | 551 / LTX v3 | 初版变脸，Failed | 15.828秒 | 10314MiB |
| 1091 | 551 / LTX v3 | 定向重试，仍有嘴部异常/动作不完成 | 12.846秒 | 11255MiB |

关键帧seed=2026091101，25steps；视频seed=2026091102，20steps，CFG3，320×416，请求73帧/24fps，尾帧guide72/0.45。两次视频仅增加首尾明确同身份绑定及重试说明，保持seed和其他采样参数不变。

初次使用I2V别名被预检422拒绝、未创建任务；改用系统支持的ImageToVideo类型成功提交，不绕过门禁。

Comfy prompt IDs：关键帧7deb310d-600e-47ca-90e6-e4731a1237e2；初版b7abf20e-fe9b-49b8-b603-7ddb47cfa81e；重试a68f6bb8-7ba0-4ccc-bf70-90982f4ee3e0。

## 缺陷证据

- 首版实际LoadImage首帧为本次输入，尾帧仍为character_reference.png，导致明显换人。重试通过referenceImages显式传入同一新关键帧，实际history确认两路均为本任务输入。尚未修复通用适配器默认保留模板参考的根本问题。
- 关键帧请求512×320，实际肖像工作流保留640×832；未把其宣称横幅生成通过。
- 原视频实际81帧、320×416、1000/41fps、3.321秒，与请求73帧/24fps有偏差；来源涉及模型解码/WEBP时基，尚待进一步修复。
- 抽帧：重试保持短发与背景，但嘴部有非预期动作，睁眼指令未明确完成。不能标记身份/动作通过。
- CPU后期仅等比缩放补边、规范24fps，未超分/修脸/插帧。静音，不宣称声音流程通过。

## 文件

- 展示版：C:/install/AI/Data/acceptance/new_preview_20260911/window_preview_720p.mp4
- 初版抽帧：C:/install/AI/Data/acceptance/new_preview_20260911/contact_sheet.jpg
- 重试抽帧：C:/install/AI/Data/acceptance/new_preview_20260911/retry1_contact_sheet.jpg
- 原始重试：C:/install/AI/Data/Artifacts/project-22/video/task-1091/v0001/v0001_task_1091_task_1091_attempt_1_9b6435b4_00001__00b3a0a72a41.mp4
- 展示版SHA256：C63780FCBB7D92DE8754CA26EBF2B5D3AB013D9DFA73D68F5977725056B27976。
- FFprobe确认展示版1280×720、H264、24fps、3.333333秒；竖幅内容左右补黑，不是原生720p细节。

## 成本与剩余验收

视频两次任务墙钟耗时合计28.674秒（不是独立GPU内核时间）；加关键帧合计35.298秒。未采集RAM峰值或功耗，不虚构电费。人工审核通过秒数0，每合格秒成本不可计算。

仍需修复参考槽位污染与帧数/时基偏差，重新验证动作。没有通过的能力不进入三条剧情生产或正式发布。
