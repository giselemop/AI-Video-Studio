"""Synchronize Chinese authoritative notes and compatibility records after acceptance."""
from run import *
import shutil
s=read(FOLDER/'run.json')
if not s.get('completed') or s['stage']!='ReadyForUserPreview':raise RuntimeError('Finish actual acceptance first')
summary=read(FOLDER/'execution-summary.json');env=read(FOLDER/'final-environment-verification.json')
text=f'''# 画面定向修复小样执行与验收

项目{s['projectId']}，`ReadyForUserPreview`。用户授权针对眨眼闭合不完整、H3中段表情漂移和QHD丢失皮肤细节做纯本地小样，保留现有版本并交付前后对比。技术 **Passed**，内容 `NeedReview`，发布 **Blocked**。

新对比页：<http://127.0.0.1:18080/visual-targeted.html>。旧对比页与旧原片保留。三组可同步、半速、共同定位、逐帧与局部观看；对比为静音画面验收，不代表对白口型、真人表演或发布批准。

| 分支 | 本轮任务 | 实际输出 | 耗时 |
|---|---|---|---|
| H3分时段闭口 | 1322 | 原生864×480，24FPS，124帧，5.167秒 | 10分16.5秒 |
| 眼部残差修复 | 1323 | 原生1024×576，25FPS，50帧，2秒 | 20.6秒 |
| 眨眼展示帧率统一 | 1324 | 1280×720，24FPS，48帧，2秒 | 1.2秒 |
| 原有皮肤细节回补及同编码对照 | 1325 | 两版2560×1440，24FPS，48帧，2秒 | 1分43.9秒 |

耗时为业务任务执行时间。仅2个GPU任务且互不重叠；全部生成/合成经业务队列。没有下载新模型或调用云推理。

## 实际修复与画面结论

**眨眼**：保留同一关键帧、同一旧自有task1293驱动、完整头部/嘴部运动与1.0动作倍数。新增独立 `blink-residual-v1` 适配器，比较当前渲染与目标闭眼状态的学习式眼部残差，只在驱动眨眼区间、官方眼部关键点和局部眼部掩膜内使用。没有开启会替换整个相对运动基底的官方眼睛重定向开关。原表演V1脚本与官方源码逐项SHA保留，分支/强度/输入/回执及脚本漂移均做绑定。

原生50帧中的25帧实际施加眼部修正。检查统一24FPS的0、9、12、15、24、37帧，可见原先半闭的关键帧已经闭合，嘴部和头部保持一致。部分关键帧203点眼睑开合比从约0.33–0.35降至约0.026–0.054；这是实际渲染上的几何观察，不是美学、身份或自然度分数。闭眼节奏仍继承旧生成驱动，不是新真人表演。仅做1次修复，未盲目加大强度。解码256×256脸部裁片中，眼部掩膜外像素严格不变；后续贴回、重采样与有损编码另行记录，不能扩大成最终视频逐像素不变的承诺。

**H3中段**：与旧task1316保持模型、种子2026102407、首尾图、20步和规格完全相同，只改提示。前4秒保持中性闭口，最后1秒才微笑，删去并发眨眼要求以减少同时动作。检查0、12、24、36、48、61、72、84、92、104、116、123帧及实际正常/半速播放，中段明显更克制，抽查未出现上一版露齿大笑，收尾轻微微笑。全部124帧计算了嘴部几何观察；中段内唇开合比P95从约0.292降至0.181，但68点估计不是所有帧闭口/无牙或身份一致的语义证明。该样本更稳，同时动作更少，不据此宣称自然度普遍提高。仅做1次重生成。

**皮肤细节**：不增加扩散生成或随机颗粒。从逐帧完全对齐的精修前720p素材取已有亮度频段，与QHD对应频段求差，强度0.65、亮度增量限幅6级；只作用于有色彩支持的皮肤掩膜，排除眼睛、眉毛、嘴唇、牙齿与鼻部中心。两版均以相同CRF12编码，左侧为上一轮QHD的同编码对照，旧QHD原文件保留。48帧的眼口保护区和皮肤掩膜外在编码前逐像素不变。检查同帧局部及播放，收益较轻，保留了一些原有皮肤颗粒，不能称恢复真实毛孔或显著提升清晰度。源频带均方差诊断由约0.894降至0.247，仅证明更接近指定源频段，不作为主观质量评分。仅做1次合成。

## 测试、保全与运行环境

- 表演协议回归 **28项Passed**，包括原有超时/取消子进程、输入/输出SHA、尺寸、回执和新分支隔离；报告 `Data/acceptance/visual_acting_baa811f6b70c442f864a1dfb518ccc3c/report.json`。
- 细节请求边界 **7项Passed**；实际API **13个无效POST均422、零新增任务**，覆盖引擎/清单/输入SHA、越界路径、未知/非字符串分支、未登记强度与掩膜版本；两个真实有效预检及4个实际任务全部成功。
- 七份交付/对照视频完整解码、帧数/FPS/尺寸/时长与冻结SHA **Passed**；H3实际Comfy成功历史已归档，原始输出与发布文件SHA一致，未补造历史。
- 实际浏览器三组各正常/半速完整播放，共6次；共同定位、前后逐帧和2倍局部 **Passed**，页面错误日志0。原始AX、截图见 `browser-playback.json` 与 `browser-final.png`。
- .NET发布、Python编译、页面JS语法与Git空白检查 **Passed**。未提交或推送；原工作区脏修改保留。
- 冻结输入及旧版共{summary['priorVersionHashesVerified']}个文件SHA复核一致；模型目录{summary['modelDirectoryMetadataFilesUnchanged']}个基线文件的大小/mtime一致，没有重算所有旧权重的完整SHA，也未删除旧缓存或模型。新运行基线独立保存；上一轮已报告的历史缓存差异不被抹掉。
- 原18080服务保留；仅在H3任务结束并确认空闲后切换独立18081修复构建，旧构建仍在Data/Deploy。Comfy仅在空闲时通过 `/free` 释放内存中的模型，没有重启、换模型或清空历史。
- RTX4070 12GB，本轮采样显存最高{summary['sampledPeakDeviceVramMiB']}MiB，可用RAM最低{summary['sampledMinAvailableRamMiB']}MiB，磁盘剩余最低{summary['sampledMinFreeDiskGiB']}GiB；为系统/设备采样，不是单进程精确峰值或长片稳定性保证。
- 原队列已恢复此前的 `paused={env['originalQueuePaused']}`；实验队列暂停。数据库、Comfy、FFmpeg在线，生成队列空闲。

人脸检测权重仍按既有研究用途实验边界使用；内容/许可/人工发布门未绕过。画面自然度、人物一致性和使用偏好留给观看复核，小样通过不自动推广成批量默认流程。

## 恢复与证据

`C:/install/AI/Data/VisualTargeted20261024/run.json` 为恢复入口。完成状态下运行 `tools/visual_targeted/run.py --stage check` 只读核验；其他阶段也不得重复提交。新一轮修改使用独立版本。

证据：`execution-summary.json`、`media-verification.json`、`visual-review.json`、`h3-live-history.json`、`h3-source-verification.json`、`h3-aperture-observations.json`、`api-admission-checks.json`、`detail-protocol-checks.json`、各任务回执、资源采样、`source-manifest.json` 与 `final-environment-verification.json`。
'''
(ROOT/'docs/VISUAL_TARGETED_20261024.md').write_text(text,encoding='utf-8')
start='<!-- visual-targeted-20261024:start -->';end='<!-- visual-targeted-20261024:end -->'
entry=(start+'\n> 2026-10-24定向画面修复小样已交付，项目39，任务1322–1325：局部眨眼残差、同条件H3分时段闭口、源频段皮肤回补。技术与真实页面Passed；眨眼闭合及中段表情改善，皮肤收益较轻，内容NeedReview，发布Blocked。全本地、无新增模型，旧模型/版本/成片保全；原队列恢复。恢复Data/VisualTargeted20261024/run.json，只读不重生成。见[验收记录](docs/VISUAL_TARGETED_20261024.md)、[本机新对比](http://127.0.0.1:18080/visual-targeted.html)。\n'+end+'\n\n')
for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
    p=ROOT/name;backup=FOLDER/'backups/docs'/name;backup.parent.mkdir(parents=True,exist_ok=True)
    if not backup.exists():shutil.copy2(p,backup)
    old=p.read_text(encoding='utf-8-sig')
    if start in old:
        a=old.index(start);b=old.index(end,a)+len(end);old=old[:a]+old[b:].lstrip('\r\n')
    prefix=entry.replace('(docs/VISUAL_TARGETED_20261024.md)','(VISUAL_TARGETED_20261024.md)') if name.startswith('docs/') else entry
    p.write_text(prefix+old,encoding='utf-8')
print('Final Chinese/compatibility records updated; previous notes preserved')
