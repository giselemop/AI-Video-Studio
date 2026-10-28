"""Extract real frames for a separate visual review. Never approves story content."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw
from run_campus_story import DATA, FOLDER

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--shot', type=int, choices=range(1, 6), required=True)
args = parser.parse_args()
state = json.loads((FOLDER/'run.json').read_text(encoding='utf-8'))
n = args.shot
if state.get(f'shot{n}TechnicalStatus') != 'Passed':
    raise RuntimeError('Only an existing technically checked shot can be extracted')
video = DATA / state[f'shot{n}VideoPath']
digest = hashlib.sha256(video.read_bytes()).hexdigest()
if digest != state[f'shot{n}VideoSha256']:
    raise RuntimeError('Actual video has changed')
folder = FOLDER / f'shot-{n:02}'
source_marker = folder/'extraction-source.json'
source = {'sourceTaskId': state[f'shot{n}TaskId'], 'sourceVideoPath': state[f'shot{n}VideoPath'], 'sourceVideoSha256': digest}
for existing in [source_marker, folder/'inspection-inputs.json']:
    if existing.exists() and json.loads(existing.read_text(encoding='utf-8')).get('sourceVideoSha256') != digest:
        raise RuntimeError('An earlier extraction belongs to another video; preserve it in its attempt folder before extracting a replacement')
source_marker.write_text(json.dumps(source, indent=2), encoding='utf-8')
reference = DATA / f'StoryReferences/project-{state["projectId"]}/shot-{n:02}'
reference.mkdir(parents=True, exist_ok=True)
frames = []
for index in (0, 24, 60, 96, 123):
    output = reference/'ending.png' if index == 123 else folder/f'frame-{index:03}.png'
    if not output.exists():
        subprocess.run([r'C:\install\FFmpeg\bin\ffmpeg.exe', '-v', 'error', '-i', str(video),
            '-vf', f'select=eq(n\\,{index})', '-frames:v', '1', '-n', str(output)], check=True)
    with Image.open(output) as image:
        image.load()
        if image.size != (state['outputWidth'], state['outputHeight']):
            raise RuntimeError('Extracted frame dimensions differ from native1080 plan')
        thumb = image.convert('RGB')
        thumb.thumbnail((640, 360))
        frames.append((index, output, thumb))
contact = Image.new('RGB', (1280, 3*390), '#10141c')
draw = ImageDraw.Draw(contact)
for i, (index, output, thumb) in enumerate(frames):
    x, y = (i%2)*640, (i//2)*390
    contact.paste(thumb, (x, y+25))
    draw.text((x+8,y+5), f'Shot {n} / frame {index} / {index/24:.3f}s', fill='white')
contact.save(folder/'contact.jpg', quality=95)
manifest = {'status': 'AwaitingVisualInspection', 'shot': n, 'sourceTaskId': state[f'shot{n}TaskId'],
    'sourceVideoPath': state[f'shot{n}VideoPath'], 'sourceVideoSha256': digest,
    'lastFrameIndex': 123, 'lastFrameTimeSeconds': 123/24,
    'lastFramePath': frames[-1][1].relative_to(DATA).as_posix(),
    'lastFrameSha256': hashlib.sha256(frames[-1][1].read_bytes()).hexdigest(),
    'frames': [{'index': index, 'path': str(path)} for index, path, _ in frames],
    'contactPath': str(folder/'contact.jpg'), 'contentStatus': 'NeedReview', 'publicationStatus': 'Blocked'}
(folder/'inspection-inputs.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps(manifest))
