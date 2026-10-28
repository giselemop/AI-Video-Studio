"""Verify the delivered post-dubbing preview and submission boundaries."""
import json, subprocess
from character_plot_preview import Plot, ROOT, DATA, OUT, sha, write, mysql
from character_plot_verify import stored_task


def main():
    p=Plot();s=p.state;p.preserve();p.idle();frame=s['Keyframe'];video=s['Video'];preview=s['Preview']
    assert preview['status']=='Succeeded' and video['inspection']['payload']['decision']=='Passed'
    out=OUT/('preview-'+str(preview['id']));out.mkdir(exist_ok=True);checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='Passed' if ok else 'Failed'))
        if not ok:write(out/'checks.json',dict(status='Failed',checks=checks));raise AssertionError(name)
    task=stored_task(preview['id']);info=task['input']['parameters']['storyPreview'];clip=info['clips'][0]
    check('actual CPU preview depends on inspected H3 task',task['status']=='Succeeded' and task['dependency']==video['id'] and clip['taskId']==video['id'] and clip['reviewId']==video['inspection']['id'])
    check('source video path and hash retained',clip['path']==video['assetPath'] and clip['sha256']==video['sha256'] and sha(DATA/clip['path'])==clip['sha256'])
    check('post dubbing without selected audio',info['audioStrategy']=='PostDubbing' and info['audioPath'] is None and info['publication']=='Blocked')
    path=DATA/preview['assetPath'];check('delivered preview SHA256',sha(path)==preview['sha256'])
    probe=ROOT.parent.parent/'FFmpeg/bin/ffprobe.exe';ffmpeg=ROOT.parent.parent/'FFmpeg/bin/ffmpeg.exe'
    data=json.loads(subprocess.check_output([str(probe),'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'));write(out/'ffprobe.json',data)
    v=next(x for x in data['streams'] if x['codec_type']=='video')
    check('preview remains 864x480 24fps',v['width']==864 and v['height']==480 and v['avg_frame_rate']=='24/1')
    check('preview frames and duration',int(v['nb_read_frames'])==124 and abs(float(data['format']['duration'])-124/24)<.15)
    check('no audio stream in delivered post-dubbing preview',not any(x['codec_type']=='audio' for x in data['streams']))
    decoded=subprocess.run([str(ffmpeg),'-v','error','-i',str(path),'-f','null','-'],capture_output=True,timeout=120)
    check('full delivered preview decodes',decoded.returncode==0 and not decoded.stderr)
    response=p.s.get(p.base+'/api/media',params={'assetPath':preview['assetPath']},headers={'Range':'bytes=0-1023'},timeout=30)
    check('preview media supports browser range requests',response.status_code==206 and len(response.content)==1024)
    before=int(mysql('SELECT COUNT(*) FROM generation_tasks;'))
    existing=p.api('/api/character-story/generate/Video',video['body'])
    check('repeat video submission resolves same task without new generation',existing['id']==video['id'] and existing['created'] is False)
    existing=p.api('/api/character-story/preview',preview['body'])
    check('repeat preview submission resolves same task',existing['id']==preview['id'] and existing['created'] is False)
    for plan in [s['planId'],s['PlanHistory'][0]['planId']]:
        body=dict(planId=plan,profile='baseline480',seed=2026103151,repairOfTaskId=1553,changeReason='预算边界验证',promptAdjustment='No extra person.',idempotencyKey=p.key('budget-check-plan-'+str(plan)))
        response=p.s.post(p.base+'/api/character-story/generate/Keyframe',json=body,timeout=90)
        check('shot repair budget cannot be reset via plan '+str(plan),response.status_code==422 and '上限' in response.text)
    check('all idempotency and cap checks created no tasks',int(mysql('SELECT COUNT(*) FROM generation_tasks;'))==before)
    p.preserve()
    write(out/'checks.json',dict(status='Passed',checks=checks,videoTask=video['id'],previewTask=preview['id'],sha256=preview['sha256'],duration=data['format']['duration'],frames=v['nb_read_frames'],fps=v['avg_frame_rate'],audioStreams=0,contentReview='NeedReview',publication='Blocked'))
    print(str(len(checks))+' delivery, replay and retry-cap checks Passed; no new GPU tasks.')


if __name__=='__main__':main()
