"""Bounded project handoff entries; never changes historical evidence blocks."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FOLDER=ROOT.parent/'Data/DialoguePilot20261023'
START='<!-- dialogue-pilot-20261023:start -->'
END='<!-- dialogue-pilot-20261023:end -->'

def update(summary):
    for name in ['项目状态.md','待办事项.md','变更记录.md','PROJECT_STATE.md','NEXT_STAGE.md','CHANGELOG.md','docs/ACCEPTANCE_REPORT.md','docs/FIX_HISTORY.md']:
        path=ROOT/name
        text=path.read_text(encoding='utf-8')
        link='DIALOGUE_PILOT_20261023.md' if name.startswith('docs/') else 'docs/DIALOGUE_PILOT_20261023.md'
        block=f'{START}\n> {summary} 见[本轮记录]({link})。\n{END}'
        if START in text:
            a=text.index(START);b=text.index(END,a)+len(END);text=text[:a]+block+text[b:]
        else:text=block+'\n\n'+text
        path.write_text(text,encoding='utf-8')

if __name__=='__main__':
    summary=FOLDER/'progress-summary.txt'
    if not summary.exists():raise RuntimeError('Write a verified current progress summary before synchronizing records')
    update(summary.read_text(encoding='utf-8'))
