"""Offline SeedVR2 worker. Invoked only by GenerationQueue under its GPU lease."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


class TeeStream:
    """Keep an inspectable live log while the queue still captures the full child log."""
    def __init__(self, original, live):
        self.original, self.live = original, live

    def write(self, value):
        result = self.original.write(value)
        self.live.write(value)
        self.live.flush()
        return result

    def flush(self):
        self.original.flush()
        self.live.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def controlled(path, root, existing=True):
    resolved = Path(path).resolve(strict=existing)
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError('Media path must be inside central Data')
    if existing and not resolved.is_file():
        raise ValueError('Input must be a regular file')
    return resolved


def run(args):
    return subprocess.check_output([str(a) for a in args], encoding='utf-8', stderr=subprocess.STDOUT)


def probe(binary, path):
    data = json.loads(run([binary, '-v', 'error', '-show_streams', '-of', 'json', path]))
    return next(s for s in data['streams'] if s['codec_type'] == 'video')


def output_spec(job, width, height):
    profile = job.get('outputProfile', 'source')
    target = (job.get('outputWidth', width), job.get('outputHeight', height))
    if any(type(value) is not int for value in target):
        raise ValueError('Output dimensions must be integers')
    if profile == 'source' and target == (width, height):
        return *target, profile
    if profile == 'qhd1440' and target == (2560, 1440) and width * 9 == height * 16:
        return *target, profile
    raise ValueError('Only source geometry or explicit 2560x1440 16:9 upscale is supported')


def streaming_chunk(config, profile):
    value = config.get('qhdChunkSize', 0) if profile == 'qhd1440' else 0
    if type(value) is not int or value < 0 or value > 65 or value and (value < 5 or value % 4 != 1):
        raise ValueError('QHD streaming chunk must be 0 or 4n+1 frames from 5 to 65')
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    config = json.loads(Path(parser.parse_args().config).read_text(encoding='utf-8'))
    job = json.load(sys.stdin)
    root = Path(job['dataRoot']).resolve(strict=True)
    source = controlled(job['source'], root)
    output = controlled(job['output'], root, existing=False)
    if output.exists() or source == output:
        raise ValueError('Existing output is preserved')
    if sha(source) != job['sourceSha256']:
        raise ValueError('Source digest changed')
    strength = job['strength']
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength) or not .25 <= strength <= 1:
        raise ValueError('Invalid restoration strength')
    video = probe(job['ffprobe'], source)
    width, height, count = video['width'], video['height'], int(video['nb_frames'])
    if width > 1920 or height > 1080 or video['avg_frame_rate'] != '24/1' or not 1 <= count <= 240:
        raise ValueError('Restoration preview requires <=1080p, 24 FPS and <=240 frames')
    output_width, output_height, output_profile = output_spec(job, width, height)
    # Five frames bound the 1440p activation footprint; overlap stays at three.
    batch_size = min(config['batchSize'], 5) if output_profile == 'qhd1440' else config['batchSize']
    chunk_size = streaming_chunk(config, output_profile)
    cuts = job['cutFrames']
    if not isinstance(cuts, list) or len(cuts) > 8 or any(type(i) is not int or not 0 < i < count for i in cuts) or sorted(set(cuts)) != cuts:
        raise ValueError('Invalid shot boundaries')
    engine = Path(config['engineDirectory']).resolve(strict=True)
    if run(['git', '-C', engine, 'rev-parse', 'HEAD']).strip() != config['engineRevision']:
        raise ValueError('Engine revision changed')
    subprocess.run(['git', '-C', str(engine), 'diff', '--quiet', 'HEAD'], check=True)
    models = Path(config['modelDirectory']).resolve(strict=True)
    for model in config['files']:
        file = (models / model['file']).resolve(strict=True)
        if not file.is_relative_to(models) or file.stat().st_size != model['size'] or sha(file) != model['sha256']:
            raise ValueError('Pinned model digest mismatch')
    output.parent.mkdir(parents=True, exist_ok=True)
    live_log = output.with_name(output.name + '.live.log')
    live = live_log.open('x', encoding='utf-8', buffering=1)
    sys.stdout, sys.stderr = TeeStream(sys.stdout, live), TeeStream(sys.stderr, live)
    work = output.with_suffix('.frames')
    work.mkdir(exist_ok=False)
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    sys.path.insert(0, str(engine))
    sys.argv = [str(engine / 'inference_cli.py'), str(source), '--output_format', 'png',
        '--model_dir', str(models), '--dit_model', config['files'][0]['file'],
        '--resolution', str(min(output_width, output_height)), '--max_resolution', str(max(output_width, output_height)),
        '--batch_size', str(batch_size), '--uniform_batch_size',
        '--temporal_overlap', str(config['temporalOverlap']), '--seed', '20261022',
        '--dit_offload_device', 'cpu', '--vae_offload_device', 'cpu', '--tensor_offload_device', 'cpu',
        '--blocks_to_swap', str(config['blocksToSwap']), '--swap_io_components',
        '--vae_encode_tiled', '--vae_decode_tiled',
        '--vae_encode_tile_size', str(config['tileSize']), '--vae_decode_tile_size', str(config['tileSize']),
        '--vae_encode_tile_overlap', str(config['tileOverlap']), '--vae_decode_tile_overlap', str(config['tileOverlap']),
        '--color_correction', 'lab', '--attention_mode', 'sdpa', '--cache_dit', '--cache_vae']
    if chunk_size:
        sys.argv += ['--chunk_size', str(chunk_size)]
    import inference_cli as cli
    # The official CLI's main() downloads weights. This worker uses only verified local weights.
    cli.download_weight = lambda **kwargs: True
    args = cli.parse_arguments()
    if not cli.torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable')
    cli.torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    boundaries = [0, *cuts, count]
    all_frames = []
    cache = {}
    segments = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        target = work / f'shot-{index:02}'
        args.skip_first_frames, args.load_cap = start, end - start
        print(json.dumps({'stage':'RestoringShot','start':start,'frames':end-start}), flush=True)
        written = cli.process_single_file(str(source), args, ['0'], str(target), runner_cache=cache)
        frames = sorted(target.rglob('*.png'))
        if written != end-start or len(frames) != written:
            raise RuntimeError('Restoration returned an unexpected frame count')
        for frame in frames:
            image = cli.cv2.imread(str(frame))
            if image is None or image.shape[:2] != (output_height, output_width):
                raise RuntimeError('Restoration changed the requested image dimensions')
        segments.append({'startFrame':start,'frames':written})
        all_frames.extend(frames)
    sequence = work / 'sequence'
    sequence.mkdir()
    for index, frame in enumerate(all_frames):
        os.link(frame, sequence / f'frame_{index:06}.png')
    temporary = output.with_name(output.stem + '.encoding.mp4')
    command = [job['ffmpeg'], '-hide_banner', '-loglevel', 'error', '-n', '-framerate', '24',
        '-i', str(sequence / 'frame_%06d.png'), '-i', str(source)]
    if strength < 1:
        command += ['-filter_complex', f'[0:v]format=gbrp,setpts=PTS-STARTPTS[a];[1:v]scale={output_width}:{output_height}:flags=lanczos,format=gbrp,setpts=PTS-STARTPTS[b];[a][b]blend=all_expr=A*{strength}+B*{1-strength}[v]', '-map', '[v]']
    else:
        command += ['-map', '0:v:0']
    command += ['-an', '-c:v', 'libx264', '-crf', '16', '-preset', 'medium', '-pix_fmt', 'yuv420p',
        '-frames:v', str(count), '-t', str(count/24), '-movflags', '+faststart', str(temporary)]
    print(json.dumps({'stage':'Encoding','frames':count,'strength':strength}), flush=True)
    subprocess.run(command, check=True)
    actual = probe(job['ffprobe'], temporary)
    if (actual['width'], actual['height'], actual['avg_frame_rate'], int(actual['nb_frames'])) != (output_width, output_height, '24/1', count):
        raise RuntimeError('Encoded output did not preserve dimensions, rate or frame count')
    muxed = output.with_name(output.stem + '.muxing.mp4')
    subprocess.run([job['ffmpeg'], '-v', 'error', '-n', '-i', str(temporary), '-i', str(source),
        '-map', '0:v:0', '-map', '1:a?', '-c', 'copy', '-movflags', '+faststart', str(muxed)], check=True)
    def audio_digest(path):
        data = subprocess.check_output([job['ffmpeg'], '-v', 'error', '-i', str(path), '-map', '0:a:0', '-c:a', 'copy', '-f', 'adts', '-'])
        return hashlib.sha256(data).hexdigest()
    has_audio = any(s['codec_type'] == 'audio' for s in json.loads(run([job['ffprobe'], '-v', 'error', '-show_streams', '-of', 'json', source]))['streams'])
    if has_audio and audio_digest(source) != audio_digest(muxed):
        raise RuntimeError('Audio packet preservation failed after video encoding')
    subprocess.run([job['ffmpeg'], '-v', 'error', '-i', str(muxed), '-f', 'null', '-'], check=True)
    if sha(source) != job['sourceSha256']:
        raise RuntimeError('Source changed during inference')
    receipt = dict(schemaVersion=1, engine='SeedVR2-3B-FP8', engineRevision=config['engineRevision'],
        modelRepository=config['repository'], modelRevision=config['revision'], modelFiles=config['files'],
        sourceSha256=job['sourceSha256'], width=output_width, height=output_height, fps=24, frames=count,
        sourceWidth=width, sourceHeight=height, outputProfile=output_profile,
        strength=strength, segments=segments, batchSize=batch_size, temporalOverlap=config['temporalOverlap'],
        chunkSize=chunk_size, streamingContextFrames=config['temporalOverlap'] if chunk_size else 0,
        liveLog=str(live_log.relative_to(root)),
        seconds=time.monotonic()-started, peakAllocatedMiB=cli.torch.cuda.max_memory_allocated()/1024**2,
        peakReservedMiB=cli.torch.cuda.max_memory_reserved()/1024**2, videoEncodingPasses=1,
        audio='complete source stream copy after video encoding', contentStatus='NeedReview', publicationStatus='Blocked')
    output.with_name(output.name + '.seedvr.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    muxed.rename(output)
    print(json.dumps({'stage':'Passed','output':str(output),'seconds':receipt['seconds']}), flush=True)


if __name__ == '__main__':
    main()
