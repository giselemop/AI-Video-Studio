<!-- character-story-20261027:start -->
> 2026-10-27：Actual Klein four-input execution tested: first two-person candidate duplicated actorA, directed repair passed preview inspection. This is bounded evidence, not general identity binding or H3 Ref2VA. H3 uses the exact inspected keyframe hash. Task1516 recovered one existing Comfy prompt after API restart. 详见[本轮验收](CHARACTER_STORY_ACCEPTANCE_20261027.md)。
<!-- character-story-20261027:end -->

# ComfyUI API 集成说明

## 2026-10-18 MiniMax 本地路线

`minimax_h3_local_i2v_api.json`为独立实验工作流，使用H3兼容GGUF节点、四个固定权重及单首帧，864×480/124帧/24FPS/20steps，原生音视频经既有队列处理。节点已加载，权重下载及真实H3验收仍Blocked。准备/启动/续接命令见[实施报告](MINIMAX_LOCAL_INTEGRATION_20261018.md)。无Guide LTX的121帧契约已升级comfy031-v2，修复旧减8帧映射；带Guide路线保留原映射。

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

## 3.1 Wan2.2 TI2V-5B 质量优先工作流（已验证但有画幅约束）

- API 工作流：`C:\install\AI\Workflows\05_wan22_ti2v_5b_api.json`。
- 运行模型：`wan2.2_ti2v_5B_fp16.safetensors`、`umt5_xxl_fp8_e4m3fn_scaled.safetensors`、`wan2.2_vae.safetensors`。
- 低显存起始参数：512×320 或按参考图比例匹配的 320×416、49 帧、24 FPS、单任务串行；640×352/73 帧只在短片稳定后再试，并记录峰值显存。
- 新建镜头和未指定工作流的图生视频任务优先使用 Wan2.2，LTX 仅作为工作流文件缺失时的回退。Wan2.2 仍要求参考图与输出画幅匹配，比例不匹配会产生首段伪影，不能宣称已经解决所有脸部漂移。
- 工作流使用 Wan 自己的 CFG/steps；服务端会按任务参数补丁同步宽、高、帧数、FPS、seed 和输出前缀。
- 2026-08-09 实测任务 69/70/71 均成功完成；512×320 横幅参考图比例不匹配时出现首段块状伪影，320×416 竖幅匹配输入后抽帧未见同类首段撕裂。
- 任务 71 峰值显存 11,954 MiB、耗时 31.647 秒、49 帧/24 FPS；该结果证明“比例匹配的竖幅短片”可用，也是当前质量优先默认路线的验收边界。

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
