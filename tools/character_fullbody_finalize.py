"""Complete the preview checkpoint only when the actual edit and UI were verified."""
import json
import msvcrt
from character_fullbody_scene import Run, ROOT, DATA, OUT, sha

MARKER='<!-- character-fullbody-story-20261028 -->'

def main():
    with (OUT/'controller.lock').open('a+b') as lock:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        p=Run();s=p.state;p.preserve();p.require_reference()
        report=json.loads((OUT/'final-checks.json').read_text(encoding='utf-8'))
        browser=json.loads((OUT/'browser/playback.json').read_text(encoding='utf-8'))
        page=json.loads((OUT/'page.json').read_text(encoding='utf-8'))
        frame=s['images'][-1];video=s['videos'][-1];final=s['editTasks']['final']
        if (report['status']!='Passed' or report['taskId']!=final['id']
                or sha(DATA/final['assetPath'])!=final['sha256']
                or frame['inspection']['decision']!='Passed' or video['inspection']['decision']!='Failed'
                or video['rangeInspection']['decision']!='Passed'
                or not browser['endedState'][0]['ended'] or browser['endedState'][0]['currentTime']!=16.5
                or browser['endedState'][0]['muted'] or browser['browserErrors']
                or not 8.75<=browser['atFullbody'][0]['currentTime']<10.25
                or not (OUT/'browser/fullbody-shot.png').is_file()
                or sha(ROOT/'web/public/character-fullbody-story.html')!=page['sha256']):
            raise RuntimeError('The actual media, content or browser evidence is incomplete')
        report_path=ROOT/'docs/CHARACTER_FULLBODY_STORY_20261028.md'
        body=f"""# 《窗边等候》林安全身远景试片（2026-10-28）

## 实际结果和边界

用户希望将林安全身远景加入之前剧情。保留原15秒切镜版 #1572，在 8.75–10.25 秒插入1.5秒新全身画面，再接回原无人窗景和人物近景；总时长16.5秒。保留原三个旁白来源，第三句后移1.5秒，背景音乐以0.94倍速度铺满新时长并在结尾淡出。原音轨未覆盖；新片音频为重新混制，不声称与原片音轨哈希相同。

旧版角色 #3 有已审正面近照 #36，但没有已审核的全身造型参考。原剧情只显示米白上衣；深灰裤和白鞋依据人物库文字设定新生成，不能证明与原片画外的造型一致。被拒绝的全身参考 #43、#44 未作为输入；它们和双人场景的待审状态保持不变。新结果仅为本地实验性试片，未保存为已审核的人物库版本，也未声称满足正式全身选角门禁。

## 真实来源和候选

| 步骤 | 结果 |
|---|---|
| 原片 | #1572，SHA256 {s['baseSha256']}，未覆盖 |
| 原身份来源 | 人物版本 #3，已审近照 #36，SHA256 {s['sourceIdentitySha256']}；用于血缘和对照，不是本轮模型的直接图像输入 |
| 实际切镜参考 | 原片 #1572 第209帧，SHA256 {s['cutReference']['sha256']}；与直接解码相同，记录了任务依赖 |
| 初次关键帧 #1573 | 已保留；脸部和微笑与切镜前存在差异，预检 Failed |
| 第一次修复 #1574 | 以原片第209帧修复脸和表情，但针织上衣新增原片没有的麻花纹，预检 Failed |
| 第二次修复 #{frame['id']} | 去掉新增麻花纹，完整坐姿及双鞋可见，试片预检 Passed；脸部轻微差别、手指细节和窗格差异仍需人工查看；SHA256 {frame['sha256']} |
| 全身视频 #{video['id']} | 本地 H3 首帧路线，实际输入哈希与关键帧一致；864×480、24fps、124帧、20步；SHA256 {video['sha256']}。后半段出现无意义文字和张嘴，整段内容 Failed；逐帧检查前0–1.5秒后仅取前36帧，无原生声音 |
| 合成 #{final['id']} | 16.5秒、864×480、24fps、396帧，重新混制旁白和配乐；SHA256 {final['sha256']} |

## 测试与审看

实际业务任务、Comfy执行记录、原生输出文件和首帧哈希经过核对，视频全片解码通过；最终成片 FFprobe、媒体 Range、完整解码、抽样画面来源与三段旁白时序检查通过。浏览器完成16.5秒非静音播放，定位到全身画面并截图，无控制台错误。技术通过不等于原生完整视频内容合格，也不能替代人物一致性或听感的最终判断。

视觉限制：林安面部和表情较接近原片，但不保证完全一致；手指较小且相互靠近，窗格、墙面和背景细节与原近景及无人远景并非严格一致；裤鞋此前未出画，需要用户确认造型是否合适。

- 播放与对比：{page['url']}
- 成片：{DATA/final['assetPath']}
- 已截取的全身片段：{DATA/s['editTasks']['insert']['assetPath']}
- 原生完整视频（后半段内容失败，保留证据）：{DATA/video['assetPath']}
- 检查点：{OUT/'run.json'}
- 技术报告及 FFprobe：{OUT/'final-checks.json'}、{OUT/'final/ffprobe.json'}
- 实际图像/视频来源：{OUT/'image-checks.json'}、{OUT/'video-checks.json'}、{OUT/'range-inspection.json'} 和对应任务目录的 Comfy 历史
- 面部和手部对照：{OUT/'inspection/face-hands-shoes-1575.jpg'}
- 浏览器播放和截图：{OUT/'browser/playback.json'}、{OUT/'browser/fullbody-shot.png'}

技术状态 **Passed**；人物、服装、场景连续性和听感 **NeedReview**；正式发布 **Blocked**。已满两次针对关键帧的定向修复预算；旧候选、原片、人物审核和所有检查点均保留。

当前分支 main，未提交或推送。检查点完成后重新执行 tools/character_fullbody_scene.py prepare 只核验已有记录，不重提任务；发现来源变更先调查，不覆盖旧输出。
"""
        if report_path.exists():
            if report_path.read_text(encoding='utf-8')!=body:
                raise RuntimeError('Existing report differs and will not be overwritten')
        else: report_path.write_text(body,encoding='utf-8')
        sentence=(f"\n\n{MARKER}\n> 2026-10-28：《窗边等候》新增林安全身远景，"
                  f"关键帧{frame['id']}、H3视频{video['id']}、16.5秒成片{final['id']}；"
                  "原生视频后段出现文字而Failed，仅截取检查过的前1.5秒。"
                  "保留原窗景和旁白来源，第三句后移1.5秒，配乐略放慢。"
                  "成片技术和浏览器播放Passed；面部、手指、窗格及新补裤鞋NeedReview，发布Blocked；"
                  "被拒参考与双人待审状态不变。[详细记录](docs/CHARACTER_FULLBODY_STORY_20261028.md)。\n")
        for rel in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md',
                    'CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
            target=ROOT/rel
            if MARKER not in target.read_text(encoding='utf-8'):
                line=sentence.replace('(docs/CHARACTER_','(CHARACTER_') if rel.startswith('docs/') else sentence
                with target.open('a',encoding='utf-8',newline='') as f:f.write(line)
        p.preserve()
        s.update(completed=True,stage='CompletedForReview',contentReview='NeedReview',publication='Blocked',
                 finalVideoTaskId=final['id'],page=page['url'],
                 finalChecksPath=str(OUT/'final-checks.json'),browserChecksPath=str(OUT/'browser/playback.json'))
        p.save()
        print('Actual full-body preview checkpoint completed for user review.')

if __name__=='__main__':main()
