"""Create a read-only review page for this run's actual inspected video."""
import json
from character_plot_preview import ROOT, OUT, sha, write


def main():
    state=json.loads((OUT/'run.json').read_text(encoding='utf-8'));frame=state['Keyframe'];video=state['Video'];preview=state['Preview']
    if video.get('inspection',{}).get('payload',{}).get('decision')!='Passed' or preview.get('status')!='Succeeded':raise RuntimeError('Do not advertise uninspected or incomplete preview')
    data=dict(playTaskId=preview['id'],videoTaskId=video['id'],projectId=state['projectId'],shotId=state['shotId'],planId=state['planId'],reference=state['sourceReference'],keyframe={k:frame[k] for k in ['id','assetPath','sha256']},videoSha256=video['sha256'],previewSha256=preview['sha256'],inspection=video['inspection']['payload']['note'],contentReview='NeedReview',publication='Blocked')
    payload=json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
    template=(ROOT/'tools/character_plot_review.template.html').read_text(encoding='utf-8');html=template.replace('__PAYLOAD__',payload)
    for folder in [ROOT/'web/public',ROOT/'web/dist']:
        target=folder/'character-plot-preview.html'
        if target.exists() and target.read_text(encoding='utf-8')!=html:raise RuntimeError('Existing preview page differs; preserve it')
        target.write_text(html,encoding='utf-8')
    write(OUT/'preview-page.json',dict(url='http://127.0.0.1:18080/character-plot-preview.html',sha256=sha(ROOT/'web/public/character-plot-preview.html'),videoTaskId=video['id'],playTaskId=preview['id']))
    print('Created real, silent plot preview page; final content remains NeedReview.')


if __name__=='__main__':main()
