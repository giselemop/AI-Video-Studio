"""Bounded read-only runtime sampling while the two recorded videos execute."""
import datetime
import shutil
import time
from run import Run,FOLDER,read,write

if __name__=='__main__':
    r=Run();r.access();samples=[];deadline=time.monotonic()+7200
    print('Sampling actual queue concurrency, GPU memory and disk every 10 seconds',flush=True)
    while time.monotonic()<deadline:
        stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            q=r.session.get('http://127.0.0.1:8188/queue',timeout=10).json()
            stats=r.session.get('http://127.0.0.1:8188/system_stats',timeout=10).json();device=stats['devices'][0]
            samples.append(dict(at=stamp,running=len(q['queue_running']),pending=len(q['queue_pending']),gpuName=device['name'],totalMiB=device['vram_total']//1048576,usedMiB=(device['vram_total']-device['vram_free'])//1048576,diskFreeGiB=round(shutil.disk_usage(FOLDER).free/(1024**3),2)))
        except Exception as error:samples.append(dict(at=stamp,error=str(error)[:300]))
        write(FOLDER/'resource-samples.json',samples)
        if read(FOLDER/'run.json')['stage'] in ['VideosReady','ReadyForUserPreview']:break
        time.sleep(10)
    print('Runtime samples retained; measured samples are not exact per-task peaks',flush=True)
