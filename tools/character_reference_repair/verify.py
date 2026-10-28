"""Real output provenance, old-file protection, per-slot selection and deployed API tests."""
import json, sys, subprocess
from pathlib import Path
from PIL import Image
from run import Repair
from inventory import ROOT, DATA, OUT, read, write, sha, media
sys.path.insert(0,str(ROOT/'tools/character_story'))
from setup import mysql

def run():
 r=Repair();checks=[]
 def check(value,name):
    checks.append(dict(name=name,status='Passed' if value else 'Failed'))
    if not value:raise AssertionError(name)
 check(r.api('/api/character-workshop/prompt-policy')==__import__('character_prompt_policy').POLICY,'deployed API uses current shared policy')
 for old in r.before['characters']:
    for ref in old['references']:
        if ref['available']:check(sha(media(ref['assetPath']))==ref['actualSha256'],'original image bytes preserved ref'+str(ref['id']))
 check({v['id']:v['sha256'] for v in r.api('/api/character-library')['versions']}=={v['id']:v['sha256'] for v in r.before['versions']},'all immutable library versions preserved')
 for path,digest in read(OUT/'prompt-tests.json')['checkpoints'].items():check(sha(Path(path))==digest,'historical checkpoint preserved '+Path(path).parent.name)
 selected=read(OUT/'selected.json');check(len(selected)==63 and len({x['sha256'] for x in selected})==63,'63 distinct selected slot images')
 for row in selected:
    path=media(row['path']);check(sha(path)==row['sha256'],'selected file hash '+str(row['referenceId']))
    with Image.open(path) as im:
        im.load();check(im.size==(1536,864),'selected image full decode and native dimensions '+str(row['referenceId']))
    current=next(x for x in r.api('/api/characters/'+str(row['characterId'])+'/references') if x['id']==row['referenceId'])
    check(current['reviewStatus']!='Rejected','selected slot is not live-rejected '+str(row['referenceId']))
 for cid in range(19,26):
    state=r.api('/api/character-workshop/'+str(cid))
    check(len(state['prompts'])==9 and state['promptPolicy']=='character-anatomy-v2','all nine prompt previews for character '+str(cid))
    check(all('ONE anatomically normal head' in p['prompt'] for p in state['prompts']),'single head rule shared by character '+str(cid))
    write(OUT/'prompt-previews'/f'{cid}.json',dict(characterId=cid,policy=state['promptPolicy'],prompts=state['prompts']))
 for key,e in r.state['tasks'].items():
    check(e['status']=='Succeeded','actual Studio task success '+key)
    p=media(e['path']);check(sha(p)==e['sha256'],'output hash '+key)
    with Image.open(p) as im:
        check(im.size==(1536,864),'native resolution '+key)
        graph=json.loads(im.info['prompt'])
    check(graph['7']['inputs']['text']==e['body']['parameters']['positive'],'native PNG executed exact prompt '+key)
    check(graph['14']['inputs']['noise_seed']==e['body']['parameters']['seed'],'native PNG executed exact seed '+key)
    execution=json.loads(mysql('SELECT JSON_OBJECT(\'promptId\',comfy_prompt_id,\'durationMs\',duration_ms,\'vramPeakMiB\',vram_peak_mib) FROM generation_tasks WHERE id='+str(e['id'])+';'))
    check(bool(execution['promptId']),'real Comfy execution linked '+key)
    write(OUT/'receipts'/f'{key}-execution.json',execution)
    h=r.s.get('http://127.0.0.1:8188/history/'+execution['promptId'],timeout=30);h.raise_for_status();history=h.json()
    if execution['promptId'] in history:
        check(history[execution['promptId']]['status']['completed'],'actual Comfy completion '+key)
        write(OUT/'receipts'/f'{key}-history.json',history)
    else:check(bool(graph),'Comfy evicted history; native output provenance retained '+key)
    decode=subprocess.run(['C:/install/FFmpeg/bin/ffmpeg.exe','-v','error','-i',str(p),'-f','null','-'],capture_output=True,text=True)
    check(decode.returncode==0,'full PNG decode '+key)
    for path,digest in e['body']['parameters']['characterReferenceRepair']['inputSha256'].items():check(sha(media(path))==digest,'generation input preserved '+key+' '+Path(path).name)
    if e['visualStatus']=='Passed':
        check(bool(e.get('referenceId')),'visually inspected candidate registered '+key)
        refs=r.api('/api/characters/'+str(e['body']['parameters']['characterReferenceRepair']['characterId'])+'/references')
        ref=next(x for x in refs if x['id']==e['referenceId'])
        check(ref['reviewStatus']=='NeedReview' and ref['assetSha256']==e['sha256'],'new candidate awaits human review '+key)
        count_before=len(refs);r.collect(key);check(len(r.api('/api/characters/'+str(ref['characterId'])+'/references'))==count_before,'collect replay creates no duplicate '+key)
    else:check(not e.get('referenceId'),'failed visual candidate excluded '+key)
 check(max(s['running'] for s in r.state['resourceSamples'])<=1,'observed GPU concurrency at most one')
 check(not r.api('/api/minimax/local/status')['queue']['activeTasks'],'Studio queue idle')
 check(not r.s.get('http://127.0.0.1:8188/queue').json()['queue_running'],'Comfy queue idle')
 write(OUT/'verification.json',dict(status='Passed',checks=checks,count=len(checks),newGpuTasksDuringVerification=0,humanApprovals=0,publication='Blocked'))
 print('REFERENCE_REPAIR_VERIFICATION_PASSED',len(checks))
if __name__=='__main__':run()
