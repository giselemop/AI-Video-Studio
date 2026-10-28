# AI Video Studio 人物生成架构替换执行结果

执行日期：2026-08-18\
本轮证据目录：`C:\install\AI\Data\QA\character_architecture_replacement_20260818\run_01`\
最终决策：**ARCHITECTURE_SELECTION_INSUFFICIENT**

## 结论

本轮 Survey 记录了 8 条路线，Top 3 为 SiTH、StdGEN、SAM 3D Body。SiTH 与 StdGEN 已进入隔离部署/实际 Mini Probe 流程；SAM 3D Body 的官方 checkpoint 下载被 gated approval 阻断，因此没有伪造推理结果。当前结果只决定“是否值得进入下一轮 POC”，没有修改 ModelRouter、生产页面、主 API 或 Identity Worker。

## 本轮边界

没有重跑 InstantID/PuLID/FaceID 主 Benchmark；历史 SDXL 结果仅作为“替换架构”基线。没有做 Character LoRA、I2V、Wan Animate、HunyuanVideo、Driving/Pose、TTS、字幕、25/60 秒成片或生产 Master。

冻结 QA：raw cosine ≥0.5；front abs yaw <15°；30°视角 abs yaw ∈[12,40)；45°视角 abs yaw ∈[27,62)；Dual = IdentityPass 且 ViewPass 且无 HardReject；多视角集合还要求 5 个核心视角、至少 4/5 ViewPass、跨视角相似度阈值 0.5。

## 候选实际状态

| 候选 | 技术路线 | 实际状态 | 生产判断 |
|---|---|---|---|
| SiTH | 单参考图扩散式背面补全 + SMPL-X/纹理重建 | GENERATED；本轮 probe 边界为 back-view diffusion，完整 mesh 依赖未验证 | 不进入生产 |
| StdGEN | 语义分解多视角扩散 + S-LRM | GENERATED；输入是 head-and-shoulders，不能冒充 full-body canonicalization | 不进入生产 |
| SAM 3D Body | promptable 参数化全身 mesh | 官方 checkpoint approval required；未运行 | 不进入生产 |

Mini Probe 机器指标详见 `09-mini-probe-results.json`，五视角门槛详见 `10-multiview-mini-benchmark.json`。实际样例与失败状态页：

- [candidate-a-multiview.html](C:\install\AI\Data\QA\character_architecture_replacement_20260818\run_01\html\candidate-a-multiview.html)
- [candidate-b-multiview.html](C:\install\AI\Data\QA\character_architecture_replacement_20260818\run_01\html\candidate-b-multiview.html)
- [candidate-c-multiview.html](C:\install\AI\Data\QA\character_architecture_replacement_20260818\run_01\html\candidate-c-multiview.html)
- [architecture-comparison.html](C:\install\AI\Data\QA\character_architecture_replacement_20260818\run_01\html\architecture-comparison.html)

## 硬件与阻塞证据

本机为 RTX 4070，nvidia-smi 报告 12,282 MiB 显存；本轮所有数值均不能外推到 24GB、40GB 或 80GB。SAM 3D Body 的两个官方 checkpoint 仓库均返回 `Access denied. This repository requires approval.`。SiTH 的完整 mesh 路径还缺少已验证的 kaolin、nvdiffrast、SMPL-X 运行栈；因此只把成功的扩散阶段记为 partial probe。

## 回归

主 API、ComfyUI、Identity Worker 在本轮保持 loopback 健康；Worker 仍为 `127.0.0.1:18084`。候选代码、sidecar 依赖、权重和输出均位于 `C:\install\AI\CharacterArchitectures`；本轮只在 VideoStudio 的 `tools/character_architecture_replacement` 增加证据/探针脚本，没有重启主 API、没有修改 Worker、没有改动生产 ModelRouter 或生产页面。回归详情见 `13-build-regression.json`。

## 官方资料

- [SiTH official repository](https://github.com/SiTH-Diffusion/SiTH)
- [StdGEN official repository](https://github.com/hyz317/StdGEN)
- [SAM 3D Body official repository](https://github.com/facebookresearch/sam-3d-body)
- [GAS official repository](https://github.com/humansensinglab/GAS)
- [Pippo official repository](https://github.com/facebookresearch/pippo)
- [CharacterGen project page](https://charactergen.github.io/)
- [MVD-HuGaS paper page](https://huggingface.co/papers/2503.08218)
- [HumanGaussian official repository](https://github.com/alvinliu0/HumanGaussian)
