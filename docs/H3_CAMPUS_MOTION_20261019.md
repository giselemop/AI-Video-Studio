# H3校园前移镜头与树枝运动实验

日期：2026-10-19（Asia/Shanghai）。分支 `main`、HEAD `d6ec38d`；保留既有未提交修改，本轮未提交/推送。

技术 `Passed`：新视频1176已经生成，实际1376×768、24FPS、124帧、视频5.166667秒，原生音轨和独立WAV可用。抽帧及实际浏览器呈现可见镜头朝入口靠近、近树相对墙面位移和枝叶变化，运动幅度明显超过旧版1174。枝叶仍有运动模糊和局部细节重绘；运动自然度、建筑几何及声音内容仍为 `NeedReview`，发布 `Blocked`。

## 问题与授权范围

用户观看1174/1175后认为画面近乎静止。实际解码两段各124个不同帧，但原提示词要求固定机位、空庭院和少量树叶轻动，不适合展示动态能力；“帧不同”和技术通过都不能替代动作验收。

用户随后明确要求加入运动。本次重新生成同一校园的原生768p视频：镜头沿右侧浅色道路朝拱门前移，前后景产生可见视差，树枝及大簇树叶明显随风摆动。保持空校园，不额外增加人物或收费云调用。

## 固定输入与执行

- 项目26；原生768p旧版任务1174作为对照；新任务1176通过现有API/GenerationQueue执行成功，GPU并发1，自动重试0，一次完成。
- 首帧明确复用本实验选定的1173图片，用于控制变量；没有复用旧视频冒充新生成。
- 首帧SHA-256：`534d788b55e535cdb813ab80a766971d88f81d7ee073f636a122e873b3d1177e`。
- 原生规格1376×768、24FPS、124帧、20步、seed2026101841，`quality768`固定工作流1242。模型仍为既有H3 Q4/Qwen Q2，四模型及工作流哈希检查保留。
- 主要生成变量为提示词：取消固定机位/少量轻动约束，改为持续前移约两米、入口在尾帧约增大三分之一、明显视差及枝叶摆动。上述数值是生成意图，需对实际输出核验，不能当作已实现效果。
- 1176开始于08:31:42.789、完成于09:00:14.502，服务耗时1711.713秒（28分31.713秒）；ComfyUI日志为约28分26秒。生成与完整媒体验证在30分钟服务期限内完成。
- 内嵌prompt核对首帧哈希、动作描述和seed一致；原生规格/数帧及全片解码Passed，无成片超分、补帧或用旧视频制作后期推拉镜头。

运行报告：`C:\install\AI\Data\H3Motion20261019\run.json`；资源采样：同目录 `resource-samples.json`。旧实验 `H3Quality20261018` 的报告、视频和图片保持原样。

## 本轮工具与预览

- `tools/minimax/run_motion.py`：显式复用首帧、保存输入及旧视频哈希、稳定幂等键、已记录任务查询；提交结果未知时停止自动提交，等待核对。全片规格/解码及内嵌prompt核验后才标技术Passed。
- `tools/minimax/monitor_quality.py`：新增可选中央Data报告路径，继续约2秒资源采样，默认旧实验行为保留。
- `tools/minimax/review_motion.py`：生成0.5/2.5/4.5秒新旧抽帧及联系图，统计真实解码帧和灰度变化；不把变化幅度当作动作质量分数。
- `web/public/h3-motion-compare.html`：新旧各自完整画面的并排播放，尝试静音循环播放，点击画面暂停、同步定位及新版原生声音开关。避免拿旧480p/768p分界线标签描述这次同分辨率的动态对照。
- 新增真实媒体播放测试 `web/tests/h3-motion-compare.spec.js`，两项Passed：原生尺寸/时长、实际循环回绕、播放/点击暂停、同步定位、实际呈现3.5秒帧、无JS错误及非法媒体路径拒绝。定位检查等待实际视频帧回调，避免把currentTime赋值当作画面已更新。

## 实际资源与核验

- RTX4070显存12282MiB；沿用约31.8GiB内存、原低显存卸载配置及四模型固定版本。约2秒独立采样828个，峰值10653MiB；队列采样9473MiB。两种指标的测量方式/时间不同，不是连续硬件瞬时峰值。
- 编码阶段最低采样可用内存165MiB；采样阶段GPU持续高负载。没有因内存压力更换模型或降低规格。
- 新旧视频实际解码均124帧且各不相同。344×192灰度相邻帧平均绝对变化：旧版0.4763，新版12.9575；0.5秒与4.5秒帧差均值为11.7276/57.3234。这些数值仅说明像素变化，受亮度、纹理和运动共同影响，不是质量评分或“运动提升倍数”。
- 0.5/2.5/4.5秒联系图和3.5秒浏览器实际呈现均可见明显靠近入口及近树位移。没有标定场景尺寸，不能把提示词中的两米/三分之一当作实测物理量。
- Vue生产构建Passed，既有PURE注释/大chunk提示仍在；3个Python脚本编译Passed。本轮无C#或数据库结构变更，无需后端重启。
- 并发启动第二个runner被文件锁拒绝，最新任务仍1176；完成后重跑脚本读取1176及现有产物，前后最近任务ID一致，未重复提交GPU任务。
- 原首帧和原1174视频哈希不变；原1175及旧画质对照保留。API、数据库、ComfyUI在线，完成后服务/Comfy队列空闲。
- `git diff --check`和本轮源码/文档高置信秘密扫描Passed；新权重/媒体未进入Git。内容审核/发布资格与技术状态继续分开保存。

## 产物与接续

新视频：`C:\install\AI\Data\Artifacts\project-26\video\task-1176\v0001\v0001_task_1176_task_1176_attempt_1_e1f16d1d_00001__bee4b38f85cb.mp4`。

独立音轨：`C:\install\AI\Data\Artifacts\project-26\audio\task-1176\v0001\v0001_native_audio_task_1176_20953f3aab75.wav`。

新视频SHA-256：`bee4b38f85cbb1418fe1cfc638d316476c46fb853c7984f4030f195e5b3c0319`；旧1174仍为 `3e64b9d966a049e71af19d8ccdcc619e8e5d206bd89be8b9df8d45a3b2c57e93`。

中央Data的 `H3Motion20261019` 中保存run.json、resource-samples.json、review.json、motion-contact.png、browser-comparison.png、runner-lock-check.json、resume-check.json、validation-summary.json和workspace-check.json。对照页完整URL在review.json。

```powershell
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/minimax/run_motion.py
& C:/install/AI/ComfyUI/venv/Scripts/python.exe tools/minimax/review_motion.py
$env:H3_MOTION_REVIEW='C:\install\AI\Data\H3Motion20261019\review.json'
# 在web目录执行；只读取已完成媒体，不提交生成任务。
npx playwright test tests/h3-motion-compare.spec.js --workers=1
```

当前报告已完成，重复运行保留1176；不要删除报告绕过幂等保护。下一步等待用户观看动态自然度和声音，不自动增加新生成任务，无需API Key。
