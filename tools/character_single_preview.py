"""One explicitly scoped library experiment using approved legacy reference36.

The nine-image story run remains on its user-requested review hold. This tool
does not adopt a repaired candidate, approve a version, or change historical cast.
"""
from pathlib import Path
import argparse,datetime,json,msvcrt,re,subprocess,sys,uuid
import requests
sys.path.insert(0,str(Path(__file__).parent/'character_scene'))
from common import ROOT,DATA,write,sha,mysql
OUT=DATA/'CharacterSinglePreview20261027'
FFMPEG=ROOT.parent.parent/'FFmpeg/bin/ffmpeg.exe'
FFPROBE=ROOT.parent.parent/'FFmpeg/bin/ffprobe.exe'
PROMPT=('A single continuous close-up of the same woman by this same window. '
        'Maintain her exact face, age, shoulder-length black hair and cream knitted sweater. '
        'She calmly blinks once, then makes one very small natural head turn of only a few degrees '
        'toward picture LEFT and softly returns her gaze toward the camera. '
        'Gentle breathing, restrained expression, lips stay closed throughout, no speaking. '
        'Locked camera, unchanged framing and background, no cut or zoom, no extra person or limb. '
        'Quiet room ambience only, no voices or music.')

class Preview:
 def __init__(self):
    OUT.mkdir(parents=True,exist_ok=True);self.path=OUT/'run.json';self.base='http://127.0.0.1:18080';self.s=requests.Session()
    self.state=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(runId=str(uuid.uuid4()),stage='Created',completed=False,mode='Character-Library-Experiment',contentReview='NeedReview',publication='Blocked',maxBaseVideos=1,maxRepairs=2,newModels=0,newCloudCalls=0,audioStrategy='NativeH3; visual preview muted by default, audio content not approved')
    auth=self.api('/api/auth/status');assert auth['accessMode']=='LocalOnly' and not auth['loginRequired'];self.s.headers['X-CSRF-Token']=auth['csrfToken']
 def save(self):write(self.path,self.state)
 def api(self,path,body=None):
    r=self.s.request('POST' if body is not None else 'GET',self.base+path,json=body,timeout=180)
    if not r.ok:raise RuntimeError(path+' HTTP'+str(r.status_code)+' '+r.text[:1000])
    return r.json()
 def prepare(self):
    if self.state.get('request'):return
    health=self.api('/api/health');runtime=self.api('/api/minimax/local/status');queue=requests.get('http://127.0.0.1:8188/queue',timeout=30).json()
    assert health['database']['online'] and health['comfy']['online'] and health['ffmpeg']['available']
    assert health['comfy']['gpu']['freeMiB']>=1024 and runtime['queue']['gpuConcurrency']==1 and not runtime['queue']['activeTasks'] and not runtime['queue']['paused']
    assert not queue['queue_running'] and not queue['queue_pending'] and mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Pending','Running');")=='0'
    version=next(v for v in self.api('/api/character-library')['versions'] if v['id']==3);ref=next(r for r in version['payload']['references'] if r['referenceId']==36 and r['view']=='front')
    current=next(r for r in self.api('/api/characters/19/references') if r['id']==36)
    assert current['available'] and current['reviewStatus']=='Approved' and current['assetSha256']==ref['sha256']==sha(DATA/ref['assetPath'])
    assert version['payload']['workflow']['profile']=='baseline480' and sha(ROOT.parent/'Workflows'/version['payload']['workflow']['fileName'])==version['payload']['workflow']['sha256']
    scene=DATA/'CharacterScene20261027/run.json';sceneState=json.loads(scene.read_text(encoding='utf-8'));assert sceneState['generationHold']['active']
    self.state.update(versionId=3,sourceReference=ref,currentSourceReview=current,versionSnapshot=version,sourceInspection=dict(scope='PreviewInspection',note='Actual1536x864 portrait viewed before submission: one woman, black shoulder-length hair, cream knit sweater, coherent face and neck, no collage; slight initial head tilt retained. Human source reference36 is already Approved; final video remains NeedReview.'),heldSceneCheckpoint=str(scene),heldSceneCheckpointSha256=sha(scene),heldSceneGenerationHold=sceneState['generationHold'],initialTaskCount=int(mysql('SELECT COUNT(*) FROM generation_tasks;')),healthBefore=health,queueBefore=runtime['queue'],startedAt=datetime.datetime.now().astimezone().isoformat());self.save()
    name='林安单人动作实验_'+self.state['runId'][:8]
    existing=next((p for p in self.api('/api/projects') if p['name']==name),None)
    self.state['projectId']=existing['id'] if existing else self.api('/api/projects',dict(name=name,description='One new five-second visual experiment from explicitly chosen legacy library version3 and approved reference36. Modern nine-image versions and fixed-room story remain on review hold.',defaultWidth=864,defaultHeight=480,defaultFps=24))['id']
    self.state['request']=dict(projectId=self.state['projectId'],versionId=3,view='front',prompt=PROMPT,seed=2026102718,idempotencyKey='single-preview:'+self.state['runId']+':base')
    self.state['stage']='Prepared';self.save()
 def submit(self):
    if self.state.get('taskId'):print('Existing task retained: '+str(self.state['taskId'])+'; no new submission.');return
    if self.state['completed']:raise RuntimeError('Completed run is read-only')
    self.prepare();resolved=self.api('/api/character-library/resolve',self.state['request']);write(OUT/'resolved.json',resolved)
    assert resolved['binding']['versionId']==3 and resolved['binding']['referenceId']==36 and resolved['binding']['mode']=='Experimental'
    preflight=self.api('/api/tasks/preflight',resolved['task']);write(OUT/'preflight.json',preflight);assert preflight['passed'],preflight
    self.state['stage']='SubmissionPrepared';self.save()
    result=self.api('/api/character-library/generate',self.state['request']);write(OUT/'submission.json',result)
    self.state.update(taskId=result['id'],stage='VideoQueued');self.save();print('One real library experiment queued: task '+str(result['id'])+' / project '+str(self.state['projectId'])+' / version3 / approved reference36.')
 def tick(self):
    detail=self.api('/api/tasks/'+str(self.state['taskId']));write(OUT/'task.json',detail);self.state['taskStatus']=detail['task']['status']
    raw=mysql("SELECT JSON_OBJECT('id',id,'status',status,'input',input_json,'comfyPromptId',comfy_prompt_id,'durationMs',duration_ms,'vramPeakMiB',vram_peak_mib) FROM generation_tasks WHERE id="+str(self.state['taskId'])+';')
    trace=json.loads(raw);write(OUT/'task-trace.json',trace)
    if trace.get('comfyPromptId'):
        h=requests.get('http://127.0.0.1:8188/history/'+trace['comfyPromptId'],timeout=30).json()
        if h:write(OUT/'comfy-history.json',h)
    if detail['task']['status']=='Succeeded':
        asset=next(r for r in detail['results'] if r.get('available') and r.get('assetPath','').endswith('.mp4'));self.state.update(stage='VideoReady',assetPath=asset['assetPath'],sha256=sha(DATA/asset['assetPath']))
    elif detail['task']['status'] in ['Failed','Cancelled']:self.state.update(stage='Failed',failure=detail['task'].get('errorMessage'))
    else:self.state['stage']=detail['task']['status']
    self.save();print(json.dumps(dict(taskId=self.state['taskId'],status=self.state['taskStatus'],progress=detail['task'].get('progress'),comfyPromptId=trace.get('comfyPromptId'),failure=self.state.get('failure')),ensure_ascii=False))
 def verify(self):
    assert self.state.get('taskStatus')=='Succeeded';checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:raise AssertionError(name)
    trace=json.loads((OUT/'task-trace.json').read_text(encoding='utf-8'));binding=trace['input']['parameters']['characterLibrary'];execution=trace['input']['minimaxLocalExecution'];native=json.loads((OUT/'comfy-history.json').read_text(encoding='utf-8'))[trace['comfyPromptId']];graph=native['prompt'][2]
    check('real Comfy execution success',native['status']['completed'] and native['status']['status_str']=='success')
    check('explicit legacy version3 reference36 experiment',binding['versionId']==3 and binding['referenceId']==36 and binding['mode']=='Experimental' and binding['versionSha256']==self.state['versionSnapshot']['sha256'])
    first=Path(graph['5']['inputs']['image']);first=first if first.is_absolute() else ROOT.parent/'ComfyUI/input'/first
    check('actual H3 first frame equals approved library source',sha(first)==binding['referenceSha256']==execution['firstFrame']['sha256']==self.state['sourceReference']['sha256'])
    check('frozen workflow retained',execution['workflowSha256']==binding['workflowSha256']==self.state['versionSnapshot']['payload']['workflow']['sha256'])
    check('actual generation settings match validated shortest contract',graph['6']['inputs']['width']==864 and graph['6']['inputs']['height']==480 and graph['6']['inputs']['length']==124 and graph['14']['inputs']['fps']==24 and graph['10']['inputs']['steps']==20)
    check('actual action prompt and seed retained',graph['6']['inputs']['prompt']==trace['input']['parameters']['prompt'] and graph['7']['inputs']['noise_seed']==self.state['request']['seed'])
    path=DATA/self.state['assetPath'];probe=json.loads(subprocess.check_output([str(FFPROBE),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'));write(OUT/'ffprobe.json',probe);video=next(s for s in probe['streams'] if s['codec_type']=='video')
    check('real864x480 24fps124frames',video['width']==864 and video['height']==480 and video['avg_frame_rate']=='24/1' and int(video['nb_read_frames'])==124)
    check('valid contract duration',abs(float(probe['format']['duration'])-124/24)<.15)
    decoded=subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120);check('full audio and video decode',decoded.returncode==0 and not decoded.stderr)
    check('output hash unchanged',sha(path)==self.state['sha256'])
    def native_files(value):
        if isinstance(value,dict):
            if str(value.get('filename','')).endswith('.mp4') and value.get('type','output')=='output':
                file=(ROOT.parent/'ComfyUI/output'/value.get('subfolder','')/value['filename']).resolve(strict=True)
                if not file.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()):raise RuntimeError('Native output boundary mismatch')
                yield file
            else:
                for child in value.values():yield from native_files(child)
        elif isinstance(value,list):
            for child in value:yield from native_files(child)
    check('published file equals actual native Comfy output',any(sha(f)==self.state['sha256'] for f in native_files(native['outputs'])))
    response=self.s.get(self.base+'/api/media',params=dict(assetPath=self.state['assetPath']),headers={'Range':'bytes=0-1023'},timeout=30);check('browser media Range206',response.status_code==206 and len(response.content)==1024)
    check('original scene checkpoint and review hold unchanged',sha(Path(self.state['heldSceneCheckpoint']))==self.state['heldSceneCheckpointSha256'])
    check('only one new task in this experiment project',mysql('SELECT COUNT(*) FROM generation_tasks WHERE project_id='+str(self.state['projectId'])+';')=='1')
    write(OUT/'media-checks.json',dict(status='Passed',checks=checks,taskId=self.state['taskId'],sha256=self.state['sha256'],duration=probe['format']['duration'],nativeAudioPresent=any(s['codec_type']=='audio' for s in probe['streams']),contentReview='NeedReview',publication='Blocked'))
    frames=OUT/'frames';frames.mkdir(exist_ok=True)
    if not (frames/'frame-12.png').exists():
        indices=[round(i*123/11) for i in range(12)];expression='+'.join('eq(n,'+str(n)+')' for n in indices)
        subprocess.run([str(FFMPEG),'-v','error','-i',str(path),'-vf','select='+expression.replace(',','\\,'),'-fps_mode','passthrough',str(frames/'frame-%02d.png')],check=True,timeout=120)
    from PIL import Image,ImageDraw
    sheet=Image.new('RGB',(1728,798),'#101827');draw=ImageDraw.Draw(sheet)
    for i in range(12):
        with Image.open(frames/f'frame-{i+1:02d}.png') as frame:sheet.paste(frame.resize((432,240)),((i%4)*432,(i//4)*266))
        draw.text(((i%4)*432+8,(i//4)*266+244),f'Task {self.state["taskId"]} | {round(i*123/11)/24:.3f}s',fill='white')
    sheet.save(OUT/'contact-sheet.jpg',quality=95)
    print(str(len(checks))+' real video/provenance checks Passed. Final content remains NeedReview.')
 def page(self):
    assert self.state.get('taskId');inspectionPath=OUT/'visual-inspection.json';inspection=json.loads(inspectionPath.read_text(encoding='utf-8')) if inspectionPath.exists() else None
    payload=json.dumps(dict(taskId=self.state['taskId'],projectId=self.state['projectId'],versionId=3,source=self.state['sourceReference'],mode='Character-Library-Experiment',sourceApproved=True,contentReview='NeedReview',publication='Blocked',inspection=inspection),ensure_ascii=False).replace('<','\\u003c')
    template=(ROOT/'tools/character_single_preview.template.html').read_text(encoding='utf-8');text=template.replace('__PAYLOAD__',payload)
    for folder in [ROOT/'web/public',ROOT/'web/dist']:(folder/'character-single-preview.html').write_text(text,encoding='utf-8')
    write(OUT/'preview-page.json',dict(url='http://127.0.0.1:18080/character-single-preview.html',sha256=sha(ROOT/'web/public/character-single-preview.html'),actualTaskId=self.state['taskId']))
    print('One-video review page published locally, backed by actual task '+str(self.state['taskId'])+'.')
 def finalize(self):
    evidence={n:json.loads((OUT/n).read_text(encoding='utf-8')) for n in ['media-checks.json','browser-playback.json','visual-inspection.json','story-hold-preserved.json']}
    assert all(evidence[n]['status']=='Passed' for n in ['media-checks.json','browser-playback.json','story-hold-preserved.json']) and evidence['browser-playback.json']['ended']
    assert evidence['visual-inspection.json']['status'] in ['Passed','Failed']
    assert not evidence['browser-playback.json'].get('consoleErrors') and sha(DATA/self.state['assetPath'])==self.state['sha256']
    assert sha(Path(self.state['heldSceneCheckpoint']))==self.state['heldSceneCheckpointSha256']
    probe=json.loads((OUT/'ffprobe.json').read_text(encoding='utf-8'));trace=json.loads((OUT/'task-trace.json').read_text(encoding='utf-8'))
    report=f'''# 林安单人动作试片（2026-10-27）

应用户“现在可以生成一段视频看看效果了吗”的新请求，完成一个独立人物参考图动画实验。本次明确选用旧版已批准参考36，不恢复原双人剧情、不采用待审修复候选、不撤销原拒绝记录。

- [本次新视频与来源](http://127.0.0.1:18080/character-single-preview.html)
- 项目{self.state['projectId']}，真实业务任务{self.state['taskId']}；Comfy执行 `{trace['comfyPromptId']}`。
- 人物19林安，库版本3（v2、历史二图包），正面参考36当前审核Approved。库版本与最终视频仍NeedReview，发布Blocked。
- 实际H3首帧SHA256：`{self.state['sourceReference']['sha256']}`。
- 最终媒体：`{self.state['assetPath']}`；SHA256：`{self.state['sha256']}`。
- 原生864×480、24FPS、124帧、20步，实测时长{probe['format']['duration']}秒；本次生成耗时{trace['durationMs']/1000:.3f}秒，服务采样显存峰值{trace['vramPeakMiB']}MiB。无升分辨率、换模型或缩减契约。

## 检查结论

技术Passed：{len(evidence['media-checks.json']['checks'])}项实际媒体与来源检查，包括任务/Comfy历史、执行参数、实际首帧与源参考一致、输出等于原生Comfy文件、FFprobe、全片解码、哈希、Range206、单任务边界和原剧情检查点保全。浏览器已完整播放至结束，无媒体或控制台错误。

试片画面检查 **{evidence['visual-inspection.json']['status']}**：{evidence['visual-inspection.json']['note']}

本次为助手PreviewInspection，人工内容保持NeedReview；不生成身份分数，不代表正式人物包或双人剧情验收通过。音频策略为H3原生音频，预览页默认静音；原生音频内容未验收。

## 文件、原流程与恢复

证据：`C:\\install\\AI\\Data\\CharacterSinglePreview20261027`。主要文件：run.json、resolved.json、preflight.json、submission.json、task-trace.json、comfy-history.json、ffprobe.json、media-checks.json、contact-sheet.jpg、frames、visual-inspection.json、browser-playback.json与截图。

原`CharacterScene20261027/run.json`及generationHold保持逐字节不变；原正式剧情resolve仍以422拒绝失效来源。新九图人物与双人剧情继续待审。本轮只有一个新视频任务，没有重生图片、创建新人物版本或审核批准，没有下载模型、云调用或公开发布。

控制器：`tools/character_single_preview.py`；模板：`tools/character_single_preview.template.html`。运行submit会保留已登记任务{self.state['taskId']}，不会重复提交；完成后只核验当前输出。分支main/d6ec38d，未提交，既有未完成工作保留，无数据库结构迁移。
'''
    reportPath=ROOT/'docs/CHARACTER_SINGLE_PREVIEW_20261027.md';reportPath.write_text(report,encoding='utf-8')
    marker='character-single-preview-20261027'
    brief=f'> 2026-10-27：用户新请求的独立单人动作试片已交付，项目{self.state["projectId"]}/任务{self.state["taskId"]}，林安旧版#3、已批准正面参考36；864×480/24FPS/124帧，技术Passed，助手动作检查{evidence["visual-inspection.json"]["status"]}（实际眨眼和头部回正，定向左转未明显命中），人工内容NeedReview、发布Blocked。仅一个新视频，无新图/新版本/模型/云调用；原双人剧情检查点与保持待审指示不变。恢复Data/CharacterSinglePreview20261027/run.json，completed=true禁止重复生成。'
    for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
        p=ROOT/name;old=p.read_text(encoding='utf-8-sig');link='CHARACTER_SINGLE_PREVIEW_20261027.md' if name.startswith('docs/') else 'docs/CHARACTER_SINGLE_PREVIEW_20261027.md'
        block='<!-- '+marker+':start -->\n'+brief+f' [验收报告]({link})、[本次视频](http://127.0.0.1:18080/character-single-preview.html)。\n<!-- '+marker+':end -->'
        pattern='<!-- '+marker+':start -->[\\s\\S]*?<!-- '+marker+':end -->';updated=re.sub(pattern,lambda _:block,old) if re.search(pattern,old) else block+'\n\n'+old
        if p.read_text(encoding='utf-8-sig')!=old:raise RuntimeError('Concurrent documentation write; retry without regenerating: '+name)
        p.write_text(updated,encoding='utf-8')
    self.state.update(stage='ReadyForUserPreview',completed=True,technical='Passed',previewInspection=evidence['visual-inspection.json']['status'],contentReview='NeedReview',publication='Blocked',finishedAt=datetime.datetime.now().astimezone().isoformat());self.save()
    write(OUT/'delivery.json',dict(status='Passed',scope='Technical delivery, not action or human content approval',previewInspection=evidence['visual-inspection.json']['status'],taskId=self.state['taskId'],projectId=self.state['projectId'],videoPath=str(DATA/self.state['assetPath']),sha256=self.state['sha256'],report=str(reportPath),mediaChecks=len(evidence['media-checks.json']['checks']),contentReview='NeedReview',publication='Blocked',sceneReviewHoldUnchanged=True,newModels=0,newCloudCalls=0))
    print('Single experimental clip and documentation delivered. Formal story hold and all earlier versions retained.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['submit','tick','verify','page','finalize']);a=parser.parse_args();OUT.mkdir(exist_ok=True)
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);p=Preview();getattr(p,a.command)()
if __name__=='__main__':main()
