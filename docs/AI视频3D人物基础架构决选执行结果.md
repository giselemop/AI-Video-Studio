# AI Video Studio 3D 人物基础架构决选执行结果

执行时间：2026-08-18 22:52:41 +0800\
证据根目录：`C:\install\AI\Data\QA\3d_character_foundation_20260818\run_01`\
最终状态：**NO_3D_CHARACTER_FOUNDATION_READY**

## 结论

本轮没有任何候选达到“单一 Identity Master → 持久化 3D/canonical 表示 → 同一表示五相机渲染”的硬门槛，因此不选 HumanSplat、SiTH 或 SAM 3D Body，也不把 Pippo 作为本地候选。没有生成伪造多视图、伪造 mesh 或伪造身份分数。

## 36 项回传

1. 最终状态：`NO_3D_CHARACTER_FOUNDATION_READY`。
2. 推荐 foundation：无；当前不允许进入 Character Canonical Pack POC。
3. HumanSplat 部署：官方仓库已隔离到 `C:\install\AI\CharacterArchitectures\HumanSplat`，源码可编译，导入在缺少 `diffusers` 处停止。
4. HumanSplat 表示：未创建；核心 `out/178000/model.safetensors` 不存在。
5. HumanSplat 五视图：未执行；没有 persistent Gaussian 和 renderer 输出。
6. HumanSplat QA：身份、视角、相机单调性、重复渲染、重开渲染均为未运行。
7. HumanSplat VRAM：无完整推理峰值；不能用未完成探针推断 12GB 可行。
8. HumanSplat 门禁资产：PIXIE/SMPL-X 需要官方账号资产，`xformers`、`diffusers` 和 Windows rasterizer 也缺失；未提交凭据。
9. SiTH 部署：已有官方 `SiTH_diffusion` 权重，并下载官方 ETH `recon_model.pth`；完整入口仍被环境/资产门禁阻断。
10. SiTH 完整表示：未创建 mesh、纹理 mesh、GLB/OBJ canonical 输出。
11. SiTH 五视图：未执行；之前的背面 diffusion PNG 明确不计入本轮。
12. SiTH QA：无五视图输入，身份/视角/相机/重开/重复渲染均未运行。
13. SiTH VRAM：历史背面 sampler 约 2.6 GiB allocated 仅是扩散子步骤，不能代表完整 mesh pipeline。
14. 全身参考：冻结 Identity Master 是 head-and-shoulders；现有 A/B 全身候选与其 raw cosine 约为 `-0.0454` 至 `0.0682`，不作为同人真值，状态 `BLOCKED_FULL_BODY_REFERENCE`。
15. SiTH 依赖：Windows/Python 3.13/Torch 2.11/CUDA 13 与官方 Ubuntu 22.04/Torch 2.1/CUDA 12.1 目标不一致；`kaolin`、`nvdiffrast`、`smplx`、`trimesh` 等不完整，触发 `DEPLOYMENT_COMPLEXITY_BLOCK`。
16. SAM 3D Body 权限：DINOv3 和 ViT-H 官方 HF checkpoint 轻量请求均返回 `GatedRepo`/需要审批；按要求停止。
17. SAM 3D Body 探针：未在无权重时重复大下载；无表示、无渲染。
18. Pippo：官方 README 说明是 code-only release without pre-trained weights，本轮仅作参考。
19. 统一相机：契约为 Front 0°、Left30 -30°、Right30 +30°、Left45 -45°、Right45 +45°，elevation/roll 0；没有表示所以没有渲染。
20. 跨视图身份：要求的 8 组 pair 未运行；没有真实五视图集。
21. 表示持久化：无 `.ply/.splat/.obj/.glb/.gltf` 候选输出可验收。
22. 同一表示：未满足；没有把五张 PNG 视为一个 3D 表示。
23. Repeat Render Test：未运行；无表示。
24. Representation Reopen Test：未运行；无可保存/重开资产。
25. 本机 12GB：RTX 4070 12,282 MiB；本轮没有任何候选证明完整 foundation 在此容量可用。
26. 云端 24GB+：仅为条件性下一步，可能缓解显存/依赖压力，但不能消除 checkpoint、账号资产、许可证和输入真值门禁。
27. 许可证：HumanSplat MIT、SiTH MIT、SAM 3D Body 使用 SAM License；实际发布前仍需逐项核对权重及依赖许可。
28. 硬件阻塞证据：环境、GPU、CUDA、WSL 状态、依赖、缺失路径、官方 HTTP 门禁均写入 JSON。
29. 构建回归：本阶段证据脚本 `py_compile` 与 `git diff --check` 结果写入 `18-build-regression.json`；未改生产 ModelRouter、页面或工作流。
30. JSON 完整性：`01` 至 `19` 均在本轮证据根目录；另有 Pippo 参考状态 JSON。
31. HTML：四个候选/对比页面均明确显示 BLOCKED 或 NO READY CANDIDATE，没有伪造样本。
32. Canonical Pack：`17-canonical-pack-preview.json` 状态 `NOT_READY`，文件列表为空。
33. 磁盘：环境基线写入 C 盘总量、已用量、剩余量；下载的 SiTH 官方文件位于隔离目录。
34. 脚本：执行工具位于 `C:\install\AI\VideoStudio\tools\3d_character_foundation`，包括 baseline、HumanSplat、SiTH、SAM/Pippo、finalize。
35. READY_FOR_CHARACTER_CANONICAL_PACK_POC：`false`。
36. 下一方向：寻找支持单图直接重建 Gaussian/mesh/4D canonical 的下一代原生方案、商业服务或 24GB+ 云 GPU；不要回退到每个视角独立 FaceID 生成。

## 机器可读证据

- 统一证据根目录：`C:\install\AI\Data\QA\3d_character_foundation_20260818\run_01`
- 最终验收：`C:\install\AI\Data\QA\3d_character_foundation_20260818\run_01\19-final-acceptance.json`
- HumanSplat 探针：`C:\install\AI\Data\QA\3d_character_foundation_20260818\run_01\05-humansplat-probe.json`
- SiTH Full Pipeline：`C:\install\AI\Data\QA\3d_character_foundation_20260818\run_01\08-sith-full-pipeline-probe.json`
- SAM checkpoint 权限：`C:\install\AI\Data\QA\3d_character_foundation_20260818\run_01\11-sam3d-probe.json`
- 统一相机：`C:\install\AI\Data\QA\3d_character_foundation_20260818\run_01\13-unified-camera-render.json`
- 对比：`C:\install\AI\Data\QA\3d_character_foundation_20260818\run_01\15-method-comparison.json`

## 官方资料

- [HumanSplat 官方仓库](https://github.com/humansplat/humansplat)：单图预测 3D Gaussian；其 README 说明需要 PIXIE/SMPL-X 账号资产。
- [SiTH 官方仓库](https://github.com/SiTH-Diffusion/SiTH)：body fitting、back hallucination、textured mesh reconstruction 完整链路。
- [SAM 3D Body 官方仓库](https://github.com/facebookresearch/sam-3d-body)：官方 checkpoint 需按 INSTALL 流程申请访问。
- [Pippo 官方仓库](https://github.com/facebookresearch/pippo)：当前官方 README 标注为无预训练权重的 code-only release。
