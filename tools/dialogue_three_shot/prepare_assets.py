"""Freeze three reference crops and their local model/workflow contracts."""
import hashlib
import json
from pathlib import Path
from PIL import Image
from build_workflows import prepare

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT.parent
DATA = AI / 'Data'
FOLDER = DATA / 'DialogueThreeShot20261023'
SOURCE = DATA / 'Artifacts/project-32/image/task-1216/v0001/v0001_task_1216_task_1216_attempt_1_20013b81_00001__0a56bd1c7561.png'
EXPECTED = '0a56bd1c7561197a234c04b28e95d7f04ae6789fc6fc25f77fb0fab8a23fc066'


def main():
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != EXPECTED:
        raise RuntimeError('Original character reference changed')
    image = Image.open(SOURCE)
    boxes = [(160, 0, 688, 305), (640, 0, 1168, 305), (160, 0, 1344, 684)]
    for index, box in enumerate(boxes, 1):
        reference = image.crop(box).resize((832, 480), Image.Resampling.LANCZOS)
        target = FOLDER / f'reference-{index}.png'
        if target.exists():
            if Image.open(target).tobytes() != reference.tobytes():
                raise RuntimeError('Existing reference differs; version before changing it')
        else:
            reference.save(target)
    plan = prepare()
    target = FOLDER / 'workflow-plan.json'
    encoded = json.dumps(plan, ensure_ascii=False, indent=2)
    if target.exists() and target.read_text(encoding='utf-8') != encoded:
        raise RuntimeError('Existing workflow plan differs; preserve it')
    if not target.exists():
        target.write_text(encoded, encoding='utf-8')
    print(encoded, flush=True)


if __name__ == '__main__':
    main()
