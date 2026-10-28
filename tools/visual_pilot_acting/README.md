# LivePortrait 2–3 秒本地表演小样

本目录只负责官方 LivePortrait 人像实验的隔离准备和队列子进程。业务任务由主服务 `VisualActing` GPU 队列统一调度，本目录不提交任务，不运行后台服务。

- 独立运行时：`C:\install\AI\LivePortraitPilot\venv\Scripts\python.exe`，使用只读 bundled Python 3.12.14 创建。
- 官方源码：`KlingAIResearch/LivePortrait`，commit `9b294b3d0536135442ea73cb01e6cb3ca7029dd3`。只取得人像推理所需文件，不下载网上人物示例。
- 源码和权重清单：`Data/VisualValidation20261024/acting-setup/download-source.json`、`download-models.json`。源码逐项对照固定官方 Git blob；模型按官方 HF 文件页面 SHA256 核对。
- 推理期间禁止 socket HTTP 连接和 urllib 下载；缺模型或哈希漂移即失败，不自动下载/换模型。
- 显式计算配置：Torch CUDA 承担动画，ONNX CPU 承担检测/landmark；不开 `torch.compile`，不打开 WIP eye/lip retargeting。
- 许可证：LivePortrait MIT；所附 InsightFace 检测权重仅非商业研究。因此本实验输出 `NeedReview`，发布 `Blocked`，不进入商业发布链。

## 接口

仅依赖预检，不加载模型或 CUDA 上下文：

```powershell
& 'C:\install\AI\LivePortraitPilot\venv\Scripts\python.exe' run.py --preflight --receipt 'C:\install\AI\Data\VisualValidation20261024\acting-setup\preflight-unique.json'
```

GPU 队列调用：

```powershell
& 'C:\install\AI\LivePortraitPilot\venv\Scripts\python.exe' run.py --manifest '<Data内请求.json>' --receipt '<Data内任务私有receipt.json>'
```

请求：

```json
{
  "sourcePath": "C:/install/AI/Data/本轮新关键帧.png",
  "sourceSha256": "真实SHA256",
  "drivingPath": "C:/install/AI/Data/Artifacts/project-37/video/task-1293/...mp4",
  "drivingSha256": "真实SHA256",
  "driverOrigin": "existing-local-generated-task-1293; old expression driver, new appearance source",
  "outputDirectory": "C:/install/AI/Data/任务私有且尚不存在的staging目录",
  "durationSeconds": 2.0,
  "drivingStartSeconds": 0.0,
  "animationRegion": "exp",
  "drivingMultiplier": 0.6
}
```

`animationRegion` 仅允许 `exp` 或 `all`；时长 2–3 秒且不得超过驱动片实际长度。输入仅限 Data 内图片和 MP4；不接受 pickle 驱动模板。原片只读，驱动剪段和官方输出均进入新任务目录。片尾输出 JSON，同时写 receipt，核心字段为 `outputPath/outputSha256/width/height/fps/frames/durationSeconds/sourceAndModelHashesPreserved`。

输出画面保持驱动原帧率；无音频，原声由业务合成阶段独立保留，不把24/25FPS转换当作播放速度变更。旧驱动→新关键帧重演只能证明该局部重演链可用，不能称为新真人表演或自然度已提高。

## 准备和恢复

源码：`prepare.py --stage source`。完整清单存在时只校验本地哈希。

权重可明确选择 `prepare.py --stage models --transport modelscope-verified-mirror`；镜像传输版本 `f49a6df47080f1a36ce46812ec771c72b75dfbc5`，八项官方 SHA256 冻结，两个本地同哈希检测文件可复用。下载阶段可显式传 `--proxy http://127.0.0.1:7897`，不写系统代理。推理阶段始终禁网。

官方 CUDA wheel 固定为 `torch 2.3.0+cu121 / torchvision 0.18.0+cu121`；其他依赖见 `requirements-pilot.txt`。没有改动 ComfyUI、Qwen3TTS、SeedVR2 的环境。总准备预算12GB，下载和推理均要求至少20GiB磁盘余量。

安装完成后必须通过实际预检及队列小样，不能以下载目录存在宣称通过。
