# MiniMax H3 原生768p校园画质对照

生成日期：2026-10-18；续接核验与交付：2026-10-19（Asia/Shanghai）。分支 `main`、HEAD `d6ec38d`。既有未提交修改保留，本轮未提交或推送。

## 结果

技术 `Passed`：RTX 4070 12GB 已通过真实服务队列生成1376×768原生视频1174，以及864×480对照1175。两段均24FPS、124帧、5.166667秒视频，带原生AAC音轨和独立WAV；没有把480p视频放大后当作原生768p。完整数帧、全片解码和浏览器同步播放均通过。

相同展示尺寸和相同时间的抽帧中，768p砖缝、窗框边缘及灌木细节比480p放大版更清楚。两段仍有轻微构图漂移和局部纹理变化，不能据此宣布所有动作、人物或长片质量通过。内容状态 `NeedReview`，发布 `Blocked`。本轮没有客观感知质量评分或可信的画质提升百分比，也没有与Seedance 2.5进行受控比较。

768p耗时28分6.670秒，480p耗时9分23.191秒，前者约3倍。768p已经加入工作台的明确可选规格；原480p默认、本地LTX、系统中文TTS和此前60FPS实验均保留。未使用云API、未产生云端付费调用，无需API Key。

## 对照设计与首帧优化

- 新项目26；任务1171/1172新生成两张864×480校园首帧，使用SD1.5、28步、CFG6.5，未复用旧校园视频。
- 选1171：建筑占据主要画面，窗框、砖缝和树叶可用于细节检查。根据实际图片纠正视频提示词中的树、入口和道路位置，避免提示词与首帧冲突。
- 任务1173用已经安装且固定哈希的Real-ESRGAN x2plus准备首帧，再以Lanczos缩放/中心裁剪至1376×768。该首帧源于864×480合成图，超分可能补出合成纹理，不能当作真实高分辨率摄影素材。
- 两种H3规格共用准备后的同一张首帧、同一提示词、seed `2026101841`、20步、`res_multistep/simple`采样、124帧和24FPS。提示词采用官方结构，约束单镜头、自然晨光、建筑几何、轻微叶片运动和无对白环境声。
- 两段成片均未做视频超分、运动补帧、裁时或重新编码。对照页只在播放器中将480p放大；诊断联系图仅为查看而缩放，不改写视频。
- 此设计主要比较生成分辨率；两档都使用优化首帧和提示词，因此没有单独量化首帧优化或提示词优化各自贡献。
- 相同seed在不同尺寸对应不同形状的噪声张量，生成画面仍可能不完全相同；单个样本不能证明长期稳定的画质收益。

首帧SHA-256：`534d788b55e535cdb813ab80a766971d88f81d7ee073f636a122e873b3d1177e`。

## 真实任务与资源

硬件RTX4070，显存12282MiB，系统内存约31.8GiB。复用ComfyUI0.31.0、torch2.11/cu130、原Python环境与FFmpeg；GPU并发1。

| 任务 | 内容和实际输出 | 服务耗时 | 结果 |
| --- | --- | ---: | --- |
| 1171/1172 | 两张全新864×480候选首帧 | 见任务记录 | Passed |
| 1173 | 选定首帧准备为1376×768 | 见任务记录 | Passed |
| 1174 | H3原生1376×768，24FPS/124帧，视频5.166667秒，原生音轨及独立WAV | 1686.670秒 | Passed |
| 1175 | H3原生864×480，24FPS/124帧，视频5.166667秒，原生音轨及独立WAV | 563.191秒 | Passed |

两次H3均一次执行成功，没有自动重生或降规格。1174于10月18日22:26:03开始、22:54:09结束；1175于22:54:12开始、23:03:35结束。容器音频时基使格式时长显示5.167秒，不是补帧或延长画面。

