"""Close the verified pilot, preserving previous documentation bodies and source media."""
from pathlib import Path
import re
import subprocess
from pilot import ROOT,DATA,FOLDER,API,Run,read,write,sha,media,preserve

run=Run(API,FOLDER/'run.json');run.access();preserve(run)
for name in ['verification.json','preflight-verification.json','execution-summary.json','source-verification.json']:
    if read(FOLDER/name)['status']!='Passed':raise RuntimeError('Required evidence failed: '+name)
browser=read(FOLDER/'browser-playback.json')
for key in ['normal','halfSpeed','qhdAudio']:
    if not all(v['ended'] and v['duration']==2 and v['readyState']==4 for v in browser[key]['videos']):
        raise RuntimeError('Incomplete actual browser playback')
if not all(v['ended'] for v in read(FOLDER/'browser-final-playback.json')['videos']):raise RuntimeError('Latest page was not played')
if read(FOLDER/'browser-console-errors.json'):raise RuntimeError('Browser console errors remain')
controls=read(FOLDER/'browser-controls.json')
if any(any(abs(t-item['frame']/24)>1e-5 for t in item['actual']) for item in controls['seeks']):raise RuntimeError('Seek mismatch')
if not (FOLDER/'browser-final.png').is_file():raise RuntimeError('Final screenshot missing')
source=read(FOLDER/'source-verification.json')
if not all(source[k] for k in ['existingWorkflowContractsPreserved','pythonCompiled','htmlPublicDistEqual','jsonPublicDistEqual']):
    raise RuntimeError('Source/deployment verification incomplete')
summary=read(FOLDER/'execution-summary.json')
run.save('ReadyForUserPreview',technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',
         finalPath=run.state['outputs']['optimized'],finalSha256=sha(media(run.state['outputs']['optimized'])))
status=('2026-10-24：项目36两秒局部肤质与跨帧稳定小样已交付，最终任务1281实际2560×1440/24FPS/48帧/2秒。'
        '取原片5–52帧，完整保留“哟，约会回来了？”，原版/当前2K/优化版使用同一原声片段；'
        '技术Passed，肤质收益较轻、内容待用户复核，发布Blocked。原嘴部/眼睛/非皮肤区域在编码前逐像素保持；'
        '不宣称恢复真实毛孔。恢复Data/SkinPilot20261024/run.json为ReadyForUserPreview，仅核验、不重复提交。')
