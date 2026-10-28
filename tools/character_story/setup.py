"""Apply the additive ledger migration only after verifying a real SQL backup.
Installs a four-reference graph derived from the existing Klein graph; no weights.
"""
from pathlib import Path
import hashlib,json,os,subprocess,copy,uuid
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT.parent/'Data'
OUT=DATA/'CharacterStory20261027'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);temporary=p.with_name(p.name+'.tmp-'+uuid.uuid4().hex)
    with temporary.open('w',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(v,ensure_ascii=False,indent=2));stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,p)
def mysql(query):
    values={}
    for line in (ROOT/'config/local.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);values[k.strip()]=v.strip().strip('"').strip("'")
    env=dict(os.environ,MYSQL_PWD=values['AI_VIDEO_STUDIO_DB_PASSWORD'])
    result=subprocess.run(['C:/install/mysql8.0.22/bin/mysql.exe','--protocol=TCP','--default-character-set=utf8mb4','-h',values.get('AI_VIDEO_STUDIO_DB_HOST','127.0.0.1'),'-P',values.get('AI_VIDEO_STUDIO_DB_PORT','3306'),'-u',values['AI_VIDEO_STUDIO_DB_USER'],'-N','-B','--raw',values['AI_VIDEO_STUDIO_DB_NAME']],input=query,capture_output=True,text=True,encoding='utf-8',env=env)
    if result.returncode:raise RuntimeError(result.stderr.replace(values['AI_VIDEO_STUDIO_DB_PASSWORD'],'[REDACTED]'))
    return result.stdout.strip()
def migrate():
    state=json.loads((OUT/'run.json').read_text(encoding='utf-8')) if (OUT/'run.json').exists() else {}
    backup=ROOT/state.get('backup','backup/20261027_021612')
    manifest=dict(l.split('=',1) for l in (backup/'backup-manifest.txt').read_text(encoding='utf-8-sig').splitlines() if '=' in l)
    assert sha(backup/'ai_video_studio.sql')==manifest['database_dump_sha256']
    assert (backup/'ai_video_studio.sql').stat().st_size>1000000
    before=mysql("SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='ck_entity_versions_type';")
    counts=mysql('SELECT (SELECT COUNT(*) FROM projects),(SELECT COUNT(*) FROM generation_tasks),(SELECT COUNT(*) FROM entity_versions);')
    migration=ROOT/'database/migrations/010_character_story_records.sql'
    applied='ShotCast' not in before
    if applied:
        try:mysql(migration.read_text(encoding='utf-8-sig'))
        except RuntimeError as error:
            write(OUT/'migration-010.json',dict(applied=False,backup=str(backup),backupSha256=manifest['database_dump_sha256'],migrationSha256=sha(migration),countsBefore=counts,before=before,status='Blocked',error=str(error),businessRowsChanged=False))
            raise
    after=mysql("SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME='ck_entity_versions_type';")
    assert all(t in after for t in ['Character','Workflow','ShotCast','CharacterWorkflow'])
    assert counts==mysql('SELECT (SELECT COUNT(*) FROM projects),(SELECT COUNT(*) FROM generation_tasks),(SELECT COUNT(*) FROM entity_versions);')
    write(OUT/'migration-010.json',dict(applied=applied,backup=str(backup),backupSha256=manifest['database_dump_sha256'],migrationSha256=sha(migration),countsBeforeAfter=counts,before=before,after=after,status='Passed'))
def workflow():
    folder=ROOT/'tools/character_story';source=ROOT.parent/'Workflows/character_pack_klein4b_dual_api.json'
    graph=json.loads(source.read_text(encoding='utf-8-sig'))
    for start,prevpos,prevneg in [(30,'23','24'),(40,'33','34')]:
        graph[str(start)]={'class_type':'LoadImage','inputs':{'image':'actor-b-reference.png'}}
        graph[str(start+1)]={'class_type':'ImageScaleToTotalPixels','inputs':{'image':[str(start),0],'upscale_method':'lanczos','megapixels':1.0,'resolution_steps':1}}
        graph[str(start+2)]={'class_type':'VAEEncode','inputs':{'pixels':[str(start+1),0],'vae':['3',0]}}
        for offset,prior in [(3,prevpos),(4,prevneg)]:graph[str(start+offset)]={'class_type':'ReferenceLatent','inputs':{'conditioning':[prior,0],'latent':[str(start+2),0]}}
    graph['11']['inputs']['positive']=['43',0];graph['11']['inputs']['negative']=['44',0]
    name='character_story_klein4b_four_api.json'
    dest=ROOT.parent/'Workflows'/name
    serialized=json.dumps(graph,ensure_ascii=False,indent=2)+'\n'
    if dest.exists() and dest.read_text(encoding='utf-8')!=serialized:raise RuntimeError('Existing four-reference graph differs; preserve it')
    dest.write_text(serialized,encoding='utf-8');(folder/name).write_text(serialized,encoding='utf-8')
    contract=copy.deepcopy(json.loads((ROOT/'tools/character_reference_pack/character-pack-klein4b-dual-1536-v1.contract.json').read_text()))
    contract.update(id='character-story-klein4b-four-1536-v1',version='character-story-klein4b-four-1536-v1',fileName=name,notes='sha256='+sha(dest)+' | Two distinct identities, each with separate wardrobe input; static candidate requires actual inspection. Not H3 Ref2VA. Experimental, no production/publication eligibility.')
    for role,node in [('secondIdentity','30'),('secondWardrobe','40')]:contract['slots'].append(dict(role=role,nodeId=node,classType='LoadImage',inputName='image',required=True))
    for role,node in [('secondIdentityPositive','33'),('secondIdentityNegative','34'),('secondWardrobePositive','43'),('secondWardrobeNegative','44')]:contract['nodes'].append(dict(role=role,nodeId=node,classType='ReferenceLatent',inputName='latent'))
    write(folder/'character-story-klein4b-four-1536-v1.contract.json',contract)
    cfg=ROOT/'config/workflow-contracts.json';config=json.loads(cfg.read_text(encoding='utf-8-sig'))
    existing=next((c for c in config['contracts'] if c['id']==contract['id']),None)
    if existing and existing!=contract:raise RuntimeError('Existing contract differs; preserve it')
    if not existing:config['contracts'].append(contract);write(cfg,config)
    write(OUT/'workflow-four-inputs.json',dict(path=str(dest),sha256=sha(dest),slots=contract['slots'],empiricalValidation='Pending',h3Ref2VA=False))
def review_audit():
    if mysql("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='character_reference_reviews';")=='1':
        write(OUT/'migration-011.json',dict(status='Passed',tablePresent=True,appliedByThisRun=False));return
    migration=ROOT/'database/migrations/011_character_reference_review_audit.sql'
    try:mysql(migration.read_text(encoding='utf-8-sig'))
    except RuntimeError as error:
        write(OUT/'migration-011.json',dict(status='Blocked',tablePresent=False,migrationSha256=sha(migration),error=str(error),businessRowsChanged=False));raise
    write(OUT/'migration-011.json',dict(status='Passed',tablePresent=True,appliedByThisRun=True,migrationSha256=sha(migration)))
if __name__=='__main__':migrate();review_audit();workflow();print('Backup verified; required schema and candidate graph checked.')
