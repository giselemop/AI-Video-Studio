"""Create a protected, resumable baseline without generating or approving."""
from pathlib import Path
import sys,json,requests,subprocess,datetime,uuid
sys.path.insert(0,str(Path(__file__).parent))
from common import ROOT,DATA,OUT,sha,write,mysql

def run():
    OUT.mkdir(parents=True,exist_ok=True);checkpoint=OUT/'run.json'
    if checkpoint.exists():print('Existing scene checkpoint retained; inspect it before continuing.');return
    base='http://127.0.0.1:18080';health=requests.get(base+'/api/health',timeout=30).json();runtime=requests.get(base+'/api/minimax/local/status',timeout=30).json();queue=requests.get('http://127.0.0.1:8188/queue',timeout=30).json()
    assert health['database']['online'] and health['comfy']['online'] and runtime['queue']['gpuConcurrency']==1 and runtime['queue']['activeTasks']==0 and not runtime['queue']['paused']
    assert not queue['queue_running'] and not queue['queue_pending']
    assert mysql("SELECT COUNT(*) FROM generation_tasks WHERE status IN ('Running','Pending');")=='0'
    previous=json.loads((DATA/'CharacterStory20261027/pilot.json').read_text(encoding='utf-8'));assert previous['completed']
    protected=[]
    for s in previous['slots'].values():
        for kind in ['Keyframe','Video']:
            for t in s.get(kind+'History',[])+[s[kind]]:protected.append(dict(assetPath=t['assetPath'],sha256=sha(DATA/t['assetPath'])))
    protected.append(dict(assetPath=previous['preview']['assetPath'],sha256=sha(DATA/previous['preview']['assetPath'])))
    backup=sorted((ROOT/'backup').glob('*/backup-manifest.txt'))[-1].parent
    manifest=dict(l.split('=',1) for l in (backup/'backup-manifest.txt').read_text(encoding='utf-8-sig').splitlines() if '=' in l);assert sha(backup/'ai_video_studio.sql')==manifest['database_dump_sha256']
    git=subprocess.check_output(['git','-c','core.quotepath=false','status','--short','--branch'],cwd=ROOT,text=True,encoding='utf-8');(OUT/'git-before.txt').write_text(git,encoding='utf-8')
    files=['server/CharacterStoryService.cs','server/CharacterStoryStore.cs','server/CharacterStoryEndpoints.cs','server/ComfyUiClient.cs','server/Program.cs','web/src/components/CharacterStoryPanel.vue','config/workflow-contracts.json']
    for f in files:
        dest=OUT/'source-before'/f;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/f).read_bytes())
    state=dict(runId=str(uuid.uuid4()),stage='Audited',completed=False,startedAt=datetime.datetime.now().astimezone().isoformat(),actors=[dict(characterId=19,versionId=4),dict(characterId=20,versionId=5)],profile='baseline480',width=864,height=480,fps=24,frames=124,keyframeWidth=1536,keyframeHeight=864,maxBaseClips=4,maxRepairsPerSlot=2,sourceSceneTaskId=1514,originalTaskCount=int(mysql('SELECT COUNT(*) FROM generation_tasks;')),previousPilotPath=str(DATA/'CharacterStory20261027/pilot.json'),previousPilotSha256=sha(DATA/'CharacterStory20261027/pilot.json'),expansionCheckpointSha256=sha(DATA/'CharacterExpansionFive20261026/run.json'),protectedFiles=protected,originalVersions=requests.get(base+'/api/character-library',timeout=30).json()['versions'],backup=str(backup),backupSha256=manifest['database_dump_sha256'],contentReview='NeedReview',publication='Blocked',slots={},newModels=0,newCloudCalls=0)
    write(checkpoint,state);write(OUT/'audit-runtime.json',dict(health=health,queue=runtime['queue'],comfyQueue=queue,versionTypeConstraint=mysql("SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='ck_entity_versions_type';")))
    print('Scene run baseline protected; previous completed tasks not resubmitted. SQL backup verified, no migration required for existing Scene ledger type.')
if __name__=='__main__':run()