| 资源记录 | 原生768p | 480p对照 |
| --- | ---: | ---: |
| 队列显存采样字段 | 8494MiB | 9534MiB |
| 独立nvidia-smi约2秒采样峰值 | 10426MiB | 10565MiB |
| 独立样本数 | 812 | 276 |
| GPU利用率达到90%以上的样本数 | 710 | 195 |
| 采样中最低可用系统内存 | 47MiB | 426MiB |

另有1个结束样本，共1089个。采样峰值不是连续硬件瞬时峰值；队列与nvidia-smi测量方式、时刻不同，不能混作同一指标。480p峰值略高也不能解释为其计算量更大。

## 为什么会看到GPU为0

日志明确记录H3文本编码器 `load device: cpu, offload device: cpu`。当前低显存配置将Qwen3-VL 32B编码器放在CPU，并将一部分视频模型卸载至系统内存；提示词/首帧编码和模型搬运阶段会出现CPU高、GPU低。采样阶段已实测GPU96%–100%，而非全程CPU生成。

用户截图中的图表为3D、Copy和视频编解码，不等同于CUDA计算曲线；但当时也确实处于CPU阶段，不能只归因于图表选错。生成结束且队列空闲后GPU接近0%正常。系统内存曾接近耗尽，低显存卸载与内存压力共同影响速度，未强制把整套模型塞入显存。

## 已实施的流程改动

1. `MiniMaxLocalService`增加明确的 `baseline480` / `quality768` 规格，分别固定864×480和1376×768，其余参数仍124帧、24FPS、20步。历史请求未指定规格时仍走原480p；未知规格或规格/工作流不一致直接拒绝。
2. 安装、登记、提交前检查和执行前检查覆盖两种固定工作流及四个模型的哈希；原生H3质量检查明确要求124帧，保留原生音轨。两种受管工作流都禁止因OOM静默改参数，执行快照保留首帧/工作流证据。
3. 新增首帧准备契约 `h3-quality-keyframe-x2-v1`，实验用途、固定1376×768、显式 `firstFrame` 槽及Real-ESRGAN模型哈希。H3主流程使用自身受管固定文件检查，不能冒称它已走通用契约。
4. 工作台增加生成规格选择和历史规格显示；768p清楚标为实验，显示实际尺寸和资源说明，不修改默认路线。
5. 新增可接续生成工具、资源采样、接口负向检查和诊断抽帧工具。保存稳定幂等键、任务ID及首帧哈希；结果未知时先查已记录任务，不盲目提交。
6. 新增同步滑动对照页：完整播放、同步定位、分界线、单独播放链接。对照默认静音，单独视频保留原生声音；声音内容尚未人工审核。

| 工作流 | SHA-256 |
| --- | --- |
| `minimax_h3_local_i2v_api.json` | `66b77a2cbfd64af481a65f26a222c3a1914b0756240a6e49e049aadbaf4d762c` |
| `minimax_h3_local_768_i2v_api.json` | `a0698b03e9d14e575cb808c2d4e5178f75a8ccecf9d9b892bbe587cda388c1e5` |
| `h3_keyframe_upscale_api.json` | `4e9ee28f4e5bc4c7b6c1f261570e529ea874f7b46bcc497d3d09911147d447e4` |

两种H3 JSON仅条件节点的宽高不同。主模型仍是原H3 FL2VA Q4，编码器仍Qwen Q2；没有换为参考视频文字中标注的官方INT8。四个组件及GGUF加载器修订沿用 `config/minimax-local-assets.json`。

## 验证与续接

