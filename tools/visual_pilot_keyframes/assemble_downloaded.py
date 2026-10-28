"""Offline recovery: assemble only already-complete range files, then verify official SHA256."""
from pathlib import Path
import hashlib,json,os,shutil
from download_models import ARTIFACTS,MODEL_ROOT,EVIDENCE_ROOT,file_hash

rows=[]
root=MODEL_ROOT.resolve()
for item in ARTIFACTS:
    target=(root/item['role']/item['name']).resolve()
    if not target.is_relative_to(root):raise RuntimeError('Unsafe assembly target')
    if target.exists():
        if target.stat().st_size!=item['size'] or file_hash(target)!=item['sha256']:raise RuntimeError('Existing artifact differs')
    else:
        parts=target.with_suffix(target.suffix+'.parts');layout=json.loads((parts/'ranges.json').read_text())
        sources=[];offset=0
        if layout['prefix_bytes']:
            prefix=target.with_suffix(target.suffix+'.partial')
            if prefix.stat().st_size!=layout['prefix_bytes']:raise RuntimeError('Prefix size changed')
            sources.append(prefix);offset=layout['prefix_bytes']
        for start,end in layout['ranges']:
            part=parts/f'{start:012d}-{end:012d}.part'
            if start!=offset or not part.is_file() or part.stat().st_size!=end-start+1:raise RuntimeError('Range incomplete or noncontiguous')
            sources.append(part);offset=end+1
        if offset!=item['size']:raise RuntimeError('Incomplete full artifact coverage')
        if shutil.disk_usage(root).free-item['size']<20*1024**3:raise RuntimeError('Assembly requires 20GiB remaining free disk')
        combined=target.with_suffix(target.suffix+'.assembled-v2')
        if combined.exists():raise RuntimeError('Recovery assembly already exists; inspect before rerunning')
        with combined.open('xb') as output:
            for source in sources:
                with source.open('rb') as stream:shutil.copyfileobj(stream,output,8*1024**2)
            output.flush();os.fsync(output.fileno())
        if combined.stat().st_size!=item['size'] or file_hash(combined)!=item['sha256']:raise RuntimeError('Official SHA256 mismatch; all inputs retained')
        combined.rename(target)
        # Only discard fresh download fragments after the canonical full model is verified.
        for source in sources:
            if not source.resolve().is_relative_to(root):raise RuntimeError('Unsafe fragment cleanup')
            source.unlink()
        (parts/'ranges.json').unlink();parts.rmdir()
    rows.append({**item,'path':str(target),'verified':True})
    print('Verified '+item['name'],flush=True)
report=dict(status='Passed',operation='offline assembly of completed ranges',artifacts=rows,
    diskFloorDuringAssemblyGiB=20,freeBytesAfter=shutil.disk_usage(root).free)
(EVIDENCE_ROOT/'download_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('KLEIN_MODEL_DOWNLOAD_VERIFIED',flush=True)