report=f'''# 两秒局部肤质与跨帧稳定小样

{status}

## 实际结果

- 预览：http://127.0.0.1:18080/skin-pilot-compare.html；支持三列同步播放、半速、逐帧、同帧脸部范围和单路原声。
- 原版两秒：`{run.state['outputs']['original']}`。
- 当前2K两秒：`{run.state['outputs']['qhd']}`。
- 优化两秒：`{run.state['outputs']['optimized']}`；SHA256 `{run.state['finalSha256']}`。
- 同一片段为原片0.208333–2.208333秒、48帧；原10秒/三镜头1263与2K1268及其状态文件哈希均保持。

## 本地处理与保护

使用现有ComfyUI、RealVisXL V5 FP16及CPU InsightFace 68点模型，无新权重下载、云推理、TTS或口型生成。
5个768×768局部关键帧由真实GPU队列执行，登记新实验工作流`realvisxl-skin-patch-768-v1`，绑定模型/工作流哈希与firstFrame/editMask槽位。
原帧图像与低降噪约束人物外观，不声称新增身份适配器。皮肤遮罩排除眼睛、眉毛、嘴唇、牙齿、鼻部中心与轮廓边缘。
初次0.24降噪/CFG3.5细节收益过轻，定向调整为0.32/CFG4.0，其他模型/种子/采样器保持，选择第二轮；只进行1轮GPU定向修复。

CPU队列SkinComposite只传播生成结果相对原帧的纹理残差，采用双向光流、遮挡置信度与相邻关键帧余弦融合；限制残差与低频色调变化。
不会用光流替换整个脸部RGB。48帧逐一断言所有保护区域和非皮肤区域在交付编码前与2K源帧一致。
三版各一次H.264 CRF12编码；有损交付不承诺编码后的每个像素比特相同。

原成片AAC实际为16kHz单声道；按其真实采样率截取3333起的32000样本，原声PCM在AAC编码前逐样本一致。
音频起点四舍五入误差-0.000020833秒，小于一个原采样点；语速、音高与内容保持。
同一份AAC编码后复制进三版，三版实际解码PCM相同，容器/视频/音频时长均核验为两秒。

## 真实验证与资源

- 实际GPU任务1269–1278全部Succeeded，ComfyUI prompt/history、原输出PNG与发布资产SHA逐一对应；GPU最大并发{summary['maximumGpuConcurrency']}。
- GPU任务合计{summary['gpuSeconds']:.3f}秒；CPU任务合计{summary['cpuSeconds']:.3f}秒，包含保留的失败/未选候选。
- 资源采样{summary['resourceSamples']}条，整卡采样显存峰值{summary['sampledDevicePeakMiB']}MiB，系统最低可用RAM{summary['minimumAvailableRamMiB']}MiB；不是进程精确峰值。
- 13项真实预检、无效POST422拒绝、零新增测试任务Passed；完整48帧解码、尺寸、时长、保护区、原声和源文件保持Passed。
- 浏览器真实正常/半速完整播放、三路单独原声、9个时点与前后逐帧通过；最新版页面再次完整播放，控制台错误0。
- .NET实际发布及Python编译、前端JS语法核验Passed；原有工作流契约对象不变，新增皮肤实验条目。
- 原主服务18080未替换；新后端在独立预览18081运行。它沿用既有本机访问边界，未扩展认证白名单。旧2K预览的独立进程在空闲后替换，二进制保留。

## 保留的失败与修复

- 1279任务Failed：固定裁剪ROI外尚有遮罩。修复为只处理遮罩与ROI交集，外部原像素保留，无GPU重生成。
- 1280队列任务Succeeded，但最终交付校验Failed：音频样本索引误按24kHz计算，实际原片16kHz，造成容器3秒。该候选未用于交付。
- 改为探测原片采样率并校验容器与每条流的时长，1281实际Succeeded、最终核验Passed；不改写旧任务状态。

## 观感限制与恢复

检查九组实际同帧脸部裁图与正常/半速页面播放，人物及原口眼动作保留；优化版的肤质变化很轻，生成平滑感仍在。
不能把技术通过、纹理传播或生成的微纹理等同于真实拍摄皮肤恢复，也不宣称显著电影感提升。
内容仍需用户观看复核；不继续自动增强到十秒、不自动发布。

证据根目录`Data/SkinPilot20261024`：run.json、verification.json、execution-summary.json、comfy-history/、
preflight-verification.json、browser-playback.json、browser-final-playback.json、browser-controls.json、
browser-final.png、final-visual-review.json、source-verification.json及三次CPU修复记录。
接续使用`tools/skin_pilot/pilot.py --stage check`只核验现有文件，不提交新任务。
'''
(ROOT/'docs/SKIN_PILOT_20261024.md').write_text(report,encoding='utf-8')
marker='skin-pilot-20261024'
documents=['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']
for name in documents:
    path=ROOT/name;old=path.read_text(encoding='utf-8-sig')
    clean=re.sub(r'<!-- '+marker+r':start -->[\s\S]*?<!-- '+marker+r':end -->\n\n?','',old)
    before=(FOLDER/'source-before'/name).read_text(encoding='utf-8-sig')
    if clean!=before:raise RuntimeError('Unrelated documentation body changed: '+name)
    link='SKIN_PILOT_20261024.md' if name.startswith('docs/') else 'docs/SKIN_PILOT_20261024.md'
    prefix=f'<!-- {marker}:start -->\n> {status} 见[本轮记录]({link})。\n<!-- {marker}:end -->\n\n'
    path.write_text(prefix+clean,encoding='utf-8')
write(FOLDER/'documentation-verification.json',dict(status='Passed',preservedBodies=documents,report='docs/SKIN_PILOT_20261024.md'))
(FOLDER/'resume-notes.md').write_text('COMPLETED: ReadyForUserPreview. Final task1281, project36. Do not repeat GPU/CPU tasks.\n'
    'Read run.json, verify preserved sources/final hashes and existing queue records. Original API18080 unchanged; independent preview18081.\n'
    'Skin changes are subtle. Content NeedReview; publication Blocked.\n',encoding='utf-8')
print('ReadyForUserPreview; technical Passed, content needs user review; eight documentation bodies preserved',flush=True)
