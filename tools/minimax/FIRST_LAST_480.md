H3首尾双帧本地实验（2026-10-24）

- profile：`firstlast480`，独立工作流`minimax_h3_local_fl2v_480_api.json`。
- 保留原FL2VA Q4、Qwen Q2_K_M和两套VAE，未修改模型清单。
- 两张输入必须为Data下的864×480静态PNG/JPEG/WebP，提供各自SHA256；124帧、24FPS、20步固定。最后参考目标帧索引为123。
- 首尾分别绑定LoadImage 5/16，不使用参考图顺序推断。预检读取实际文件与FFprobe规格；执行重新核对源哈希、复制后哈希，再绑定GPU图。
- 只允许独立实验，没有Shot/Episode/ProductionRun关联，内容仍需人工复核。

部署新后端后，沿用现有本机访问方式先调用`POST /api/minimax/local/register`。从`GET /api/minimax/local/status`的generationProfiles选取firstlast480，或调用既有API获取新工作流ID。

`POST /api/minimax/local/video`示例（实际生成统一由主验证runner控制，示例不自动执行）：

```json
{
  "projectId": 1,
  "profile": "firstlast480",
  "prompt": "A single gentle gesture with the same fictional person and consistent room lighting.",
  "inputImagePath": "VisualValidation20261024/inputs/first.png",
  "lastFramePath": "VisualValidation20261024/inputs/last.png",
  "firstFrameSha256": "REPLACE_WITH_ACTUAL_FIRST_FRAME_SHA256",
  "lastFrameSha256": "REPLACE_WITH_ACTUAL_LAST_FRAME_SHA256",
  "seed": 2026102401,
  "steps": 20
}
```

必须带稳定的`Idempotency-Key`。路径、哈希或规格不符会在写入任务前拒绝；不会更换模型、裁切参考或降规格。

只测试、不生成GPU任务：

```powershell
dotnet run --project C:\install\AI\VideoStudio\tools\minimax\h3_firstlast_selftest\H3FirstLastSelfTest.csproj -- C:\install\AI\Data\VisualValidation20261024\h3-integration
```

该测试运行旧H3与MiniMax回归，再验证真实合成色块PNG的解码、哈希、画幅、路径边界及双槽绑定；合成测试图不是用户验证包的成片或画面效果结果。

新增工作流及契约可由`prepare_firstlast480.py`幂等核对。它保留已有不同版本，不提交GPU任务。
