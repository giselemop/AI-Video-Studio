"""Read-only image/video, database and native Comfy provenance acceptance."""
import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
from PIL import Image
from run import Run,PEOPLE,SLOTS,FOLDER,ROOT,read,write,sha,media

def verify(images_only=False):
    r=Run();r.access();r.preserve();checks=[];outputs=[]
    entries={}
    for person in PEOPLE:
        for view,framing in SLOTS:
            logical=person['key']+'-'+view+'-'+framing
            entries[logical]=dict(r.state['tasks'][r.selected_key(logical)],person=person['key'],view=view,framing=framing)
    if not images_only:
        for person in PEOPLE:
            key=person['key']+'-fullBody-video'
            entries[key]=dict(r.state['tasks'][key],person=person['key'],view='front',framing='fullBody')
    spec=importlib.util.spec_from_file_location('old_delivery_helpers',ROOT/'tools/character_library/verify_delivery.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    traces=helper.database_traces([entry['id'] for entry in entries.values()]);write(FOLDER/'task-input-traces.json',traces)
    by_id={trace['id']:trace for trace in traces}
    target=FOLDER/('image-verification.json' if images_only else 'media-verification.json')
    def check(name,passed):
        checks.append(dict(name=name,status='Passed' if passed else 'Failed'))
        write(target,dict(status='Passed' if all(c['status']=='Passed' for c in checks) else 'Failed',checks=checks,outputs=outputs))
        if not passed:raise AssertionError(name)
    def comfy_input(value):
        path=Path(value)
        if not path.is_absolute():path=ROOT.parent/'ComfyUI/input'/path
        path=path.resolve(strict=True)
        if not path.is_relative_to((ROOT.parent/'ComfyUI/input').resolve()):raise ValueError('Comfy input boundary violation')
        return path
    def native_outputs(value,extension):
        if isinstance(value,dict):
            if str(value.get('filename','')).lower().endswith(extension) and value.get('type','output')=='output':
                path=(ROOT.parent/'ComfyUI/output'/value.get('subfolder','')/value['filename']).resolve(strict=True)
                if not path.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()):raise ValueError('Comfy output boundary violation')
                yield path
            else:
                for child in value.values():yield from native_outputs(child,extension)
        elif isinstance(value,list):
            for child in value:yield from native_outputs(child,extension)
    for key,entry in entries.items():
        trace=by_id[entry['id']];is_video=entry['path'].endswith('.mp4');parameters=trace['input']['parameters']
        check(key+'_database_succeeded',trace['status']=='Succeeded' and bool(trace['comfyPromptId']))
        # A native process crash removed pre-crash in-memory /history. The PNGs
        # retain the actual executed graph; verify it against native output,
        # source hashes and the Succeeded business record. Never invent history.
        saved=FOLDER/(r.selected_key(key)+'-comfy-history.json')
        history=read(saved) if saved.exists() else r.session.get('http://127.0.0.1:8188/history/'+trace['comfyPromptId'],timeout=30).json()
        item=history.get(trace['comfyPromptId']);evidence='ComfyHistory'
        if item:
            write(FOLDER/(key+'-comfy-history.json'),history)
            check(key+'_actual_comfy_succeeded',item['status']['status_str']=='success' and item['status']['completed'])
            workflow=item['prompt'][2]
        else:
            if is_video:raise AssertionError('Video history must have been durably archived')
            with Image.open(media(entry['path'])) as image:workflow=json.loads(image.info['prompt'])
            write(FOLDER/(key+'-executed-png-prompt.json'),workflow);evidence='NativePngPromptAndDatabase'
            check(key+'_native_executed_graph_metadata',workflow['18']['inputs']['filename_prefix'].startswith('video_studio/task_'+str(entry['id'])+'_attempt_'))
        if is_video:
            binding=parameters['characterLibrary'];execution=trace['input']['minimaxLocalExecution']
            check(key+'_fullbody_version_binding',binding['schema']=='character-library-v2' and binding['framing']=='fullBody' and binding['view']=='front' and binding['versionId']==r.state['people'][entry['person']]['versionId'])
            check(key+'_copied_firstframe_hash',execution['firstFrame']['sha256']==binding['referenceSha256'] and execution['firstFrame']['assetPath']==binding['referenceAssetPath'] and sha(comfy_input(workflow['5']['inputs']['image']))==binding['referenceSha256'])
            check(key+'_actual_prompt_and_workflow',workflow['6']['inputs']['prompt']==parameters['prompt'] and execution['workflowSha256']==binding['workflowSha256'])
        else:
            person=r.state['people'][entry['person']]
            check(key+'_original_identity_input',sha(comfy_input(workflow['4']['inputs']['image']))==person['identitySha256'])
            check(key+'_actual_image_prompt',workflow['7']['inputs']['text']==parameters['positive'])
            if entry['framing']=='fullBody' and entry['view']!='front':
                master=r.state['tasks'][entry['person']+'-front-fullBody']
                check(key+'_same_fullbody_wardrobe_master',sha(comfy_input(workflow['20']['inputs']['image']))==master['sha256'] and workflow['23']['inputs']['conditioning']==['8',0] and workflow['11']['inputs']['positive']==['23',0])
        if item:native=list(native_outputs(item['outputs'],'.mp4' if is_video else '.png'))
        else:
            prefix=workflow['18']['inputs']['filename_prefix'];base=(ROOT.parent/'ComfyUI/output'/prefix).resolve()
            if not base.is_relative_to((ROOT.parent/'ComfyUI/output').resolve()):raise ValueError('Native PNG output boundary violation')
            native=list(base.parent.glob(base.name+'_*.png'))
        check(key+'_native_output_matches',any(sha(path)==entry['sha256'] for path in native))
        path=media(entry['path']);probe=json.loads(subprocess.check_output(['C:/install/FFmpeg/bin/ffprobe.exe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],text=True,encoding='utf-8'))
        write(FOLDER/(key+'-ffprobe.json'),probe);video=next(s for s in probe['streams'] if s['codec_type']=='video')
        check(key+'_native_resolution',(video['width'],video['height'])==((864,480) if is_video else (1536,864)))
        if is_video:
            check(key+'_framecount_fps_duration',int(video['nb_read_frames'])==124 and video['avg_frame_rate']=='24/1' and abs(float(probe['format']['duration'])-124/24)<.15)
        decoded=subprocess.run(['C:/install/FFmpeg/bin/ffmpeg.exe','-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120)
        check(key+'_full_decode',decoded.returncode==0 and not decoded.stderr)
        response=r.session.get(r.base+'/api/media',params=dict(assetPath=entry['path']),headers={'Range':'bytes=0-1023'},timeout=30)
        check(key+'_http_range',response.status_code==206 and len(response.content)==1024)
        check(key+'_artifact_hash',sha(path)==entry['sha256'])
        if not is_video and person.get('versionId'):
            version=next(v for v in r.api('/api/character-library')['versions'] if v['id']==person['versionId'])
            ref=next(ref for ref in version['payload']['references'] if ref['view']==entry['view'] and ref['framing']==entry['framing'])
            check(key+'_uploaded_library_copy',ref['sha256']==entry['sha256'] and sha(media(ref['assetPath']))==entry['sha256'])
        outputs.append(dict(name=key,taskId=entry['id'],assetPath=entry['path'],sha256=entry['sha256'],person=entry['person'],view=entry['view'],framing=entry['framing'],width=video['width'],height=video['height'],frames=int(video['nb_read_frames']),durationMs=trace['durationMs'],sampledVramPeakMiB=trace['vramPeakMiB'],kind='video' if is_video else 'image',executionEvidence=evidence,preCrashHistoryAvailable=bool(item)))
        if is_video:
            subprocess.run(['C:/install/FFmpeg/bin/ffmpeg.exe','-hide_banner','-loglevel','error','-y','-i',str(path),'-vf','select=eq(n\\,0)+eq(n\\,24)+eq(n\\,48)+eq(n\\,72)+eq(n\\,96)+eq(n\\,123),scale=432:240,tile=3x2','-frames:v','1',str(FOLDER/(key+'-contact.png'))],check=True,timeout=120)
        write(target,dict(status='Passed',checks=checks,outputs=outputs))
    old=read(ROOT.parent/'Data/CharacterLibrary20261026/run.json')
    check('original_task_artifacts_preserved',all(sha(media(record['path']))==record['sha256'] for record in old['tasks'].values() if record.get('sha256')))
    old_delivery=read(ROOT.parent/'Data/CharacterLibrary20261026/delivery.json')
    check('all_five_previous_videos_preserved',all(sha(media(record['assetPath']))==record['sha256'] for record in old_delivery['outputs']))
    write(target,dict(status='Passed',checks=checks,outputs=outputs))
    if not images_only:write(FOLDER/'delivery.json',dict(outputs=outputs,technical='Passed',contentReview='NeedReview',publication='Blocked',newModels=0,newCloudCalls=0,gpuConcurrency=1))
    print(str(len(checks))+' media/provenance checks Passed for '+str(len(outputs))+' selected outputs',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--images-only',action='store_true');verify(parser.parse_args().images_only)
