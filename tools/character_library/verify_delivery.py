"""Read-only media and provenance verification for the two-character pilot."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).parent))
from run_acceptance import Run, ROOT, DATA, FOLDER, read, write, media, sha

def database_traces(ids):
    values={}
    for raw in (ROOT/'config/local.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in raw and not raw.lstrip().startswith('#'):
            key,value=raw.split('=',1);values[key.strip()]=value.strip().strip('"').strip("'")
    env=dict(os.environ,MYSQL_PWD=values['AI_VIDEO_STUDIO_DB_PASSWORD'])
    query="SELECT JSON_OBJECT('id',id,'status',status,'input',input_json,'comfyPromptId',comfy_prompt_id,'durationMs',duration_ms,'vramPeakMiB',vram_peak_mib) FROM generation_tasks WHERE id IN ("+','.join(str(int(i)) for i in ids)+") ORDER BY id;"
    command=['C:/install/mysql8.0.22/bin/mysql.exe','--protocol=TCP','--default-character-set=utf8mb4','-h',values.get('AI_VIDEO_STUDIO_DB_HOST','127.0.0.1'),'-P',values.get('AI_VIDEO_STUDIO_DB_PORT','3306'),'-u',values['AI_VIDEO_STUDIO_DB_USER'],'-N','-B','--raw',values['AI_VIDEO_STUDIO_DB_NAME'],'-e',query]
    result=subprocess.run(command,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

def verify():
    r=Run('http://127.0.0.1:18080');r.access();r.preserve()
    entries={key:record for key,record in r.state['tasks'].items() if '-video-' in key}
    ui=read(FOLDER/'browser-ui-checks.json')
    ui_id=ui['submittedTaskId']
    ui_detail=r.api('/api/tasks/'+str(ui_id))
    if ui_detail['task']['status']!='Succeeded':raise RuntimeError('Browser-submitted task is not Succeeded yet')
    result=next(i for i in ui_detail['results'] if i.get('available') and i.get('assetPath','').endswith('.mp4'))
    entries['browser-linan-v2']=dict(id=ui_id,path=result['assetPath'],sha256=sha(media(result['assetPath'])))
    if len(entries)!=5 or r.state['stage'] not in ['VideosReady','ReadyForUserPreview']:raise RuntimeError('Four scripted views and one real browser call are required')
    traces=database_traces([e['id'] for e in entries.values()]);write(FOLDER/'task-input-traces.json',traces)
    by_id={t['id']:t for t in traces};checks=[];outputs=[]
    def check(name,passed):
        checks.append(dict(name=name,status='Passed' if passed else 'Failed'))
        write(FOLDER/'media-verification.json',dict(checks=checks,outputs=outputs,status='Passed' if all(c['status']=='Passed' for c in checks) else 'Failed'))
        if not passed:raise AssertionError(name)
    for key,entry in entries.items():
        task_id=entry['id'];trace=by_id[task_id];binding=trace['input']['parameters']['characterLibrary'];execution=trace['input']['minimaxLocalExecution']
        check(key+'-source-binding',execution['firstFrame']['sha256']==binding['referenceSha256'] and execution['firstFrame']['assetPath']==binding['referenceAssetPath'])
        check(key+'-workflow-binding',execution['workflowSha256']==binding['workflowSha256'])
        history=r.session.get('http://127.0.0.1:8188/history/'+trace['comfyPromptId'],timeout=30).json()
        write(FOLDER/(key+'-comfy-history.json'),history)
        item=history.get(trace['comfyPromptId'])
        check(key+'-comfy-succeeded',bool(item and item['status']['status_str']=='success' and item['status']['completed']))
        workflow=item['prompt'][2]
        first_path=Path(workflow['5']['inputs']['image'])
        if not first_path.is_absolute():first_path=ROOT.parent/'ComfyUI/input'/first_path
        first_path=first_path.resolve(strict=True)
        check(key+'-actual-comfy-first-frame',first_path.is_relative_to((ROOT.parent/'ComfyUI/input').resolve()) and sha(first_path)==binding['referenceSha256'])
        check(key+'-actual-comfy-identity-prompt',workflow['6']['inputs']['prompt']==trace['input']['parameters']['prompt'])
        def native_outputs(value):
            if isinstance(value,dict):
                if str(value.get('filename','')).lower().endswith('.mp4') and value.get('type','output')=='output':
                    candidate=(ROOT.parent/'ComfyUI/output'/value.get('subfolder','')/value['filename']).resolve(strict=True)
                    if not candidate.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()):raise ValueError('Comfy output boundary violation')
                    yield candidate
                else:
                    for child in value.values():yield from native_outputs(child)
            elif isinstance(value,list):
                for child in value:yield from native_outputs(child)
        native=list(native_outputs(item['outputs']))
        check(key+'-matches-fresh-comfy-output',any(sha(candidate)==entry['sha256'] for candidate in native))
        path=media(entry['path'])
        probe=json.loads(subprocess.check_output(['C:/install/FFmpeg/bin/ffprobe.exe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],text=True,encoding='utf-8'))
        write(FOLDER/(key+'-ffprobe.json'),probe)
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        check(key+'-native-dimensions',video['width']==864 and video['height']==480)
        check(key+'-frames-fps-duration',int(video['nb_read_frames'])==124 and video['avg_frame_rate']=='24/1' and abs(float(probe['format']['duration'])-124/24)<.15)
        decoded=subprocess.run(['C:/install/FFmpeg/bin/ffmpeg.exe','-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120)
        check(key+'-full-decode',decoded.returncode==0 and not decoded.stderr)
        response=r.session.get(r.base+'/api/media',params=dict(assetPath=entry['path']),headers={'Range':'bytes=0-1023'},timeout=30)
        check(key+'-http-range',response.status_code==206 and len(response.content)==1024)
        check(key+'-output-hash',sha(path)==entry['sha256'])
        outputs.append(dict(name=key,taskId=task_id,assetPath=entry['path'],sha256=entry['sha256'],versionId=binding['versionId'],characterId=binding['characterId'],view=binding['view'],width=video['width'],height=video['height'],frames=124,fps=24,duration=float(probe['format']['duration']),durationMs=trace['durationMs'],sampledVramPeakMiB=trace['vramPeakMiB']))
        write(FOLDER/'media-verification.json',dict(checks=checks,outputs=outputs,status='Passed'))
        # Contact sheet extraction is for inspection; it is not a new generated asset.
        sheet=FOLDER/(key+'-contact.png')
        subprocess.run(['C:/install/FFmpeg/bin/ffmpeg.exe','-hide_banner','-loglevel','error','-y','-i',str(path),'-vf','select=eq(n\\,0)+eq(n\\,24)+eq(n\\,48)+eq(n\\,72)+eq(n\\,96)+eq(n\\,123),scale=432:240,tile=3x2','-frames:v','1',str(sheet)],check=True,timeout=120)
    write(FOLDER/'delivery.json',dict(outputs=outputs,technical='Passed',contentReview='NeedReview',publication='Blocked',newModels=0,newCloudCalls=0))
    print(f'{len(checks)} media and provenance checks Passed for {len(outputs)} fresh videos',flush=True)

if __name__=='__main__':verify()
