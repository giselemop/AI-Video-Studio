"""Re-check the two completed pilot clips. Never labels them as new story clips."""
import sys,json,subprocess,requests,importlib.util
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from setup import ROOT,DATA,OUT,sha,write
def run():
    spec=importlib.util.spec_from_file_location('delivery_helpers',ROOT/'tools/character_library/verify_delivery.py');helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
    traces=helpers.database_traces([1454,1455]);write(OUT/'existing-task-traces.json',traces);checks=[];rows=[];session=requests.Session()
    def check(name,passed):
        checks.append(dict(name=name,status='Passed' if passed else 'Failed'))
        if not passed:raise AssertionError(name)
    for trace in traces:
        taskId=trace['id'];detail=session.get('http://127.0.0.1:18080/api/tasks/'+str(taskId),timeout=30).json();check(str(taskId)+'-actual-task-succeeded',detail['task']['status']=='Succeeded')
        result=next(r for r in detail['results'] if r.get('available') and r.get('assetPath','').endswith('.mp4'));path=(DATA/result['assetPath']).resolve(strict=True);check(str(taskId)+'-controlled-media-path',path.is_relative_to(DATA.resolve()))
        source=trace['input']['parameters']['characterLibrary'];execution=trace['input']['minimaxLocalExecution']
        check(str(taskId)+'-actual-first-frame-hash',sha(DATA/source['referenceAssetPath'])==execution['firstFrame']['sha256']==source['referenceSha256'])
        probe=json.loads(subprocess.check_output(['C:/install/FFmpeg/bin/ffprobe.exe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'));write(OUT/(str(taskId)+'-existing-ffprobe.json'),probe);video=next(s for s in probe['streams'] if s['codec_type']=='video')
        check(str(taskId)+'-native-contract',video['width']==864 and video['height']==480 and video['avg_frame_rate']=='24/1' and int(video['nb_read_frames'])==124)
        check(str(taskId)+'-duration',abs(float(probe['format']['duration'])-124/24)<.15)
        decoded=subprocess.run(['C:/install/FFmpeg/bin/ffmpeg.exe','-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120);check(str(taskId)+'-full-decode',decoded.returncode==0 and not decoded.stderr)
        r=session.get('http://127.0.0.1:18080/api/media',params=dict(assetPath=result['assetPath']),headers={'Range':'bytes=0-1023'},timeout=30);check(str(taskId)+'-http-range',r.status_code==206 and len(r.content)==1024)
        live=session.get('http://127.0.0.1:8188/history/'+trace['comfyPromptId'],timeout=30).json();write(OUT/(str(taskId)+'-existing-comfy-live.json'),live)
        native=live.get(trace['comfyPromptId']);liveStatus='Passed' if native and native['status']['status_str']=='success' else 'Blocked'
        archive=DATA/'CharacterReferencePack20261026'/('linan-fullBody-video-comfy-history.json' if taskId==1454 else 'zhouyan-fullBody-video-comfy-history.json')
        archived=json.loads(archive.read_text(encoding='utf-8'))[trace['comfyPromptId']]
        check(str(taskId)+'-original-archived-comfy-receipt',archived['status']['status_str']=='success' and archived['status']['completed'])
        check(str(taskId)+'-archived-actual-prompt',archived['prompt'][2]['6']['inputs']['prompt']==trace['input']['parameters']['prompt'])
        if native:
            graph=native['prompt'][2];frame=Path(graph['5']['inputs']['image']);frame=frame if frame.is_absolute() else ROOT.parent/'ComfyUI/input'/frame
            # Input files may have been archived after completed execution; do not recreate them.
            if frame.exists():check(str(taskId)+'-actual-comfy-input-bytes',sha(frame)==source['referenceSha256'])
        old=json.loads((DATA/'CharacterReferencePack20261026/run.json').read_text(encoding='utf-8'));record=next(r for r in old['tasks'].values() if r['id']==taskId);check(str(taskId)+'-original-output-unchanged',record['sha256']==sha(path))
        rows.append(dict(taskId=taskId,assetPath=result['assetPath'],sha256=sha(path),sourceReferenceSha256=source['referenceSha256'],versionId=source['versionId'],comfyPromptId=trace['comfyPromptId'],liveComfyReceipt=liveStatus,originalComfyArchive=str(archive),archiveSha256=sha(archive),archivedReceipt='Passed',width=864,height=480,frames=124,fps=24,duration=float(probe['format']['duration']),contentReview='NeedReview',publication='Blocked',existingCompletedMaterial=True,newStoryPipelineEvidence=False))
    write(OUT/'existing-media-checks.json',dict(status='Passed',checks=checks,outputs=rows,gpuSubmitted=0,newStoryClips=0));print(str(len(checks))+' existing-media checks Passed; no regeneration, no claim of new story acceptance.')
if __name__=='__main__':run()
