"""CPU-only native-window padding and a quiet procedural indoor response.

No API calls, model inference, downloads, independent room noise or Foley.
The synthetic response is a finishing experiment, not a recorded room IR.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT.parent / "Data"
FOLDER = DATA / "DialogueThreeShot20261023" / "audio"
RATE = 24000
ROOM_PARAMETERS = dict(
    kind="Procedural synthetic mono indoor impulse response; not a recorded ambience or measured room",
    seed=2026102306, sampleRate=RATE, durationSeconds=.32, preDelaySeconds=.010,
    approximateDecayT60Seconds=.24, wetGain=.045, earlyL1Weight=.65, diffuseL1Weight=.35,
    diffuseStartSeconds=.032, diffuseLowpassMovingAverageSamples=7,
    earlyReflections=[dict(delaySeconds=t, relativeGain=g) for t, g in
                      ((.013, .35), (.023, .22), (.037, .16), (.057, .10),
                       (.083, .07), (.113, .045), (.149, .03), (.193, .015), (.227, .01))],
    independentRoomTone=False, foley=False,
)


def sha(path: Path):
    path = path.resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(DATA.resolve()):
        raise RuntimeError("Controlled audio paths must stay under Data")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_audio(path: Path, expected_hash=None):
    digest = sha(path)
    if expected_hash is not None and digest != expected_hash:
        raise RuntimeError("Prepared audio SHA changed: " + str(path))
    audio, rate = sf.read(path, dtype="float32")
    if rate != RATE or audio.ndim != 1 or not len(audio) or not np.all(np.isfinite(audio)):
        raise RuntimeError("Expected finite mono 24kHz audio: " + str(path))
    return audio, digest


def save_audio(path: Path, audio):
    temporary = path.with_name(path.stem + ".verified-part.wav")
    sf.write(temporary, audio, RATE, subtype="PCM_24")
    expected = sha(temporary)
    if path.exists():
        if sha(path) != expected:
            temporary.unlink()
            raise RuntimeError("Existing finishing output differs; preserve and version it: " + str(path))
        temporary.unlink()
    else:
        temporary.replace(path)
    return expected


def save_report(path: Path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise RuntimeError("Existing audio finishing report differs; preserve and version it")
        return
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def measure(path):
    result = subprocess.run([
        "C:/install/FFmpeg/bin/ffmpeg.exe", "-hide_banner", "-nostats", "-i", str(path),
        "-af", "loudnorm=I=-23:TP=-2:LRA=7:print_format=json", "-f", "null", "-"],
        capture_output=True, encoding="utf-8", check=True)
    start = result.stderr.rfind("{\n")
    if start < 0:
        raise RuntimeError("FFmpeg returned no perceptual loudness measurement")
    raw = json.JSONDecoder().raw_decode(result.stderr[start:])[0]
    return dict(integratedLufs=float(raw["input_i"]), truePeakDbTP=float(raw["input_tp"]),
                loudnessRangeLu=float(raw["input_lra"]), thresholdLufs=float(raw["input_thresh"]),
                engine="FFmpeg loudnorm EBU-R128 input measurement; analysis only")


def room_ir():
    count = round(ROOM_PARAMETERS["durationSeconds"] * RATE)
    early = np.zeros(count, np.float64)
    for reflection in ROOM_PARAMETERS["earlyReflections"]:
        early[round(reflection["delaySeconds"] * RATE)] += reflection["relativeGain"]
    early /= np.sum(np.abs(early))
    random = np.random.default_rng(ROOM_PARAMETERS["seed"]).standard_normal(count)
    diffuse = np.convolve(random, np.ones(7) / 7, mode="same")
    times = np.arange(count) / RATE
    diffuse *= np.exp(-math.log(1000) * times / ROOM_PARAMETERS["approximateDecayT60Seconds"])
    diffuse[times < ROOM_PARAMETERS["diffuseStartSeconds"]] = 0
    diffuse *= np.minimum(1, np.maximum(0, (times - ROOM_PARAMETERS["diffuseStartSeconds"]) / .015))
    diffuse /= np.sum(np.abs(diffuse))
    impulse = early * ROOM_PARAMETERS["earlyL1Weight"] + diffuse * ROOM_PARAMETERS["diffuseL1Weight"]
    return impulse / np.sum(np.abs(impulse))


def fft_convolve(source, impulse):
    size = len(source) + len(impulse) - 1
    length = 1 << (size - 1).bit_length()
    result = np.fft.irfft(np.fft.rfft(source, length) * np.fft.rfft(impulse, length), length)
    return result[:size]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify existing outputs without rewriting")
    args = parser.parse_args()
    report_path = FOLDER / "room-mix.json"
    if args.check:
        existing = json.loads(report_path.read_text(encoding="utf-8"))
        for path, digest in existing["outputHashes"].items():
            if sha(DATA / path) != digest:
                raise RuntimeError("Finishing artifact changed: " + path)
        for path, digest in existing["inputHashes"].items():
            if sha(DATA / path) != digest:
                raise RuntimeError("Prepared input changed: " + path)
        print(json.dumps(dict(status="Passed", newTasksSubmitted=False, outputCount=len(existing["outputHashes"]))))
        return
    state = json.loads((FOLDER / "run.json").read_text(encoding="utf-8"))
    if state.get("stage") != "AudioPrepared":
        raise RuntimeError("Run the explicit audio prepare stage first")
    timeline = json.loads((FOLDER / "timeline.json").read_text(encoding="utf-8"))
    shots = json.loads((FOLDER / "shot-definitions.json").read_text(encoding="utf-8"))
    if len(timeline) != 4 or len(shots) != 3 or state.get("durationSeconds") != 10:
        raise RuntimeError("Expected frozen four-line, three-shot, ten-second plan")
    input_hashes, output_hashes, native = {}, {}, []
    for name in ("timeline.json", "shot-definitions.json", "preparation.json"):
        path = FOLDER / name
        input_hashes[path.relative_to(DATA).as_posix()] = sha(path)
    for shot in shots:
        duration = shot["durationSeconds"]
        frames = math.ceil(duration * 25 - 1e-9) + 1
        samples = round(frames / 25 * RATE)
        item = dict(index=shot["index"], finalDurationSeconds=duration, nativeFrames=frames,
                    nativeFps=25, nativeDurationSeconds=frames / 25, tracks={})
        for role in ("female", "male"):
            path = DATA / shot[role + "Audio"]
            relative = path.relative_to(DATA).as_posix()
            if relative not in state["outputHashes"]:
                raise RuntimeError("Shot audio missing from the prepared manifest")
            audio, digest = load_audio(path, state["outputHashes"][relative])
            input_hashes[relative] = digest
            if len(audio) != round(duration * RATE) or len(audio) > samples:
                raise RuntimeError("Native padding would truncate or alter a shot")
            padded = np.pad(audio, (0, samples - len(audio)))
            target = FOLDER / f"shot-{shot['index']}-{role}-native.wav"
            target_sha = save_audio(target, padded)
            actual, _ = load_audio(target, target_sha)
            if not np.array_equal(actual[:len(audio)], audio) or np.any(actual[len(audio):]):
                raise RuntimeError("Native window speech changed or nonzero padding appeared")
            target_relative = target.relative_to(DATA).as_posix()
            output_hashes[target_relative] = target_sha
            item["tracks"][role] = dict(path=target_relative, sha256=target_sha,
                                       sourceSamples=len(audio), outputSamples=samples,
                                       zeroPaddingSamples=samples - len(audio), sourceInteriorSamplesUnchanged=True)
        native.append(item)
    source_path = FOLDER / "dialogue-balanced-10s.wav"
    source_relative = source_path.relative_to(DATA).as_posix()
    source, source_sha = load_audio(source_path, state["outputHashes"][source_relative])
    if len(source) != 10 * RATE:
        raise RuntimeError("Balanced dialogue is not exactly ten seconds")
    input_hashes[source_relative] = source_sha
    impulse = room_ir()
    ir_path = FOLDER / "procedural-room-ir.wav"
    ir_sha = save_audio(ir_path, impulse)
    output_hashes[ir_path.relative_to(DATA).as_posix()] = ir_sha
    wet = fft_convolve(source.astype(np.float64), impulse)
    mix = source.astype(np.float64) + ROOM_PARAMETERS["wetGain"] * wet[:len(source)]
    discarded_tail = wet[len(source):] * ROOM_PARAMETERS["wetGain"]
    discarded_tail_max = float(np.max(np.abs(discarded_tail))) if len(discarded_tail) else 0
    if discarded_tail_max > 10 ** (-70 / 20):
        raise RuntimeError("Audible room tail would exceed ten seconds; shorten synthetic response before continuing")
    peak = float(np.max(np.abs(mix)))
    global_gain = min(1., .94 / peak) if peak else 1.
    mix *= global_gain
    output_path = FOLDER / "dialogue-room-10s.wav"
    mix_sha = save_audio(output_path, mix)
    output_hashes[output_path.relative_to(DATA).as_posix()] = mix_sha
    delivered, _ = load_audio(output_path, mix_sha)
    report = dict(status="Passed", scope="Deterministic audio padding, mixing and technical measurements only",
                  contentStatus="NeedReview", roomDescription=ROOM_PARAMETERS["kind"],
                  durationSeconds=len(delivered) / RATE, sampleRate=RATE, channels=1,
                  sourcePath=source_relative, sourceSha256=source_sha, mixPath=output_path.relative_to(DATA).as_posix(),
                  mixSha256=mix_sha, pitchChange=0, tempo=1, sourceTimelineUnchanged=True,
                  proceduralIRParameters=ROOM_PARAMETERS, proceduralIRSha256=ir_sha,
                  impulseL1Norm=float(np.sum(np.abs(impulse))), globalOutputGain=global_gain,
                  discardedRoomTailMaxAbs=discarded_tail_max,
                  finalSamplePeak=float(np.max(np.abs(delivered))),
                  sourceLoudness=measure(source_path), finalLoudness=measure(output_path),
                  nativePadding=native, inputHashes=input_hashes, outputHashes=output_hashes)
    save_report(report_path, report)
    print(json.dumps(dict(status=report["status"], mixPath=report["mixPath"], mixSha256=mix_sha,
                          nativePadding=native, finalLoudness=report["finalLoudness"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
