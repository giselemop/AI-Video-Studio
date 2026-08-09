# ComfyUI API 集成说明

## 1. 当前连接

- Base URL：`http://127.0.0.1:8188`
- 根目录：`C:\install\AI\ComfyUI`
- 模型根目录：`C:\install\AI\Models`
- 工作流根目录：`C:\install\AI\Workflows`
- 输入/临时输出由现有 ComfyUI 目录管理，最终媒体下载到 `C:\install\AI\Data`。

最近健康检查：ComfyUI 在线，GPU 为 NVIDIA GeForce RTX 4070，`/system_stats` 报告 PyTorch `2.11.0+cu130`、`comfyui_version=0.31.0`，CUDA 设备总显存约 12GB。

## 2. 使用的端点

| 端点 | 用途 | 真实要求 |
| --- | --- | --- |
| `GET /system_stats` | 在线、版本、设备、总/空闲显存 | 任务前检查显存门禁 |
| `POST /prompt` | 提交 API 格式工作流 | 必须保存返回的 `prompt_id` |
| `GET /history/{prompt_id}` | 轮询执行状态、错误和节点输出 | 只有真实完成才推进任务 |
| `GET /view?filename=...&subfolder=...&type=...` | 下载输出 | 下载后登记 SHA256/媒体元数据 |
| `POST /interrupt` | 取消当前生成 | 取消后重新检查队列和数据库状态 |
| `POST /free` | 尝试释放模型缓存 | 任务结束后按服务支持情况调用 |

AI Video Studio 对外提供 `/api/health`、任务和生产接口；它不通过浏览器点击 ComfyUI，也不写入假结果。

## 3. 当前工作流

扫描目录后当前登记 8 个工作流，其中核心生产链使用：

- `01_portrait_quality_api.json`：SD1.5 人物关键帧。
- `02_ltx_i2v_quality_api.json`：LTX 图生视频，默认约 512×320、121 帧、24 FPS。
- `06_scene_keyframe_quality_api.json`：场景关键帧。
- `07_cinematic_shot_presets.json`：电影镜头提示词/预设。

工作流扫描器根据文件名识别 `Image`、`ImageToVideo`、`Motion`、`Enhancement` 等类型，并把可修改的节点参数登记到数据库。提交任务时服务会修改 Prompt、负面 Prompt、seed、宽高、帧数、CFG、steps、输入图片和输出前缀；具体能否修改以 API 工作流节点结构为准。

当前模型登记 3 个、LoRA 登记 0 个。没有已安装的 IP-Adapter/ControlNet/角色 LoRA，因此角色身份控制只能使用现有参考图、Prompt、seed 和镜头设计。

## 4. RTX 4070 参数门槛

- 只允许 GenerationQueue 单任务占用 GPU；不要手工同时启动多个视频工作流。
- 关键帧先用 512×320 或 768×512；I2V 先用 73/97/121 帧。
- 3/4/5 秒基线对应 73/97/121 帧、24 FPS；默认优先 5 秒但先用一镜头验证动作。
- OOM 时先降低帧数，再降低分辨率、候选数和 steps；不直接把 1080P 输入视频模型。
- 1080P/30 FPS、插帧、去闪烁和封装由 FFmpeg 后处理完成。

## 5. 故障诊断

1. 先检查 `GET http://127.0.0.1:18080/api/health` 和 ComfyUI `/system_stats`。
2. 检查 `C:\install\AI\VideoStudio\logs\comfyui.log`、`comfyui_error.log`、`server.log`，不要把其中的凭据复制到报告。
3. 确认工作流、模型文件和输入参考图都存在且路径在允许目录内。
4. 只重试失败 Shot；修改与错误有关的参数，并把前后 seed/分辨率/帧数/参考图记录在任务日志。
5. 同一问题连续三轮仍失败时标记 `Blocked`，说明具体错误和缺少的外部条件，不继续盲目生成。
