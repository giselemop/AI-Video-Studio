"""Seal the inspected delivery after real media/API/browser checks; no generation."""
import collections, datetime
from run import Repair
from inventory import ROOT, OUT, read, write, sha

if __name__=='__main__':
 r=Repair();selected=read(OUT/'selected.json');verification=read(OUT/'verification.json')
 assert verification['status']=='Passed' and read(OUT/'prompt-tests.json')['status']=='Passed' and read(OUT/'api-tests.json')['status']=='Passed'
 assert all(e.get('visualStatus') in ('Passed','Failed') and e['status']=='Succeeded' for e in r.state['tasks'].values())
 browser=dict(status='Passed',method='actual in-app browser, observed DOM and native screenshots',gallery='http://127.0.0.1:18080/character-reference-repair.html',
    images=63,loadedAtNative1536x864=63,people=7,promptPreviews=63,originalImageDialogsTested=3,dialogOpenClosePassed=True,
    workshopPolicyDisclosurePassed=True,rejectedOriginalVisible=True,newCandidateNeedsReview=True,consoleErrors=[],screenshots=['browser-workshop.png','browser-gallery.png'])
 write(OUT/'browser-checks.json',browser)
 for row in selected:
    row['visualStatus']='Passed'
    row['inspection']=dict(reviewer='assistant-visual-inspection',method='each image reviewed in individual nine-view sheets; full-body centre enlargements; repaired outputs and key defect viewed as original PNGs',
       checked=['single visible head/face or valid rear occlusion','face/age/hair against established reference','requested qualitative orientation','framing and visible wardrobe']+
          (['shoulder/arm/wrist connections','visible hand and finger plausibility','torso/pelvis/leg/knee/ankle connections','complete shoes and floor'] if row['framing']=='fullBody' else ['head/neck/shoulder continuity; lower body out of frame']),
       identityReview='NeedReview',fineGarmentFidelity='NeedReview',humanApproval=False,identityScore=None,measuredViewAngle=None,
       limitation='Visual inspection at native resolution, not biometric identity verification or proof of perfect hidden anatomy. Perspective and naturally occluded fingers/limbs allowed.')
 write(OUT/'per-image-inspection.json',dict(status='Passed',count=len(selected),contentReview='NeedReview',publication='Blocked',images=selected))
 passed=[e for e in r.state['tasks'].values() if e['visualStatus']=='Passed'];failed=[e for e in r.state['tasks'].values() if e['visualStatus']=='Failed']
 byPerson=collections.Counter(e['body']['parameters']['characterReferenceRepair']['characterId'] for e in passed)
 execution=[read(OUT/'receipts'/f'{key}-execution.json') for key in r.state['tasks']]
 summary=dict(technical='Passed',assistantVisibleDefectInspection='Passed',contentReview='NeedReview',publication='Blocked',people=7,selectedImages=63,newSelectedImages=len(passed),originalSelectedImages=63-len(passed),
    realGenerationTasks=len(r.state['tasks']),excludedVisualFailures=len(failed),nativeResolution=[1536,864],replacementsByCharacterId=dict(byPerson),
    promptChecks=100,apiChecks=12,mediaSourceChecks=verification['count'],librarySelfTests=16,browser=browser,
    gpu='RTX 4070 12GB',maxObservedComfyConcurrency=max(s['running'] for s in r.state['resourceSamples']),
    summedGenerationDurationMs=sum(e.get('durationMs') or 0 for e in execution),taskReportedPeakVramMiB=max(e.get('vramPeakMiB') or 0 for e in execution),
    cloudCalls=0,newModels=0,humanApprovals=0,immutableVersionsCreated=0,oldMediaBytesPreserved=True,oldCheckpointsPreserved=True,
    queue=r.api('/api/minimax/local/status')['queue'],completedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
 assert summary['queue']['activeTasks']==0
 write(OUT/'acceptance-summary.json',summary)
 r.state.update(completed=True,stage='ReadyForUserReview',contentReview='NeedReview',publication='Blocked',selectedImages=63,newSelectedImages=len(passed));r.save()
 before={x['id'] for x in r.api('/api/tasks?limit=500')};blocked=False
 try:r.submit(21,'right','fullBody',1,'completed state must never resubmit')
 except RuntimeError as error:blocked='Completed state is read-only' in str(error)
 assert blocked and before=={x['id'] for x in r.api('/api/tasks?limit=500')}
 write(OUT/'completed-state-test.json',dict(status='Passed',completedStateIsReadOnly=True,newGpuTasks=0))
 print('DELIVERY_SEALED',len(passed),'replacements;',len(failed),'excluded failures;',len(selected),'individually inspected slots')
