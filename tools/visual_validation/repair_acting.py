"""At most two documented, local-only targeted reenactment repairs; retain every take."""
from run import *

parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,choices=[1,2],required=True);args=parser.parse_args()
run=Run('http://127.0.0.1:18081',FOLDER/'run.json');run.preserve();run.access()
if run.state.get('completed'):raise RuntimeError('Completed package is read-only')
reason=read(FOLDER/f'acting-repair-{args.attempt}.json')
params=reason.get('parameters',{})
if not reason.get('reason') or not params or set(params)-{'drivingMultiplier','animationRegion'}:
    raise RuntimeError('A bounded, relevant repair reason and parameter change are required')
manifest=FOLDER/f'acting-manifest-repair-{args.attempt}.json'
value=read(FOLDER/'acting-manifest.json');value.update(params)
if manifest.exists() and read(manifest)!=value:raise RuntimeError('Repair manifest changed')
if not manifest.exists():write(manifest,value)
body=dict(projectId=run.state['projectId'],taskType='VisualActing',resourceClass='GPU',maxRetries=0,
    stage=f'Visual-Validation-Reference-Acting-Repair-{args.attempt}',parameters=dict(
        manifest=rel(manifest),manifestSha256=sha(manifest),engineVersion=sha(ROOT/'tools/visual_pilot_acting/run.py')))
detail=run.once(f'actingRepair{args.attempt}TaskId',body);path=result(detail,'.mp4')
receipt=next(x['assetPath'] for x in detail['results'] if x.get('available') and 'visual_acting_receipt' in x.get('assetPath',''))
candidates=run.state.get('actingCandidates',[])
for item in [dict(taskId=run.state.get('actingSelectedTaskId',run.state['actingTaskId']),path=run.state['actingPath'],sha256=run.state['actingSha256']),
             dict(taskId=detail['task']['id'],path=path,sha256=sha(media(path)))]:
    if item['taskId'] not in [x['taskId'] for x in candidates]:candidates.append(item)
run.save('AwaitingActingInspection',actingCandidates=candidates,actingSelectedTaskId=detail['task']['id'],
    actingPath=path,actingSha256=sha(media(path)),actingReceiptPath=receipt)
print(path,flush=True)
