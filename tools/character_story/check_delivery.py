"""Read-only completion checks against registered real tasks and protected assets."""
import sys,json,requests,subprocess,datetime,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from setup import ROOT,DATA,OUT,sha,mysql,write

def run():
    base='http://127.0.0.1:18080'
    def get(path):r=requests.get(base+path,timeout=60);r.raise_for_status();return r.json()
    health=get('/api/health');runtime=get('/api/minimax/local/status');ready=get('/api/character-story/readiness');queue=requests.get('http://127.0.0.1:8188/queue',timeout=30).json()
    assert health['database']['online'] and health['comfy']['online'] and health['ffmpeg']['available'] and ready['ready']
    assert runtime['queue']['gpuConcurrency']==1 and runtime['queue']['activeTasks']==0 and not runtime['queue']['paused'] and not queue['queue_running'] and not queue['queue_pending']
    assert mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Running','Pending');")=='0'
    current=get('/api/character-library')['versions'];original=json.loads((DATA/'CharacterExpansionFive20261026/run.json').read_text(encoding='utf-8'))
    assert {v['id']:v['sha256'] for v in current}=={v['id']:v['sha256'] for v in original['originalVersions']}
    for f in original['protectedFiles']:assert sha(DATA/f['assetPath'])==f['sha256']
    adopted=json.loads((OUT/'adopted-candidates.json').read_text(encoding='utf-8'));assert sha(DATA/'CharacterExpansionFive20261026/run.json')==adopted['originalCheckpointSha256']
    drafts=get('/api/character-workshop');assert sorted((r['characterId'],r['present']) for r in drafts)==[(21,7),(22,8),(23,8),(24,9),(25,8)]
    assert all(r['reviewStatus']=='NeedReview' and r['versionStatus']=='Draft' for r in drafts)
    pilot=json.loads((OUT/'pilot.json').read_text(encoding='utf-8'));registered=[];baseVideos=[]
    for slot,item in pilot['slots'].items():
        assert item['Keyframe']['inspection']['payload']['decision']=='Passed' and item['Video']['inspection']['payload']['decision']=='Passed'
        for kind in ['Keyframe','Video']:
            history=item.get(kind+'History',[]);assert len(history)<=2
            for task in history+[item[kind]]:
                registered.append(task['id'])
                if kind=='Video' and not task['body'].get('repairOfTaskId'):baseVideos.append(task['id'])
    assert len(baseVideos)==4
    preview=pilot['preview'];assert get('/api/tasks/'+str(preview['id']))['task']['status']=='Succeeded'
    controls=json.loads((OUT/'queue-controls.json').read_text(encoding='utf-8'));assert controls['status']=='Passed'
    allowed=sorted(registered+[preview['id'],controls['taskId']])
    actual=[int(line) for line in mysql("SELECT id FROM generation_tasks WHERE JSON_CONTAINS_PATH(input_json,'one','$.parameters.storyPipeline','$.parameters.characterWorkbench','$.parameters.storyPreview') ORDER BY id;").splitlines()]
    assert actual==allowed,(actual,allowed)
    assert int(mysql('SELECT COUNT(*) FROM generation_tasks;'))==1500+len(allowed)
    for name in ['backend-self-test.json','workflow-contract-checks.json','reference-policy-checks.json','api-checks.json','integration-checks.json','pilot-media-checks.json','preview-media-checks.json','restart-recovery.json','browser-runtime-checks.json']:
        result=json.loads((OUT/name).read_text(encoding='utf-8-sig'));assert result['status']=='Passed',name
    assert 'CHARACTER_LIBRARY_SELF_TEST_PASSED 16' in (OUT/'legacy-library-tests.txt').read_text(encoding='utf-8-sig')
    assert '# pass 7' in (OUT/'frontend-tests.tap').read_text(encoding='utf-8-sig')
    assert sha(ROOT/'server/publish/VideoStudio.Server.dll')==sha(ROOT/'server/bin/Release/net8.0/VideoStudio.Server.dll')==sha(OUT/'deploy/VideoStudio.Server.dll')
    assert sha(ROOT/'web/public/character-story-preview.html')==sha(ROOT/'web/dist/character-story-preview.html')
    paths=['server/Program.cs','server/TaskSubmissionPreflightService.cs','server/GenerationQueue.cs','server/TaskLeaseRepository.cs','server/FfmpegService.cs','web/src/App.vue','config/workflow-contracts.json']
    whitespace=subprocess.run(['git','diff','--check','--',*paths],cwd=ROOT,capture_output=True,text=True,encoding='utf-8');(OUT/'diff-check.txt').write_text(whitespace.stdout+whitespace.stderr,encoding='utf-8');assert whitespace.returncode==0
    secretFiles=list((ROOT/'tools/character_story').glob('*.py'))+list((ROOT/'server').glob('CharacterStory*.cs'))+[ROOT/'server/CharacterWorkshopService.cs']
    patterns=[r'sk-[a-zA-Z0-9]{24,}',r'(?i)Bearer\s+[a-zA-Z0-9_.-]{20,}',r'(?i)password\s*=\s*[\"\'][^\"\']{8,}[\"\']']
    assert not [str(p.relative_to(ROOT)) for p in secretFiles if p.name not in ['final_checks.py','check_delivery.py'] and any(re.search(pattern,p.read_text(encoding='utf-8')) for pattern in patterns)]
    assert subprocess.run(['git','check-ignore','config/local.env'],cwd=ROOT,capture_output=True).returncode==0
    write(OUT/'final-runtime.json',dict(status='Passed',timestamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),health=health,queue=runtime['queue'],comfyQueue=queue,migration=ready,existingVersionsUnchanged=True,protectedFilesChecked=len(original['protectedFiles']),expansionCheckpointUnchanged=True,drafts=drafts,registeredNewTaskIds=allowed,newGpuTasks=len(registered),baseVideoTaskIds=baseVideos,newStoryBaseClips=4,deployedMatchesBuild=True,deployedDllSha256=sha(ROOT/'server/publish/VideoStudio.Server.dll'),backupDllSha256=sha(OUT/'server-before/VideoStudio.Server.dll'),diffCheck='Passed',literalSecretScan='Passed',secretFileIgnored=True,technical='Passed',contentReview='NeedReview',publication='Blocked'))
    print(f'Final runtime, queue1/idle, {len(registered)} real GPU tasks, four base clips, preservation, recovery, media and browser evidence Passed. Content remains NeedReview, publication Blocked.')
if __name__=='__main__':run()
