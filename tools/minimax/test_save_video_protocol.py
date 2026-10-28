"""CPU-only SaveVideo V3 protocol/1080p/audio fixture; never a user sample or GPU task."""
import json
from pathlib import Path
import subprocess
import sys
from fractions import Fraction
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[2]
COMFY = ROOT.parent / 'ComfyUI'

def main():
    sys.path.insert(0, str(COMFY))

    sys.argv = [sys.argv[0], '--cpu']
    import torch
    import folder_paths
    from comfy_extras.nodes_video import SaveVideo
    from comfy_api.latest import _io, InputImpl, Types

    workflow = json.loads((ROOT / 'tools/minimax/minimax_h3_local_1088_i2v_api.json').read_text(encoding='utf-8'))
    inputs = workflow['15']['inputs'].copy()
    final, _, data = _io.get_finalized_class_inputs(SaveVideo.INPUT_TYPES(), inputs)
    valid = {k: v for k, v in inputs.items() if k in final['required'] or k in final['optional']}
    nested = _io.build_nested_inputs(valid, data)
    assert nested['codec'] == {'codec': 'h264', 'encoding': {'encoding': 're-encode', 'crf': 16.0}}
    bad = inputs | {'codec': {'codec': 'h264', 'encoding': {'encoding': 're-encode', 'crf': 16.0}}}
    bad_final, _, _ = _io.get_finalized_class_inputs(SaveVideo.INPUT_TYPES(), bad)
    assert 'codec' not in bad_final['required']  # Reproduce why the first API graph failed only at execution.
    output = ROOT.parent / 'Data/acceptance' / ('native1080_codec_' + uuid.uuid4().hex)
    output.mkdir()
    folder_paths.set_output_directory(str(output))
    SaveVideo.hidden = SimpleNamespace(prompt=None, extra_pnginfo=None)
    # Expanded CPU view keeps fixture memory small. It is deliberately a static test pattern.
    images = torch.rand((1, 1080, 1920, 3), generator=torch.Generator().manual_seed(42)).expand(124, -1, -1, -1)
    audio = {'waveform': torch.zeros((1, 2, 248000)), 'sample_rate': 48000}
    video = InputImpl.VideoFromComponents(Types.VideoComponents(images=images, audio=audio, frame_rate=Fraction(24)))
    SaveVideo.execute(video, filename_prefix='cpu_protocol_fixture', format='mp4', codec=nested['codec'])
    files = list(output.rglob('*.mp4'))
    assert len(files) == 1 and files[0].stat().st_size > 0
    probe = json.loads(subprocess.run([r'C:\install\FFmpeg\bin\ffprobe.exe', '-v', 'error', '-count_frames',
        '-show_streams', '-show_format', '-of', 'json', str(files[0])], capture_output=True, text=True, check=True, timeout=90).stdout)
    stream = next(x for x in probe['streams'] if x['codec_type'] == 'video')
    assert (stream['width'], stream['height'], int(stream['nb_read_frames']), stream['avg_frame_rate']) == (1920, 1080, 124, '24/1')
    assert any(x['codec_type'] == 'audio' for x in probe['streams'])
    result = {'status': 'Passed', 'device': 'CPU', 'realGpuTask': False, 'nestedCodec': nested['codec'],
              'fixturePath': str(files[0]), 'probe': probe, 'workflowSaveInputs': inputs,
              'reproducedNestedObjectFailure': True}
    report = ROOT.parent / 'Data/H3Native108020261019/codec-protocol-check.json'
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'Passed', 'device': 'CPU', 'geometry': '1920x1080', 'frames': 124, 'fps': 24,
                      'audio': True, 'fixture': str(files[0])}))


if __name__ == "__main__":
    main()
