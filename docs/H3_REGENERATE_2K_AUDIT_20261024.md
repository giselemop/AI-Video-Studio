# H3-Regenerate-2K 纯本地部署核查（2026-10-24）

核查 `Passed`；官方纯本地部署、项目接入和本轮 10 秒三镜头 2K 样片均 `Blocked`。阻塞是官方模块尚未开放本地部署，不是一次显存不足测试。未执行 GPU 推理，不能由此推断 RTX 4070 运行其他 2K 路线的能力。

## 用户目标与执行边界

先核查 H3-Regenerate-2K 能否在本机纯本地运行；可行才接入项目，制作同人物、同台词的 10 秒三镜头 2K 样片。允许慢速生成，不允许云端推理。

本轮只执行官方文档、代码及模型清单读取，本地环境与原片核验。新增 GPU 任务、云推理调用、权重下载均为 0，没有新样片。未安装社区扩展，未升级 ComfyUI 或修改原工作流。原片不充当本轮新结果。

## 官方公开内容

- 官方 README 的 H3-Regenerate-2K 段明确写明该模块尚未开源，待就绪后发布。
- Full 2K Workflow 使用本地 H3-Base 配合官方 H3-Context-IR、H3-Regenerate-2K API，并非完整本地工作流。
- 实际图生视频再生成脚本把源视频编码为 Data URL，向 `$MINIMAX_API_BASE/v2/video_regeneration` 发起认证请求。因此脚本文件存在不能证明提供了本地推理实现。只读取脚本，未执行。
- 官方 GitHub 完整树 281 项（未截断）、Hugging Face 文件清单 280 项，以及 Comfy-Org 模型清单 37 项均已存档。含 `2k` 的官方文件是示例媒体或 API 脚本；没有发现可部署的专用再生成模块入口。文件名检索仅作旁证，官方声明及实际调用方式是结论依据。
- 官方基础模型输出帧率为 24 FPS；2K 再生成不是 60 FPS 生成能力。未由“2K”自行指定 2560×1440，也未导出任意放大视频代替该路线。

可核验来源：

- [官方 H3-Regenerate-2K 说明](https://github.com/MiniMax-AI/MiniMax-H3/tree/d21241f0a4b3acbb34c97dae47fa417b7065e438#h3-regenerate-2k)
- [官方 Full 2K Workflow](https://github.com/MiniMax-AI/MiniMax-H3/tree/d21241f0a4b3acbb34c97dae47fa417b7065e438#full-2k-workflow)
- [实际再生成 API 脚本](https://github.com/MiniMax-AI/MiniMax-H3/blob/d21241f0a4b3acbb34c97dae47fa417b7065e438/scripts/readme/full-2k-i2va-h3-regenerate-2k.sh)
- [官方模型清单](https://huggingface.co/MiniMaxAI/MiniMax-H3/tree/42ed227ee7df40d41602854ae760620d6eb651fe)

## 社区复现的补充核查

发现 `ckinpdx/ComfyUI-MMH3Tools` 的本地 in-context 再生成实现，核对到提交 `031bb909061355d6d273dac6fe57601cf8a0197a`。它是第三方基于 H3-Base 的复现，不是已公开的官方 H3-Regenerate-2K 模块。不能把官方未开源扩大为“所有本地再生成方法都不存在”。

作者报告单窗口可工作，跨窗口存在偏离，也明确说明源视频占用参考槽、缺少官方 base_video 角色标记等区别。作者的成功报告不等于本机已实测。

该项目 README 要求 ComfyUI `v0.33.0-20-gff6c8a8a` 或更新，并涉及配套依赖；当前本机运行的是 `0.31.0`，核心提交 `dd79c64`。示例工作流使用 Ref2VA 模型、INT8 文本编码器及其他节点，本机固定路线是 FL2VA Q4 和 Qwen Q2_K_M。没有把整套示例安装到现有生产环境，也未测其 12GB 显存/32GB RAM 可行性。

因此社区路线仅完成源码/依赖核查，不能承诺官方等效效果、口型保持或本机 2K 成功。若后续选择这一实验，应作为单独路线保留来源标记、兼容性验证及独立短测，不冒充官方实现。

[社区作者的实现说明与局限](https://github.com/ckinpdx/ComfyUI-MMH3Tools/blob/031bb909061355d6d273dac6fe57601cf8a0197a/docs/regenerate-2k.md)

## 本机与项目实况

| 项目 | 本次读取结果 |
|---|---|
| CPU | Intel Core i5-13600KF |
| GPU | RTX 4070，12282 MiB 显存 |
| RAM | 31.82 GiB |
| C 盘空闲 | 约 36.8 GiB，随运行变化 |
| 本地 H3 loader | ComfyUI-GGUF-H3，`6d33de29cdc8bfa3f417dc0d96cbbc3b5412b8ed` |
| 固定基础模型 | FL2VA Q4、Qwen Q2_K_M、视频 VAE FP16、音频 VAE FP32 |
| 已登记规格 | 864×480、1376×768、1920×1088（1080p 裁切实验） |
| 本轮 GPU 耗时/峰值 | 未运行，不填写伪造峰值或预计耗时 |

已读取的本地 Comfy 节点包括 H3 图生视频与参考生成节点；未发现已安装的 Regenerate-2K 节点。四个固定资产的文件长度符合清单，本轮没有重新计算全部大模型 SHA256，不能声称本轮完成权重全量哈希验证。

项目分支 `main`，HEAD `d6ec38d076a8b0336d349c36df5c123f2c941ac8`；更新文档前工作区有 215 项既有改动，全部保留，无提交或推送。

同人物/台词来源仍为项目 34、最终任务 1263，四句为“哟，约会回来了？”、“哼，要你管。”、“好啦，不逗你了。”、“这还差不多。”。原三镜头成片 1280×720、24 FPS、10 秒，SHA256 `1b677efb8f9ee23b866bd157cfb5607fce4485ea7935fa0c4337b0639d2d44d1` 已核对。该片不是本轮 2K 结果。

## 恢复与后续

机器证据位于 `C:\install\AI\Data\H3Regenerate2KAudit20261024`：`audit.json`、固定版本官方 README/API 脚本、官方与社区文件树、社区说明/关键源码/工作流、来源哈希及原文件哈希。源视频没有上传到远程服务。

恢复时先读 `audit.json`。只有官方发布可用的本地再生成实现后，才重新核查模型、兼容性与短测，不因用户愿意等待就认定缺失模块可运行。现有 SeedVR2 能提供另一条本地细节修复/超分路线，但不是 H3-Regenerate-2K，本轮未自动切换或开始生成。
