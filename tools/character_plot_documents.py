"""Append this run's bounded status without rewriting shared project archives."""
from pathlib import Path
from character_plot_preview import ROOT


MARKER='<!-- character-plot-preview-20261027 -->'
entries={
 '项目状态.md':'2026-10-27：《窗边等候》单人剧情新试片已由关键帧1554、H3视频1555和静音预览1556实际生成。技术及浏览器播放通过；人物身份细节和最终内容待用户审核，发布Blocked。旧版已审近照36仅用于单人近景，双人场景继续待审。详见[本轮记录](docs/CHARACTER_PLOT_PREVIEW_20261027.md)。',
 '变更记录.md':'2026-10-27：剧情分镜新增显式旧版已审正面近景选择与关键帧仅使用起始状态选项；旧计划保持原有提示词。同镜头启用该选项后跨计划共用修复预算，并串行化提交。新增真实送审播放页及本地验收控制器；[任务与验证](docs/CHARACTER_PLOT_PREVIEW_20261027.md)。',
 '待办事项.md':'2026-10-27：《窗边等候》本地视频及技术检查已完成；[播放和验收记录](docs/CHARACTER_PLOT_PREVIEW_20261027.md)。待用户确认人物、侧脸和表情自然度；发布资格保持Blocked。九图被拒素材及此前双人场景保持待审，不因本次单人视频通过而自动改变。',
 'docs/CHARACTER_STORY_PIPELINE_20261027.md':'2026-10-27：增加显式选择已审核旧版正面近照的单人近景路线和“关键帧只呈现人物起始状态”选项。缺失全身参考不由近照替代；后续动作只传给视频，旧计划不改写；该镜头跨计划限制两次定向修复。实际任务及边界见[《窗边等候》试片](CHARACTER_PLOT_PREVIEW_20261027.md)。'
}
for relative,content in entries.items():
    path=ROOT/relative
    existing=path.read_text(encoding='utf-8-sig')
    if MARKER not in existing:
        with path.open('a',encoding='utf-8',newline='') as stream:stream.write('\n\n'+MARKER+'\n> '+content+'\n')
    print(relative+': recorded')
