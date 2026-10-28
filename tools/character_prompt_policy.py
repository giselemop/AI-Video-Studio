"""The same versioned reference prompt policy used by the .NET workbench."""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / 'config/character-reference-prompts.json').read_text(encoding='utf-8-sig'))
SLOTS = [('front','closeUp'),('threeQuarterLeft','closeUp'),('threeQuarterRight','closeUp'),('front','fullBody'),('threeQuarterLeft','fullBody'),('left','fullBody'),('back','fullBody'),('right','fullBody'),('threeQuarterRight','fullBody')]

def compose(view, framing, reference_count, identity='', outfit='', body=''):
    if (view, framing) not in SLOTS or reference_count not in (0,1,2):
        raise ValueError('Invalid reference view, framing or reference count')
    parts = [POLICY['subject'], POLICY['directions'][view], POLICY['references'][reference_count], 'Identity traits: ' + identity,
             POLICY['face'], POLICY['head'], POLICY[framing]]
    parts += ['Body proportions: ' + body, 'Complete wardrobe: ' + outfit] if framing == 'fullBody' else ['Visible collar and upper garment only: ' + re.split('[,，、;；]',outfit)[0]]
    return ' '.join(parts + [POLICY['finish']])
