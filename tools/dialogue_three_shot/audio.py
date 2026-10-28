"""Local queued dialogue, followed by deterministic timing and a CPU-only audit.

GPU inference is submitted only by the explicit ``generate`` stage. Existing
task IDs and uncertain submissions are never discarded or silently resubmitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
AI = ROOT.parent
DATA = AI / "Data"
FOLDER = DATA / "DialogueThreeShot20261023" / "audio"
sys.path.insert(0, str(ROOT / "tools" / "minimax"))
from run_local_acceptance import Acceptance, TaskFailure
from download_assets import download_lock

SAMPLE_RATE = 24000
DURATION = 10.0
GAPS = (.22, .34, .20)
LINES = [
    dict(role="female", text="哟，约会回来了？", voice="qwen3:Vivian",
         instruction="成年年轻女性，熟人间含笑打趣的自然口语。‘哟’轻轻一带就接后半句，不拖长、不停顿卖关子；重音轻落在‘约会’，尾音自然上扬。带一点好奇和忍笑，语速正常，亲近、不做作。只说给定台词，不加词，不另发笑声。"),
    dict(role="male", text="哼，要你管。", voice="qwen3:Dylan",
         instruction="成年年轻男性，听到熟人的打趣后，马上半笑着佯装不服。‘哼’是很轻很短的鼻音，紧接‘要你管’，不拉长、不刻意顿开；后半句语气轻松，尾音收住，能听出是玩笑，正常口语速度，不真生气、不喊。只说给定台词，不加词。"),
    dict(role="female", text="好啦，不逗你了。", voice="qwen3:Vivian",
         instruction="同一位成年年轻女性，看出对方假装不服，带一点笑意自然让步。‘好啦’轻巧温柔，直接接‘不逗你了’，中间仅短暂自然换气，不拖长、不作朗诵停顿。尾音柔和，声音比刚才稍轻，语速自然。只说给定台词，不加词，不另发笑声。"),
    dict(role="male", text="这还差不多。", voice="qwen3:Dylan",
         instruction="同一位成年年轻男性，听见对方让步，忍住笑、轻松满意地接话。像对熟人随口回答，嘴角有笑意，‘这还’连贯，‘差不多’轻轻收尾，正常口语速度，不摆架子、不夸张、不喊。只说给定台词，不加词，不另发笑声。"),
]

REPAIR_INSTRUCTIONS = {
    1: {
        2: "年轻女性含笑打趣熟人，轻快连贯，哟后马上接下一词，整句话一口气自然说完。",
        3: "年轻女性自然口语，轻轻笑着问一句，节奏紧凑，约会两字清晰，结尾轻微上扬。",
    },
    2: {
        2: "年轻男性带笑地佯装不服，短促轻声，哼后马上接话，说到管字立即收住。",
        3: "年轻男性随口逗熟人，轻哼一声连着说完，管字收尾，简短利落。",
    },
    3: {
        2: "年轻女性含笑温柔让步，整句话连贯轻巧，好啦后仅短停，结尾了字自然收住。",
        3: "年轻女性轻声哄熟人，轻快地一口气说完好啦不逗你了，声音自然温柔。",
    },
}


def selected_line(run, index):
    attempt = run.state.get(f"selectedLine{index}Attempt", 1)
    prefix = f"line{index}" if attempt == 1 else f"line{index}Attempt{attempt}"
    return dict(attempt=attempt, taskId=run.state[prefix + "TaskId"],
                path=run.state[prefix + "Path"], sha256=run.state[prefix + "Sha256"],
                duration=run.state[prefix + "Duration"],
                instruction=run.state[prefix + "TaskIdInput"]["instruction"])


def preserve_copy(source, target):
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if source.read_bytes() != target.read_bytes():
            raise RuntimeError("Existing attempt evidence differs; preserve it: " + str(target))
    else:
        shutil.copy2(source, target)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def sha(path: Path) -> str:
    path = path.resolve(strict=True)
    if not path.is_relative_to(DATA.resolve()) or not path.is_file():
        raise RuntimeError("Audio must remain within Data")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class AudioRun(Acceptance):
    def poll(self, task_id, limit=1800):
        start = time.monotonic()
        while time.monotonic() - start < limit:
            detail = self.api(f"/api/tasks/{task_id}")
            status = detail["task"]["status"]
            import psutil
            sample = dict(epoch=time.time(), taskId=task_id, status=status,
                          availableRamMiB=psutil.virtual_memory().available // 1024**2)
            try:
                values = subprocess.check_output([
                    "nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu",
                    "--format=csv,noheader,nounits"], encoding="utf-8", timeout=10)
                sample["gpu"] = [int(v.strip()) for v in values.strip().split(",")]
            except (OSError, subprocess.SubprocessError):
                pass
            with (FOLDER / "resources.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(sample) + "\n")
            if status == "Succeeded":
                return detail
            if status in {"Failed", "Cancelled"}:
                raise TaskFailure(task_id, status, str(detail["task"].get("errorMessage"))[:1000])
            time.sleep(3)
        raise RuntimeError("Recorded audio task is unresolved; no replacement submitted")


def generate(run: AudioRun, project_id: int):
    if run.state.get("projectId") not in (None, project_id):
        raise RuntimeError("Existing project is frozen")
    if run.state.get("stage") == "AudioPrepared":
        check(run)
        return
    run.access()
    run.save("GeneratingDialogue", projectId=project_id)
    for index, line in enumerate(LINES, 1):
        field = f"line{index}TaskId"
        body = dict(projectId=project_id, voiceId=line["voice"], text=line["text"],
                    instruction=line["instruction"], speed=1, pitch=0,
                    outputName=f"three_shot_{index:02}_{line['role']}.wav")
        if run.state.get(field + "Input") not in (None, body):
            raise RuntimeError("Frozen TTS instruction changed; preserve and version the attempt")
        if not run.state.get(field):
            if run.state.get(field + "SubmissionStarted"):
                raise RuntimeError(f"Uncertain submission for {field}; inspect the queue")
            run.save(**{field + "Input": body, field + "SubmissionStarted": True})
            response = run.api("/api/audio/tts", body, key=field, timeout=180)
            task_id = response.get("taskId") or response.get("id")
            if not isinstance(task_id, int) or task_id <= 0:
                raise RuntimeError("Submission returned no valid task ID; inspect the queue")
            run.save(**{field: task_id})
            print(field, task_id, flush=True)
        result = run.poll(run.state[field])
        write_json(FOLDER / f"line-{index}-task.json", result)
        item = next(x for x in result["results"] if x.get("available") and x.get("assetPath", "").endswith(".wav"))
        path = item["assetPath"]
        audio, rate = sf.read(DATA / path)
        if rate != SAMPLE_RATE or audio.ndim != 1 or len(audio) == 0:
            raise RuntimeError("Unexpected local Qwen audio format")
        current_sha = sha(DATA / path)
        if run.state.get(f"line{index}Sha256") not in (None, current_sha):
            raise RuntimeError("Previously recorded TTS media changed")
        run.save(**{f"line{index}Path": path, f"line{index}Sha256": current_sha,
                    f"line{index}Duration": len(audio) / rate})
    run.save("DialogueGenerated", contentStatus="NeedReview")


def edge_padding(audio: np.ndarray):
    """Remove bounded near-silent edge padding, never a pause inside a phrase."""
    threshold = 10 ** (-55 / 20)
    active = np.flatnonzero(np.abs(audio) >= threshold)
    if not len(active):
        raise RuntimeError("TTS output contains no signal above -55dBFS")
    margin = round(.08 * SAMPLE_RATE)
    first = max(0, int(active[0]) - margin)
    last = min(len(audio), int(active[-1]) + margin + 1)
    if first > round(.5 * SAMPLE_RATE) or len(audio) - last > round(.5 * SAMPLE_RATE):
        raise RuntimeError("Excessive edge padding needs manual inspection; no automatic removal")
    return first, last


def measure(path: Path):
    command = [str(Path("C:/install/FFmpeg/bin/ffmpeg.exe")), "-hide_banner", "-nostats", "-i", str(path),
               "-af", "loudnorm=I=-23:TP=-2:LRA=7:print_format=json", "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, encoding="utf-8", check=True)
    begin = result.stderr.rfind("{\n")
    if begin < 0:
        raise RuntimeError("FFmpeg did not report loudness")
    return json.JSONDecoder().raw_decode(result.stderr[begin:])[0]


def repair(run: AudioRun, index: int, attempt: int, reason: str | None):
    if index not in REPAIR_INSTRUCTIONS or attempt not in (2, 3):
        raise RuntimeError("Only explicit second/third attempts of lines 1-3 are supported")
    previous = selected_line(run, index)
    if previous["attempt"] >= attempt:
        print(json.dumps(dict(line=index, selectedAttempt=previous["attempt"], newTasksSubmitted=False)), flush=True)
        return
    if attempt != previous["attempt"] + 1:
        raise RuntimeError("Targeted attempts must be sequential and bounded to three total")
    run.access()
    prefix = f"line{index}Attempt{attempt}"
    field = prefix + "TaskId"
    history = FOLDER / "history" / f"before-line-{index}-attempt-{attempt}"
    if not run.state.get(field + "Input"):
        preserve_copy(FOLDER / "run.json", history / "run.json")
        preserve_copy(FOLDER / "speech-audit.json", history / "speech-audit.json")
        for path in run.state.get("outputHashes", {}):
            source = DATA / path
            if not source.resolve().is_relative_to(FOLDER.resolve()):
                raise RuntimeError("Unexpected prepared output outside this audio run")
            preserve_copy(source, history / "derived" / source.relative_to(FOLDER))
        for name in ("timeline.json", "shot-definitions.json", "preparation.json", "room-mix.json"):
            preserve_copy(FOLDER / name, history / name)
    line = LINES[index - 1]
    body = dict(projectId=run.state["projectId"], voiceId=line["voice"], text=line["text"],
                instruction=REPAIR_INSTRUCTIONS[index][attempt], speed=1, pitch=0,
                outputName=f"three_shot_{index:02}_{line['role']}_attempt{attempt}.wav")
    if run.state.get(field + "Input") not in (None, body):
        raise RuntimeError("Frozen repair instruction changed")
    if not run.state.get(field):
        if run.state.get(field + "SubmissionStarted"):
            raise RuntimeError("Repair submission outcome is unresolved; inspect its recorded key")
        default_reason = "Compact delivery and transcript-ending review after initial ASR/low-level pause evidence"
        run.save("GeneratingTargetedRepair", **{field + "Input": body, field + "SubmissionStarted": True,
                 prefix + "Reason": reason or default_reason, prefix + "PreviousSelected": previous})
        response = run.api("/api/audio/tts", body, key=field, timeout=180)
        task_id = response.get("taskId") or response.get("id")
        if not isinstance(task_id, int) or task_id <= 0:
            raise RuntimeError("Repair returned no valid task ID; inspect the queue")
        run.save(**{field: task_id})
        print(field, task_id, flush=True)
    result = run.poll(run.state[field])
    write_json(FOLDER / f"line-{index}-attempt-{attempt}-task.json", result)
    item = next(x for x in result["results"] if x.get("available") and x.get("assetPath", "").endswith(".wav"))
    path = item["assetPath"]
    samples, rate = sf.read(DATA / path)
    if rate != SAMPLE_RATE or samples.ndim != 1 or not len(samples):
        raise RuntimeError("Unexpected targeted Qwen output")
    run.save("DialogueGenerated", **{prefix + "Path": path, prefix + "Sha256": sha(DATA / path),
             prefix + "Duration": len(samples) / rate, f"selectedLine{index}Attempt": attempt,
             "technicalStatus": "Blocked", "contentStatus": "NeedReview", "outputHashes": {},
             "derivedAudioInvalidatedBy": dict(line=index, attempt=attempt, taskId=run.state[field])})


def timestamp(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def prepare(run: AudioRun):
    if not all(run.state.get(f"line{i}Path") for i in range(1, 5)):
        raise RuntimeError("Generate and record all four lines before audio preparation")
    length = round(DURATION * SAMPLE_RATE)
    isolated = {role: np.zeros(length, np.float32) for role in ("female", "male")}
    balanced = {role: np.zeros(length, np.float32) for role in ("female", "male")}
    cursor = .40
    timeline, levels = [], []
    for index, line in enumerate(LINES, 1):
        selected = selected_line(run, index)
        source = DATA / selected["path"]
        if sha(source) != selected["sha256"]:
            raise RuntimeError("TTS source SHA changed")
        audio, rate = sf.read(source, dtype="float32")
        if rate != SAMPLE_RATE or audio.ndim != 1:
            raise RuntimeError("Unexpected source format")
        begin, end = edge_padding(audio)
        trimmed = audio[begin:end]
        start_sample = round(cursor * SAMPLE_RATE)
        end_sample = start_sample + len(trimmed)
        if end_sample > length - round(.45 * SAMPLE_RATE):
            raise RuntimeError("Unaltered dialogue is too long for 10 seconds; review a targeted TTS repair")
        isolated[line["role"]][start_sample:end_sample] = trimmed
        source_loudness = measure(source)
        measured_i = float(source_loudness["input_i"])
        measured_tp = float(source_loudness["input_tp"])
        if not np.isfinite(measured_i) or not np.isfinite(measured_tp):
            raise RuntimeError("Short phrase loudness measurement is unavailable")
        target = (-23.0, -23.0, -24.5, -23.5)[index - 1]
        gain_db = min(target - measured_i, -2.0 - measured_tp)
        gain = 10 ** (gain_db / 20)
        balanced[line["role"]][start_sample:end_sample] = trimmed * gain
        timeline.append(dict(index=index, **(line | {"instruction": selected["instruction"]}), taskId=selected["taskId"], attempt=selected["attempt"],
                             startSeconds=start_sample / SAMPLE_RATE, endSeconds=end_sample / SAMPLE_RATE,
                             durationSeconds=len(trimmed) / SAMPLE_RATE, sourcePath=str(source.relative_to(DATA)),
                             sourceSha256=sha(source), sourceStartSample=begin, sourceEndSample=end,
                             removedLeadingSeconds=begin / SAMPLE_RATE,
                             removedTrailingSeconds=(len(audio) - end) / SAMPLE_RATE,
                             nextResponseGapSeconds=GAPS[index - 1] if index <= 3 else None))
        levels.append(dict(index=index, sourceIntegratedLufs=measured_i, sourceTruePeakDbTP=measured_tp,
                           targetIntegratedLufs=target, appliedGainDb=gain_db,
                           measurement="FFmpeg loudnorm EBU-R128 analysis; gain only, no compression/time stretch"))
        cursor = end_sample / SAMPLE_RATE + (GAPS[index - 1] if index <= 3 else 0)
    if np.count_nonzero((isolated["female"] != 0) & (isolated["male"] != 0)):
        raise RuntimeError("Speaker tracks overlap")
    output_paths = []
    for role in isolated:
        path = FOLDER / f"{role}-10s.wav"
        sf.write(path, isolated[role], SAMPLE_RATE, subtype="PCM_24")
        output_paths.append(path)
    for name, audio in (("dialogue-dry-10s.wav", isolated["female"] + isolated["male"]),
                        ("dialogue-balanced-10s.wav", balanced["female"] + balanced["male"])):
        if np.max(np.abs(audio)) >= .999:
            raise RuntimeError("Dialogue mix would clip")
        path = FOLDER / name
        sf.write(path, audio, SAMPLE_RATE, subtype="PCM_24")
        output_paths.append(path)
    cuts = []
    for idx in (0, 1):
        end = timeline[idx]["endSeconds"]
        next_start = timeline[idx + 1]["startSeconds"]
        frame = round((end + next_start) * .5 * 24)
        if not end < frame / 24 < next_start:
            raise RuntimeError("Shot cut crosses speech")
        cuts.append(frame)
    frame_points = [0, *cuts, 240]
    shots = []
    for idx, (start, end) in enumerate(zip(frame_points[:-1], frame_points[1:]), 1):
        start_s, end_s = start / 24, end / 24
        a, b = round(start_s * SAMPLE_RATE), round(end_s * SAMPLE_RATE)
        paths = {}
        for role in isolated:
            path = FOLDER / f"shot-{idx}-{role}.wav"
            sf.write(path, isolated[role][a:b], SAMPLE_RATE, subtype="PCM_24")
            output_paths.append(path)
            paths[role + "Audio"] = str(path.relative_to(DATA)).replace("\\", "/")
        shots.append(dict(index=idx, composition=("female medium close-up", "male reverse medium close-up", "two-shot reaction and closing dialogue")[idx - 1],
                          startFrame=start, endFrameExclusive=end, finalFps=24, frames=end - start,
                          startSeconds=start_s, endSeconds=end_s, durationSeconds=end_s - start_s, **paths))
    subtitle = "\n\n".join(f"{line['index']}\n{timestamp(line['startSeconds'])} --> {timestamp(line['endSeconds'])}\n{'女' if line['role'] == 'female' else '男'}：{line['text']}" for line in timeline) + "\n"
    srt = FOLDER / "dialogue.srt"
    srt.write_text(subtitle, encoding="utf-8")
    output_paths.append(srt)
    integrity = []
    for line in timeline:
        source, _ = sf.read(DATA / line["sourcePath"], dtype="float32")
        expected = source[line["sourceStartSample"]:line["sourceEndSample"]]
        begin = round(line["startSeconds"] * SAMPLE_RATE)
        observed = isolated[line["role"]][begin:begin + len(expected)]
        if not np.array_equal(expected, observed):
            raise RuntimeError("Prepared track changed speech samples")
        integrity.append(dict(index=line["index"], missingSpeechSamples=0, sourceInteriorSamplesUnchanged=True))
    write_json(FOLDER / "timeline.json", timeline)
    write_json(FOLDER / "shot-definitions.json", shots)
    verification = dict(status="Passed", scope="Audio integrity, duration, speaker placement and level measurements only",
                        contentStatus="NeedReview", durationSeconds=DURATION, sampleRate=SAMPLE_RATE,
                        voiceTempo=1, voicePitch=0, leadSeconds=.4, finalReactionTailSeconds=DURATION - timeline[-1]["endSeconds"],
                        responseGapsSeconds=GAPS, boundaryTrim="Only outer low-level padding, -55dBFS threshold plus 80ms retained margin; no internal pause cuts",
                        levels=levels, balancedMixLoudness=measure(FOLDER / "dialogue-balanced-10s.wav"),
                        speechIntegrity=integrity,
                        outputs={str(p.relative_to(DATA)).replace("\\", "/"): sha(p) for p in output_paths})
    write_json(FOLDER / "preparation.json", verification)
    run.save("AudioPrepared", timeline=timeline, shots=shots, technicalStatus="Passed", contentStatus="NeedReview",
             outputHashes=verification["outputs"], durationSeconds=DURATION)
    print(json.dumps(dict(timeline=timeline, shots=shots), ensure_ascii=False, indent=2), flush=True)


def audit(run: AudioRun):
    model_path = AI / "Models" / "ASR" / "faster-whisper-small"
    weight = model_path / "model.bin"
    if not weight.exists():
        raise RuntimeError("Existing local ASR weights are unavailable; this stage never downloads")
    with weight.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671":
            raise RuntimeError("Existing local ASR weight SHA mismatch")
    from faster_whisper import WhisperModel
    model = WhisperModel(str(model_path), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
    lines = []
    for index, line in enumerate(LINES, 1):
        selected = selected_line(run, index)
        segments, info = model.transcribe(str(DATA / selected["path"]), language="zh", beam_size=5,
                                          vad_filter=False, word_timestamps=True, condition_on_previous_text=False)
        items = [dict(text=s.text, start=s.start, end=s.end, avgLogprob=s.avg_logprob,
                      words=[dict(word=w.word, start=w.start, end=w.end, probability=w.probability) for w in s.words or []]) for s in segments]
        lines.append(dict(index=index, role=line["role"], voice=line["voice"], expected=line["text"],
                          taskId=selected["taskId"], attempt=selected["attempt"], sourceSha256=selected["sha256"],
                          recognized="".join(s["text"] for s in items), segments=items, languageProbability=info.language_probability))
    report = dict(engine="Pinned existing faster-whisper-small, CPU INT8, local files only",
                  status="NeedReview", scope="Transcript evidence only; does not verify emotion, timbre or lip alignment", lines=lines)
    suffix = "-".join(f"{item['index']}a{item['attempt']}" for item in lines)
    write_json(FOLDER / f"speech-audit-{suffix}.json", report)
    if (FOLDER / "speech-audit.json").exists():
        previous_report = json.loads((FOLDER / "speech-audit.json").read_text(encoding="utf-8"))
        previous_suffix = "-".join(f"{item['index']}a{item.get('attempt', 1)}" for item in previous_report["lines"])
        preserve_copy(FOLDER / "speech-audit.json", FOLDER / "history" / f"speech-audit-{previous_suffix}.json")
    write_json(FOLDER / "speech-audit.json", report)
    print(json.dumps(lines, ensure_ascii=False, indent=2), flush=True)


def check(run: AudioRun):
    checked = []
    for path, expected in run.state.get("outputHashes", {}).items():
        if sha(DATA / path) != expected:
            raise RuntimeError("Existing prepared audio changed: " + path)
        checked.append(path)
    print(json.dumps(dict(stage=run.state["stage"], checked=checked, newTasksSubmitted=False), ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, choices=("generate", "repair", "prepare", "audit", "check"))
    parser.add_argument("--project-id", type=int)
    parser.add_argument("--line", type=int, choices=(1, 2, 3))
    parser.add_argument("--attempt", type=int, choices=(2, 3))
    parser.add_argument("--reason")
    args = parser.parse_args()
    if args.stage == "generate" and (args.project_id is None or args.project_id <= 0):
        parser.error("--project-id is required for explicit GPU generation")
    if args.stage == "repair" and (args.line is None or args.attempt is None):
        parser.error("--line and --attempt are required for explicit targeted GPU repair")
    FOLDER.mkdir(parents=True, exist_ok=True)
    run = AudioRun("http://127.0.0.1:18080", FOLDER / "run.json")
    if args.stage == "check":
        check(run)
        return
    with download_lock(FOLDER, filename=".audio-run.lock", conflict="Another audio runner is active; inspect recorded IDs"):
        run = AudioRun("http://127.0.0.1:18080", FOLDER / "run.json")
        if args.stage == "generate":
            generate(run, args.project_id)
        elif args.stage == "repair":
            repair(run, args.line, args.attempt, args.reason)
        elif args.stage == "prepare":
            prepare(run)
        elif args.stage == "audit":
            audit(run)


if __name__ == "__main__":
    main()
