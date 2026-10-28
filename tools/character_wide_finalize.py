"""Close only the verified cutaway preview checkpoint and append its evidence."""
import json
import msvcrt
from character_wide_cutaway import Cutaway, ROOT, DATA, OUT, sha

MARKER = '<!-- character-wide-cutaway-20261028 -->'

def main():
    with (OUT / 'controller.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        p = Cutaway()
        s = p.state
        p.preserve()
        technical = json.loads((OUT / 'final-checks.json').read_text(encoding='utf-8'))
        browser = json.loads((OUT / 'browser/playback.json').read_text(encoding='utf-8'))
        page = json.loads((OUT / 'page.json').read_text(encoding='utf-8'))
        final = s['editTasks']['final']
        if (technical['status'] != 'Passed' or technical['taskId'] != final['id']
                or sha(DATA / final['assetPath']) != final['sha256']
                or not browser['endedState'][0]['ended']
                or browser['endedState'][0]['currentTime'] != 15
                or browser['endedState'][0]['muted']
                or browser['at9'][0]['currentTime'] != 9
                or browser['browserErrors'] or not s.get('finalInspection')
                or not (OUT / 'browser/cutaway-at-9s.png').is_file()
                or sha(ROOT / 'web/public/character-wide-cutaway.html') != page['sha256']):
            raise RuntimeError('The actual technical, playback or visual evidence is incomplete')

        report_path = ROOT / 'docs/CHARACTER_WIDE_CUTAWAY_20261028.md'
        body = f"""# 《窗边等候》环境远景切镜试片（2026-10-28）

## 实际产出与范围

用户希望看远景切镜或其他画面。本次以原15秒有声试片 #1565 为基础，在 **8.75–10.25秒** 插入无人窗边环境镜头，随后切回林安。原始成片、声音、关键帧、人物版本与先前双人待审状态均保留。林安全身参考仍有被拒绝内容，本次未使用这些素材，也未声称这是人物全身远景。

原画面的木窗与树景用于场景参考，但新画面窗格和房间布局并非完全相同，生成图也没有出现提示词中要求的小桌。场景是氛围示例，不能把它当作同一房间几何连续性已通过的证据；运动比较轻微。

## 真实任务与证据

| 步骤 | 任务/结果 |
|---|---|
| 场景参考 | 已保留原关键帧 #1554，SHA256 {s['locationFrameSha256']} |
| 新远景关键帧 | #1566，Klein 现有工作流，1536×864，SHA256 {s['images'][-1]['sha256']}；已查看实际图片，人物不存在，小桌缺失 |
| 环境视频 | #1567，现有 MiniMax H3 FL2VA 首帧实验工作流，864×480、24fps、124帧、20步；实际首帧哈希与 #1566 一致，Comfy 历史和原生输出匹配；SHA256 {s['video']['sha256']} |
| 画面剪辑 | #1568（前段）、#1569（远景）、#1570（后段）、#1571（拼接），均通过业务 CPU 队列，来源哈希受检 |
| 完整成片 | #{final['id']}，15秒、864×480、24fps、360帧，SHA256 {final['sha256']} |
| 声音 | 从原片无损复制 AAC 音轨，源与新片的音频包 SHA256 同为 {technical['finalAudioSha256']}；无新增配音或音乐 |
| 视频路线 | 无人环境镜头使用既有 ImageToVideo 实验入口，先检查真实关键帧再进 H3；未声称多人物身份绑定或正式剧情镜头审核通过 |

媒体经过 FFprobe、完整音视频解码及媒体接口 Range/206 检查。对切入前、切入后和两个切点的抽样画面与原片/环境源作像素差核对（这只是剪辑核对，不是人物身份分数）。原字幕区间 0.4–4.56、5.5–8.7、10.8–14.48 秒不与插入区间重叠；成片字幕来自原画面。剪辑为重新编码，像素并非逐字节相同。

浏览器实际播放到 15 秒结束、非静音、无控制台错误；9 秒处截图显示环境远景；原片播放器可加载。未把浏览器可播放等同于听感或内容最终通过。

- 观看与对照：{page['url']}
- 新成片：{DATA / final['assetPath']}
- 任务/检查点：{OUT / 'run.json'}
- 关键帧和 H3 血缘：{OUT / 'image-checks.json'}、{OUT / 'video-checks.json'} 及各任务目录的 Comfy 历史
- 合成验证、FFprobe 与抽帧：{OUT / 'final-checks.json'}、{OUT / 'final'}
- 浏览器回放记录与截图：{OUT / 'browser/playback.json'}、{OUT / 'browser/cutaway-at-9s.png'}

## 验收与恢复

- 技术和浏览器播放：**Passed**。实际画面切镜可见，原 AAC 音频包哈希一致。
- 内容和听感：**NeedReview**。远景几乎静止，窗格/房间布局不同；人物、切镜和听感等待用户审看。
- 正式发布：**Blocked**。不得把本地试片当成正式审核或人物全身素材。
- 未生成或恢复被拒素材；此前双人场景仍保持待审。
- 原片及其检查点和素材 SHA256 在执行前后比对一致。模型、人物库、原片均未清理、覆盖或重置。
- 控制器检查点 Data/CharacterSceneCutaway20261028/run.json 标记完成后，重新执行 tools/character_wide_cutaway.py prepare 只核验并恢复记录，不重新提交任务；遇到不确定提交记录先查业务任务而非重复生成。
- 当前分支 main，本轮未提交、未推送；本地原有未提交修改保留。
"""
        if report_path.exists():
            if report_path.read_text(encoding='utf-8') != body:
                raise RuntimeError('Existing cutaway report differs; preserve it for inspection')
        else:
            report_path.write_text(body, encoding='utf-8')

        sentence = (f"\n\n{MARKER}\n> 2026-10-28：《窗边等候》增加无人窗边环境切镜："
                    f"关键帧1566、H3视频1567、最终成片{final['id']}；"
                    "8.75–10.25秒插入，保留原15秒音轨与字幕。技术和浏览器播放Passed；"
                    "窗格/房间布局不完全一致，内容和听感NeedReview，发布Blocked；"
                    "双人待审状态不变。"
                    "[详细证据](docs/CHARACTER_WIDE_CUTAWAY_20261028.md)。\n")
        for relative in ['项目状态.md', '待办事项.md', '变更记录.md', 'PROJECT_STATE.md',
                         'NEXT_STAGE.md', 'CHANGELOG.md', 'docs/ACCEPTANCE_REPORT.md',
                         'docs/FIX_HISTORY.md']:
            target = ROOT / relative
            text = target.read_text(encoding='utf-8')
            if MARKER not in text:
                item = sentence.replace('(docs/CHARACTER_', '(CHARACTER_') if relative.startswith('docs/') else sentence
                with target.open('a', encoding='utf-8', newline='') as f:
                    f.write(item)

        p.preserve()
        s.update(completed=True, stage='CompletedForReview', contentReview='NeedReview',
                 publication='Blocked', finalVideoTaskId=final['id'], page=page['url'],
                 finalChecksPath=str(OUT / 'final-checks.json'),
                 browserChecksPath=str(OUT / 'browser/playback.json'))
        p.save()
        print('Cutaway checkpoint completed for review; original sources and holds remain protected.')

if __name__ == '__main__':
    main()