- .NET Release构建、发布：0警告0错误。Vue生产构建Passed，既有第三方PURE注释和大chunk提示保留为性能事项。
- MiniMax本地回归22项、H3回归15项Passed；14个通用工作流契约自检及Guide/实验生产阻断Passed。
- 实际API检查9项Passed：两档有效预检；混用规格/工作流、768p缺少profile、60FPS、121帧、8步、错误宽度、未知profile均422，前后最近任务ID集合不变。
- 新服务重启后首次预检遇到模型全文件哈希冷缓存超时；检查工具改为先以600秒有界超时完成本地校验，再跑预检，9项复测Passed。无GPU任务因此重复提交。
- 前端及真实媒体7项Playwright测试Passed：完整播放、原始视频尺寸和时长、两路解码帧数至少120、同步定位差小于一帧、分界线、非法媒体路径拒绝，以及原有MiniMax上传/项目/幂等行为。没有把浏览器解码通过当作内容审核。
- FFprobe实际数帧124和FFmpeg全片解码Passed；MP4内嵌prompt确认首帧哈希、两档原生尺寸、帧数、同一提示词/种子、20步及24FPS；不存在视频超分/补帧节点。
- 准备工具和生成工具复跑Passed，复用1171–1175；续接前后最新任务仍1175。只读取已有结果完成核验，没有再次提交GPU任务。
- API发布后PID39812；数据库、ComfyUI、FFmpeg在线，服务和Comfy队列均空闲，LocalOnly回环访问保留。未执行数据库结构迁移。
- `git diff --check` Passed；秘密扫描只检查本轮源码/文档。模型、媒体、配置秘密和运行日志均不纳入Git。中央Data目录位于仓库外。

生成阶段的1174已有首帧执行快照和视频内嵌prompt；其QC的MiniMax摘要当时仍只对旧480p文件生成。收尾代码已将摘要分支同步到两个受管工作流，未回写旧任务伪造当时的QC数据，本次对照依据实际媒体及保存的执行记录核验。

## 产物与复现

状态、全部prompt/探针：`C:\install\AI\Data\H3Quality20261018\run.json`。

同目录保存 `resource-samples.json`、`admission-checks.json`、`runtime-check.json`、`validation-summary.json`、`workspace-check.json`、`review.json`、`browser-comparison.png`、`comparison-contact.png`、`comparison-crops.png` 及各时刻原始抽帧。原视频SHA-256分别为：

- 768p：`3e64b9d966a049e71af19d8ccdcc619e8e5d206bd89be8b9df8d45a3b2c57e93`。
- 480p：`d8abc83c7233c9b559704c414a59b522a4ad6565e1663a0d1681f212b24fe3ee`。

视频与音轨路径直接保存在run.json；对照页完整链接在review.json。诊断抽帧前后原视频及首帧哈希不变。

```powershell
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/minimax/prepare_quality.py
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/minimax/run_quality.py --stage frames
# 查看候选首帧后明确选0或1；本次已固定0，重复运行不会新建任务。
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/minimax/run_quality.py --stage generate --candidate 0
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/minimax/check_quality_admission.py
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/minimax/review_quality.py
```

现有结果已完成时无需再次运行frames阶段；保留报告即可接续。不同实验应另建报告目录及明确参数，不删除此报告冒充复测。

## 参考与边界

- [MiniMax H3官方概览](https://github.com/MiniMax-AI/MiniMax-H3#system-overview)：原生24FPS；Base开源发行与官方Context-IR、2K再生成能力区分。
- [官方提示词参考](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/base-en.txt)：首帧锚点、分镜时序和声景结构。
- [官方集成索引](https://github.com/MiniMax-AI/awesome-minimax-h3-integration#by-vram-and-hardware)：小显存量化/卸载路线；不替代本机实测。
- [用户提供的X视频](https://x.com/supereasyit/status/2111817625076638179)：作者画面标注1376×768、521.63秒、“RTX4080S32G”、官方fl2va_int8；硬件改装/显存等无法独立确认，不能直接拿该耗时与本机4070/12GB/Q4比较。其人物近景、首帧和后处理也与本次校园建筑不同。

本轮完成的是当前本机配置的一对5.17秒校园实验。10秒连续原生768p、原生768p/60FPS、人物身份/复杂动作、中文对白和正式剧集应用均没有因此得到验证；后续需分别立项实测和内容审核。
