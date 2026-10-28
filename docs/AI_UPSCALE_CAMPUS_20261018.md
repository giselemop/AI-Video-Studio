# 校园视频本地超分与帧率核验

> 后续更新：用户进一步要求生成阶段60FPS后，已另行完成LTX实验1169/1170，模型条件60FPS、新生成305帧，直接MP4，无外挂补帧。见[后续实验](LTX_NATIVE60_EXPERIMENT_20261018.md)。本报告下方“尚未验证”对应此前30FPS超分阶段，原超分片本身仍为30FPS。

日期：2026-10-18（Asia/Shanghai）。分支`main`，HEAD`d6ec38d`；原有大量未提交工作保留，本轮未提交或推送。

## 结果

技术Passed：两段原始校园视频经真实GenerationQueue GPU任务1166/1167进行两倍超分，CPU任务1168重新交付10秒、1280×720、30FPS、300帧、静音MP4。原始1162/1163素材及1164成片SHA-256前后相同，未覆盖。

抽样1/3/6.5/8.5秒及6.5秒局部对照可见建筑窗框/边缘略清楚；树叶依然有低分辨率源素材的柔化感。没有量化画质提升百分比，也没有仅凭技术成功批准内容。逐帧超分可能产生细小纹理跳动，动态内容留待用户观看。内容审核`NeedReview`，发布`Blocked`。

## 当前帧率与60FPS

| 文件/能力 | 实际情况 |
| --- | --- |
| 原生LTX校园素材1162/1163 | 512×320，24FPS，每段121帧，约5.041667秒 |
| 原始成片1164 | 1280×720，30FPS，300帧，10.000秒；后期帧率转换 |
| 超分素材1166/1167 | 1024×640，24FPS，每段121帧，原时序保留 |
| 增强成片1168 | 1280×720，30FPS，300帧，10.000秒 |
| FFmpeg运动补帧 | 当前安装的`minterpolate`滤镜已确认存在，可用于60FPS插帧；本轮未执行60FPS成片验证 |
| 模型原生60FPS | 未验证；本次固定LTX/H3契约均为24FPS，不通过改参数伪称原生60FPS |

60FPS插帧主要改善运动平滑度，不能增加源画面的真实细节；快运动、遮挡和镜头切换需要检查插帧伪影。当前超分对照保持相同30FPS，以便单独判断空间清晰度变化。

## 实施

- 官方[Real-ESRGAN x2plus](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.1)，67061725字节，SHA-256 `49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb`。模型位于中央Models/upscale_models，未纳入Git；[BSD-3-Clause许可证](https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE)。
- `config/video-upscale-assets.json`固定来源、模型哈希、输入/输出规格；`tools/upscale/prepare.py`只准备数据文件，复用既有Python/ComfyUI/torch，不重装环境。发现已有不同文件时保留并拒绝覆盖。
- `realesrgan-x2-video-v1`实验契约固定`sourceVideo`槽、24FPS/121帧及1024×640输出。工作流SHA-256 `8e5f2d6ca56743a16f052dfd71b11acee578531cc6c40479868593aa5ebdef6b`。使用原生LoadVideo/GetVideoComponents/UpscaleModelLoader/ImageUpscaleWithModel/CreateVideo/SaveVideo节点；没有新增自定义节点。
- `tools/upscale/enhance_campus.py`先FFprobe核验原始两段512×320/24FPS/121帧，冻结输入哈希，使用稳定请求键和进程锁；真实API登记工作流ID1172后通过服务队列提交，不直接调用ComfyUI `/prompt`。读取持久任务断点，失败不自动重生。
- `web/public/quality-compare.html`提供相同时间轴的滑动前后对照、播放、定位、全屏及单独视频入口。URL仅传本地资产相对路径；媒体仍经已有路径边界读取。

## 实机证据

设备RTX4070 12282MiB，约31.8GiB内存；ComfyUI0.31.0、torch2.11/cu130，GPU并发1。保持lowvram、关闭dynamic VRAM、reserve-vram1.5GiB和disable-pinned-memory。

| 任务 | 内容 | 实际时长 | 队列采样显存峰值 | 结果 |
| --- | --- | ---: | ---: | --- |
| 1166 | 林荫道两倍超分 | 23.008秒 | 1608MiB | Passed |
| 1167 | 校园楼两倍超分 | 22.893秒 | 1613MiB | Passed |
| 1168 | 10秒720p/30FPS交付 | 5.830秒 | CPU任务 | Passed |

显存值来自现有队列定时采样，并非硬件连续采集的瞬时峰值。ComfyUI对应两次推理日志约20.12/19.94秒，无OOM；任务时长包含队列内准备、推理和登记。

- FFprobe完整数帧：最终10.000秒、1280×720、30/1、300帧；FFmpeg全片解码无错误。
- 工作流契约self-test：12个契约Passed，含模型/工作流哈希、槽位/媒体参数及Guide/实验生产阻断。
- 实际API检查5项Passed：有效预检；缺槽、错误槽、原生fps60、错误输出尺寸均HTTP422，任务列表未增加。
- 复跑准备脚本及增强工具：Passed，沿用既有结果且未重复创建任务。
- Vue production build：Passed；原有第三方PURE注释与大chunk提示保留。
- Chrome实际页面播放/定位/分界线验证：Passed，完整播放10秒，200次同步采样最大时间差约0.000171秒，两路均结束，0 droppedFrames，0 pageerror。仅证明本次本机浏览器播放，不替代动态内容质量审核。
- 同时核实MiniMax H3任务1165已完成，独立MP4/WAV均可用；详情见[接入报告](MINIMAX_LOCAL_INTEGRATION_20261018.md)。

## 输出与复现

最终视频：`C:\install\AI\Data\Artifacts\project-25\video\task-1168\v0001\v0001_campus_morning_10s_realesrgan_x2_1996a7a6252a.mp4`。

状态、探针和源哈希：`C:\install\AI\Data\CampusUpscale20261018\run.json`。诊断抽帧/局部/浏览器截图同目录；实际API及浏览器验证摘要位于忽略目录`logs/upscale-20261018`，不含密码、Cookie、Token或Key。

对照地址：[本机同步对照](http://127.0.0.1:18080/quality-compare.html?before=Artifacts%2Fproject-25%2Fvideo%2Ftask-1164%2Fv0001%2Fv0001_campus_morning_10s_preview_021a088aa55d.mp4&after=Artifacts%2Fproject-25%2Fvideo%2Ftask-1168%2Fv0001%2Fv0001_campus_morning_10s_realesrgan_x2_1996a7a6252a.mp4)。

```powershell
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/upscale/prepare.py
# 若尚未登记新工作流，先通过现有工作台“扫描工作流”入口登记。
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/upscale/enhance_campus.py
```

本次无需API Key，未调用付费云服务。原有本地SD1.5/LTX、系统TTS及H3路线保留；实验超分没有自动升级为正式剧集发布路线。
