"""Finalize only after real media and browser evidence; never submit generation."""
import json
import re
from urllib.parse import urlparse,parse_qs
from run import ROOT,DATA,FOLDER,REPORT,StoryRun,sha
from download_assets import download_lock
from sync_docs import main as sync_docs


def main():
    with download_lock(FOLDER,'.two-person-story.lock','A story runner is still active'):
        run=StoryRun('http://127.0.0.1:18080',REPORT)
        state=run.state
        if state.get('stage') not in ['AwaitingPlaybackInspection','ReadyForUserPreview']:
            raise RuntimeError('A completed real assembly and review are required')
        delivery=json.loads((FOLDER/'delivery-verification.json').read_text(encoding='utf-8'))
        browser=json.loads((FOLDER/'browser-final-playback.json').read_text(encoding='utf-8'))
        if delivery.get('status')!='Passed' or browser.get('status')!='Passed':
            raise RuntimeError('Both delivery and actual browser checks must pass')
        if sha(DATA/state['finalVideoPath'])!=state['finalVideoSha256'] or delivery['finalVideoSha256']!=state['finalVideoSha256']:
            raise RuntimeError('Final SHA differs from its verification')
        actual=browser['actual']
        played_path=parse_qs(urlparse(actual['src']).query).get('assetPath',[''])[0]
        if played_path!=state['finalVideoPath']:
            raise RuntimeError('The browser played another asset')
        if ((actual['width'],actual['height'])!=(1280,720) or abs(actual['duration']-31)>.06
                or not actual['ended'] or actual['time']<30.95 or actual['error'] is not None
                or actual['muted'] or actual['volumePercent']!=100):
            raise RuntimeError('Actual complete audible playback was not demonstrated')
        if browser['beforePlayback']['time']>.5 or browser['elapsedWallSeconds']<30.9:
            raise RuntimeError('The full-from-start playback evidence is incomplete')
        run.access()
        task_ids=[state[f'shot{n}TaskId'] for n in range(1,7)]+[state[f'dialogue{n}TaskId'] for n in range(1,12)]+[state['assemblyTaskId']]
        tasks=[run.api(f'/api/tasks/{task_id}')['task'] for task_id in task_ids]
        if any(task['status']!='Succeeded' for task in tasks):raise RuntimeError('A required real task is not successful')
        for number in range(1,7):
            review=json.loads((FOLDER/f'shot-{number:02}/review.json').read_text(encoding='utf-8'))
            if review.get('decision')!='SelectedForContinuation':raise RuntimeError('An actual source review is missing')
        samples=[json.loads(line) for line in (FOLDER/'resources.jsonl').read_text(encoding='utf-8').splitlines() if line]
        valid=[s for s in samples if 'usedVramMiB' in s and 'systemAvailableMiB' in s]
        health=run.api('/api/health')
        summary=dict(status='Passed',projectId=state['projectId'],finalTaskId=state['assemblyTaskId'],
            finalVideoPath=state['finalVideoPath'],finalVideoSha256=state['finalVideoSha256'],
            output=dict(width=1280,height=720,fps=24,frames=744,durationSeconds=31),
            sourceTaskIds=[state[f'shot{n}TaskId'] for n in range(1,7)],sourceCanvas=[1376,768],steps=20,
            videoGpuTaskDurationMs=sum(state[f'shot{n}TaskMetrics']['durationMs'] for n in range(1,7)),
            ttsTaskDurationMs=sum(task['durationMs'] or 0 for task in tasks if task['id'] in [state[f'dialogue{n}TaskId'] for n in range(1,12)]),
            assemblyTaskDurationMs=next(task['durationMs'] for task in tasks if task['id']==state['assemblyTaskId']),
            resourceSampling=dict(nominalIntervalSeconds=5,samples=len(valid),devicePeakMiB=max(s['usedVramMiB'] for s in valid),
                minimumAvailableRamMiB=min(s['systemAvailableMiB'] for s in valid),gpu=health['comfy']['gpu']),
            completeOriginalSpeedQwenLines=11,contentStatus='NeedReview',publicationStatus='Blocked',
            limitations=['The opening starts after returning home; the entry shot is omitted.',
                'The wardrobe and staging follow the actual new SDXL identities.',
                'Sofa wrestling is simplified to forearm and cushion play.',
                'Fine hands/feet, some props/room expansion and strict Qwen lip synchronization need human review.'])
        (FOLDER/'execution-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        run.save('ReadyForUserPreview',technicalStatus='Passed',contentStatus='NeedReview',publicationStatus='Blocked',
            finalDurationSeconds=31,previewUrl='http://127.0.0.1:18080/two-person-story-preview.html',deliverySummary=summary,error=None)
        sync_docs()
        report=ROOT/'docs/DOUYIN_REFERENCE_20261023.md'
        old=report.read_text(encoding='utf-8')
        gpu_seconds=summary['videoGpuTaskDurationMs']/1000
        block=('<!-- final-delivery:start -->\n## 最终可观看文件\n\n'
            f'- 最终业务任务：{summary["finalTaskId"]}，实际Succeeded；六段视频为'+','.join(map(str,summary['sourceTaskIds']))+'。\n'
            f'- 成片：`C:/install/AI/Data/{summary["finalVideoPath"]}`\n'
            f'- SHA256：`{summary["finalVideoSha256"]}`\n'
            '- 实测1280×720、24FPS、744帧、31秒；完整解码、11句Qwen逐句/完整音轨比对、真实浏览器从头到尾播放Passed。\n'
            f'- 视频GPU任务合计{gpu_seconds:.3f}秒；CPU合成{summary["assemblyTaskDurationMs"]/1000:.3f}秒。'
            f'约5秒整卡采样峰值{summary["resourceSampling"]["devicePeakMiB"]}MiB，最低可用系统RAM{summary["resourceSampling"]["minimumAvailableRamMiB"]}MiB。\n'
            '- 浏览器按同一最终路径验证，未静音且页面实际音量显示100%，点击从头播放至31秒；帧数由FFmpeg完整解码确认。\n'
            '- 内容仍NeedReview，发布Blocked。动作和布景按照本轮已记录的改编，不声明达到原片或闭源模型的细节/口型水平。\n'
            '- 恢复执行run.py --stage check；ReadyForUserPreview只核已有任务和SHA，不新增推理。\n'
            '<!-- final-delivery:end -->')
        pattern=r'<!-- final-delivery:start -->.*?<!-- final-delivery:end -->'
        updated=re.sub(pattern,lambda match:block,old,count=1,flags=re.S) if re.search(pattern,old,flags=re.S) else old+'\n\n'+block+'\n'
        if updated!=old:report.write_text(updated,encoding='utf-8')
        print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
