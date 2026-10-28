# AI Video Studio 本地 AI 栈核验（2026-08-11）

## 运行时

| 项目 | 已核验值 |
| --- | --- |
| VideoStudio API | `http://127.0.0.1:18080` |
| ComfyUI API | `http://127.0.0.1:8188` |
| ComfyUI API 服务版本 | `3.13.2` |
| Python | `3.13.2` |
| PyTorch | `2.11.0+cu130` |
| GPU | NVIDIA GeForce RTX 4070 12GB，约 12281 MiB |
| FFmpeg/FFprobe | `8.1.1`，可用 |
| 模型根目录 | `C:\install\AI\Models` |
| 工作流根目录 | `C:\install\AI\Workflows` |

## 已安装、可实际调用的模型

- 静态人物：`v1-5-pruned-emaonly-fp16.safetensors`。
- 人物 I2V：`ltxv-2b-0.9.8-distilled-fp8.safetensors`。
- Wan2.2：`wan2.2_ti2v_5B_fp16.safetensors`，保留为无角色参考/实验路线，不作为当前人物身份默认路线。
- 文本编码器：`t5xxl_fp8_e4m3fn_scaled.safetensors`、`umt5_xxl_fp8_e4m3fn_scaled.safetensors`。
- VAE：`wan2.2_vae.safetensors`。

## 关键缺口

当前实际扫描结果为 0 个 LoRA、0 个 ControlNet、0 个 IP-Adapter/CLIP Vision、0 个 FaceDetailer/ADetailer、0 个独立人脸修复模型和 0 个插帧模型。此次优化没有重新安装环境，也没有下载大模型；系统使用单脸参考图、VAE 重绘、CPU 人脸代理检查和保守 I2V 参数补足门禁。

## 版本化工作流

| 工作流 | 用途 | 状态 |
| --- | --- | --- |
| `08_portrait_quality_v2_api.json` | 640×832 静态人物质量基线 | 推荐静态人物入口 |
| `09_character_master_reference_v2_api.json` | 单脸 Master Reference 重绘 | 推荐角色锚点入口 |
| `10_ltx_face_stable_v2_api.json` | 更强 guide 的实验版 | 已验证不作为默认 |
| `11_portrait_fullbody_v1_api.json` | 全身构图实验 | 当前模型出现重复身体/重影，拒绝作为 Master |
| `12_ltx_face_stable_v3_api.json` | 旧版稳定结构 + 320×416/73 帧/guide 0.45/尾帧前 guideFrameIndex 72 | 当前人物 I2V 默认 |

## 默认参数

- 静态人物：640×832、30 steps、CFG 5.8、DPM++ 2M/Karras；先出 2 张候选，再人工选 Master。
- 人物 I2V Draft：320×416、24 FPS、73 帧、约 3.042 秒、输入强度 1.0、guide/reference strength 0.45、`guideFrameIndex=72`、`motionProfile=small`、锁定镜头。
- 5 秒及以上必须显式设置 `allowLongVideo=true`，进入实验档，不自动放行。
- 后处理默认只缩放、补边和转码；`deflicker`、`minterpolate` 默认关闭，避免脸部鬼影。
