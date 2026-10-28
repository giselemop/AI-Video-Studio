"""Fixed CPU-only dual-person merge for the separately versioned stable profile."""
from pathlib import Path
import importlib.util,json,sys,time,os,hashlib
ROOT=Path(__file__).resolve().parents[2];DATA=(ROOT.parent/'Data').resolve()
BASE=ROOT/'tools/dialogue_sync_full/compose.py'
BASE_SHA='299faec60cdfbd87efadd26e010b0010325e764808802b651d980f01a640b605'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise RuntimeError('Frozen merge engine changed')
spec=importlib.util.spec_from_file_location('stable_merge_base',BASE);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
PROFILE='dialogue-stable-compose-v1'
def validate(q):
    if Path(q['dataRoot']).resolve()!=DATA:raise ValueError('Fixed Data root required')
    manifest=d.path(q['manifest'])
    if d.sha(manifest)!=q['manifestSha256']:raise ValueError('Manifest changed')
    m=json.loads(manifest.read_text(encoding='utf-8-sig'))
    if (m.get('profile'),m.get('phase'),m.get('width'),m.get('height'),m.get('frames'),m.get('fps'))!=(PROFILE,'merge',1024,576,151,25):raise ValueError('Unregistered stable composition')
    f={}
    for role,item in m['files'].items():
        f[role]=d.path(item['path'])
        if d.sha(f[role])!=item['sha256']:raise ValueError('Input changed '+role)
    for role,direction,stable in [('left','left-right','female-wide'),('right','right-left','male-wide')]:
        receipt=json.loads(f[role+'Receipt'].read_text(encoding='utf-8-sig'))
        if receipt['repairProfile']!='dialogue-stable-v2' or receipt['stableRole']!=stable or receipt['faceDirection']!=direction or receipt['sourceSha256']!=m['files']['source']['sha256'] or receipt['faceSupportMaskSha256']!=m['files'][role+'Mask']['sha256']:raise ValueError('Role receipt mismatch')
        v,fps,seconds=d.d.probe(f[role],q['ffprobe'])
        if (v['width'],v['height'],int(v['nb_read_frames']),fps)!=(1024,576,151,25):raise ValueError('Role video differs')
        mask=d.cv2.imread(str(f[role+'Mask']),0)
        if mask is None or mask.shape!=(576,1024) or d.np.count_nonzero(mask)<500:raise ValueError('Role mask differs')
    source=d.cv2.imread(str(f['source']))
    if source is None or source.shape[:2]!=(576,1024):raise ValueError('Source differs')
    return m,f
def main():
    q=json.load(sys.stdin);m,f=validate(q)
    if q.get('validateOnly'):print(json.dumps(dict(status='Passed',phase='merge')));return
    out=d.path(q['output'],False)
    if out.exists():raise FileExistsError(out)
    started=time.monotonic();result=d.merge(q,m,f,out)
    for role,p in f.items():
        if d.sha(p)!=m['files'][role]['sha256']:raise RuntimeError('Input changed during merge')
    receipt=dict(status='Passed',profile=PROFILE,phase='merge',manifestSha256=q['manifestSha256'],width=1024,height=576,fps=25,frameCount=151,durationSeconds=151/25,outputPath=str(out),outputSha256=d.sha(out),cpuOnly=True,cloudCalls=0,seconds=time.monotonic()-started,contentStatus='NeedReview',publicationStatus='Blocked',**result)
    Path(str(out)+'.dialogue.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print('Passed: stable merge')
if __name__=='__main__':
    import socket
    def offline(*a,**kw):raise RuntimeError('Network disabled')
    socket.socket.connect=offline;socket.socket.connect_ex=offline;socket.create_connection=offline
    os.environ['CUDA_VISIBLE_DEVICES']='';main()
