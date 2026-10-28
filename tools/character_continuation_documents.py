"""Append bounded completion notes without rewriting shared archives."""
from character_continuation import ROOT

MARKER='<!-- character-story-15s-20261028 -->'
zh='2026-10-28：《窗边等候》已续成15秒有声试片：原片1555、续片1562/1563，Qwen旁白1557–1559、本地原创器乐1560，最终合成1565。技术、来源、全片解码和浏览器播放Passed；人物细节、音色及整体听感仍NeedReview，发布Blocked。双人场景保持待审。[详细记录](docs/CHARACTER_STORY_15S_20261028.md)。'
en='2026-10-28: Window Waiting is a real 15-second narrated local preview (final task 1565; source clips 1555/1562/1563, narration 1557–1559 and original music 1560). Technical and browser checks Passed; content and listening remain NeedReview, publication Blocked. See [the detailed report](CHARACTER_STORY_15S_20261028.md).'
entries={
 '项目状态.md':zh,
 '待办事项.md':'2026-10-28：《窗边等候》15秒有声试片和技术验证已完成；待用户听看人物连续性、结尾表情、旁白及配乐，不自动批准发布。双人场景继续待审。[验收记录](docs/CHARACTER_STORY_15S_20261028.md)。',
 '变更记录.md':'2026-10-28：剧情服务增加同场景、同角色版本的已检查视频实际尾帧续接及来源哈希校验；加入固定曲目的本地CPU原创配乐任务、可选音轨淡出和可选合成来源哈希校验。实际成片1565完成，内容与听感待审。[详情](docs/CHARACTER_STORY_15S_20261028.md)。',
 'PROJECT_STATE.md':zh,
 'NEXT_STAGE.md':'2026-10-28：《窗边等候》15秒有声成片1565可供用户听看；人物、动作、音色和混音仍需人工判断，发布Blocked。下一步不自动重新生成已完成任务。[验收记录](docs/CHARACTER_STORY_15S_20261028.md)。',
 'CHANGELOG.md':zh,
 'docs/ACCEPTANCE_REPORT.md':en,
 'docs/FIX_HISTORY.md':en,
 'docs/CHARACTER_STORY_PIPELINE_20261027.md':'2026-10-28：同一场景的顺序镜头可通过受控本地流程指定前一视频的已检查实际尾帧，服务端重新核验人物、场景、帧内容、来源哈希和审核记录；关键帧入口保持不变。真实15秒有声续篇与限制见[本轮验收](CHARACTER_STORY_15S_20261028.md)。'
}
for name,message in entries.items():
    path=ROOT/name;content=path.read_text(encoding='utf-8-sig')
    if MARKER not in content:
        with path.open('a',encoding='utf-8',newline='') as stream:stream.write('\n\n'+MARKER+'\n> '+message+'\n')
    print(name+': recorded')
