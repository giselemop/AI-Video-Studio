# 本地 Klein 关键帧验证包

只准备模型、预检及六张冻结候选 JSON，不访问云推理，不提交 ComfyUI `/prompt`。所有生成由 VideoStudio 业务队列统一调度。

复用现有 ComfyUI 0.31.0 / Python 3.13.2 / torch 2.11.0+cu130，未升级运行时或安装依赖。模型放在 `C:\install\AI\Models\Flux2Klein4B`，证据放在 `C:\install\AI\Data\VisualValidation20261024\keyframes-setup`。

## 准备顺序

1. `download_models.py` 默认仅列下载预算；显式 `--download` 才下载三份官方权重，固定字节数及 SHA-256，保留至少 30 GiB 空闲空间。支持保留 `.partial` 续传，拒绝覆盖不匹配的现有成品文件。
2. 由公共配置负责人将模型目录加入现有 ComfyUI 模型路径，按既有运行方式刷新。此包不修改公共路径文件、不重启服务。
3. `preflight.py --hash` 核实权重、节点、输入参数及模型可见性，不加载权重、不提交 GPU。
4. 显式选定 Data 下的人物源图，经业务服务上传后，执行 `prepare.py --source <源图绝对路径> --comfy-image <已上传的Comfy输入名>`。输出六份 API JSON 与源图/工作流哈希清单。
5. 业务队列串行消费六张 JSON；先人工判断未经超分的原图，不能用文件生成成功代替身份或画面验收。

下载器可用 `--artifact diffusion_models` / `--artifact text_encoders` 分开执行，各 `--workers 2`，总并发4。`--source huggingface --proxy http://127.0.0.1:7897` 仅给本 Python 子进程设置显式代理，不改系统配置；也支持已授权的官方 ModelScope 镜像。来源切换保留既有范围文件，最终始终按官方 SHA-256 校验。实际来源切换与 VAE 单独传输回执保存在证据目录。

`prepare.build_workflow(comfy_image, prompt, seed, width, height, filename_prefix)` 可供业务适配器调用。参数冻结为 distilled FP8 DiT、4步、Euler、CFG 1；BF16 文本编码器显式留在 CPU，目标默认 1024×576、batch 1，尺寸参数可显式指定。各候选始终引用同一女性768×768原图裁图，避免逐张串接造成身份漂移。参考图按照官方模板缩放至约1百万像素，保留比例；输出为16:9。前两张保持原始三分之四侧脸角度/视线/构图/光线，仅改变中性闭口与极轻闭口微笑；其他四张覆盖相对原角度左右各轻转10度与中性/微笑近景，不擅自正面化。源图裁剪不算本轮新生成，须在业务运行清单中标明。

`flux2_klein4b_keyframe_api.json` 与 `contract-definition.json` 供公共配置负责人原样复制并登记。工作流仅目标 latent / scheduler 有 width/height，参考图缩放没有独立 width/height，因此现有业务参数补丁不会误改参考尺寸；RandomNoise 的 noise_seed、Flux2Scheduler 的 steps、CFGGuider 的 cfg 兼容现有通用补丁。

官方依据：

- [Comfy 官方 Klein 指南](https://docs.comfy.org/tutorials/flux/flux-2-klein)
- [官方 distilled 图像编辑模板](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_flux2_klein_image_edit_4b_distilled.json)
- [DiT FP8 权重](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8)
- [Comfy 官方拆分 TE/VAE](https://huggingface.co/Comfy-Org/flux2-klein-4B)

许可分别记录：Klein 4B 权重、Comfy Klein 拆分包、Qwen3-4B 文本编码器为 Apache 2.0；现有 ComfyUI 核心代码为 GPL-3.0。没有使用 Klein 9B、FLUX.2 dev DiT 或其商业受限权重。此包选用 Klein Apache 2.0 仓库内的 VAE，记录实际来源与哈希。
