"""Render evidence-based progress/final records without API or inference calls.

progress updates only the new detailed report and Data/execution-summary.json.
final additionally synchronizes bounded project handoff blocks, Chinese first,
after the final file, actual task result and browser playback evidence pass.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT.parent / "Data" / "DialogueThreeShot20261023"
REPORT = ROOT / "docs" / "DIALOGUE_THREE_SHOT_20261023.md"
GENERATED_START = "<!-- dialogue-three-shot-evidence:start -->"
GENERATED_END = "<!-- dialogue-three-shot-evidence:end -->"
START = "<!-- dialogue-three-shot-20261023:start -->"
END = "<!-- dialogue-three-shot-20261023:end -->"
TASK_FIELDS = ("id", "projectId", "taskType", "resourceClass", "stage", "status", "progress", "attempts",
               "startedAt", "finishedAt", "durationMs", "vramPeakMiB", "errorType", "errorMessage")


def read(path, required=False):
    path = Path(path)
    if not path.exists():
        if required:
            raise RuntimeError("Required evidence is missing: " + str(path))
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def media(value):
    root = (ROOT.parent / "Data").resolve()
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise RuntimeError("Evidence media must stay inside Data")
    return path


def digest(value):
    with media(value).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git_state():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, encoding="utf-8").strip()
    return dict(branch=git("branch", "--show-current"), head=git("rev-parse", "HEAD"))


def task_evidence(run, audio):
    task_map = {}
    for path in sorted([*FOLDER.glob("*-result.json"), *(FOLDER / "audio").glob("*-task.json")]):
        result = read(path, required=True)
        task = result.get("task") if isinstance(result, dict) else None
        if not isinstance(task, dict) or not isinstance(task.get("id"), int):
            raise RuntimeError("Task-result evidence has no actual task metadata: " + path.name)
        item = {key: task.get(key) for key in TASK_FIELDS}
        item["evidence"] = path.relative_to(FOLDER).as_posix()
        # Keep all outputs and statuses actually returned by the service, including failed attempts.
        item["availableOutputs"] = [{key: value.get(key) for key in
                                    ("assetPath", "mimeType", "width", "height", "fps", "durationSeconds")}
                                   for value in result.get("results", []) if value.get("available")]
        previous = task_map.get(task["id"])
        if previous and any(previous.get(k) != item.get(k) for k in TASK_FIELDS):
            raise RuntimeError("Conflicting snapshots for task " + str(task["id"]))
        task_map[task["id"]] = item
    references = {}
    for label, state in (("video", run), ("audio", audio)):
        for field, task_id in state.items():
            if re.search(r"TaskId$", field) and isinstance(task_id, int) and not isinstance(task_id, bool):
                references.setdefault(task_id, []).append(label + "." + field)
    return [dict(task_map[key], fields=references.get(key, [])) for key in sorted(task_map)], references


def resources():
    samples, warnings = [], []
    for path in (FOLDER / "resources.jsonl", FOLDER / "audio" / "resources.jsonl"):
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
            except json.JSONDecodeError:
                if index != len(lines) - 1:
                    raise RuntimeError("Corrupt resource evidence: " + str(path))
                warnings.append(path.relative_to(FOLDER).as_posix() + ": incomplete current last sample omitted")
                continue
            sample["evidence"] = path.relative_to(FOLDER).as_posix()
            samples.append(sample)
    gpu = [x["gpu"][0] for x in samples if isinstance(x.get("gpu"), list) and x["gpu"]]
    ram = [x["availableRamMiB"] for x in samples if isinstance(x.get("availableRamMiB"), (int, float))]
    latest = {}
    for sample in sorted(samples, key=lambda x: x.get("epoch", 0)):
        if isinstance(sample.get("taskId"), int):
            latest[sample["taskId"]] = {key: sample.get(key) for key in ("epoch", "status", "progress", "evidence")}
    return dict(scope="Sampled device memory, not process allocation or continuous monitoring",
                sampleCount=len(samples), sampledPeakDeviceMiB=max(gpu) if gpu else None,
                sampledMinimumAvailableRamMiB=min(ram) if ram else None,
                latestTaskObservations=latest, warnings=warnings)


def completed_gpu_concurrency(tasks):
    events = []
    for task in tasks:
        if task.get("resourceClass") != "GPU" or not task.get("startedAt") or not task.get("finishedAt"):
            continue
        events.extend([(datetime.fromisoformat(task["startedAt"]), 1),
                       (datetime.fromisoformat(task["finishedAt"]), -1)])
    current = maximum = 0
    for _, amount in sorted(events, key=lambda x: (x[0], x[1])):
        current += amount
        maximum = max(maximum, current)
    return maximum if events else None


def require_final(run, verification, browser, tasks):
    if run.get("stage") != "ReadyForUserPreview" or run.get("technicalStatus") != "Passed":
        raise RuntimeError("Final records require the completed ReadyForUserPreview run")
    if not verification or verification.get("status") != "Passed":
        raise RuntimeError("Actual delivery-verification.json must be Passed")
    if not run.get("finalPath") or digest(run["finalPath"]) != run.get("finalSha256"):
        raise RuntimeError("Final media differs from the recorded hash")
    if verification.get("finalSha256") != run["finalSha256"]:
        raise RuntimeError("Final verification belongs to different media")
    if tuple(verification.get(key) for key in ("width", "height", "fps", "frames")) != (1280, 720, 24, 240):
        raise RuntimeError("The verified export must be 1280x720/24FPS/240 frames")
    if not browser or browser.get("status") != "Passed" or browser.get("ended") is not True:
        raise RuntimeError("Actual complete browser playback must be Passed")
    if browser.get("muted") is not False or browser.get("volumePercent") != 100 or abs(float(browser.get("duration", -1)) - 10) > .05:
        raise RuntimeError("Browser evidence must show the ten-second unmuted result")
    final_task = next((task for task in tasks if task["id"] == run.get("finalTaskId")), None)
    if final_task is None or final_task.get("status") != "Succeeded":
        raise RuntimeError("The actual successful final business task result is required")


def summary(stage):
    run = read(FOLDER / "run.json", required=True)
    audio = read(FOLDER / "audio" / "run.json", required=True)
    tasks, references = task_evidence(run, audio)
    verification = read(FOLDER / "delivery-verification.json")
    browser = read(FOLDER / "browser-final-playback.json")
    if stage == "final":
        require_final(run, verification, browser, tasks)
    resource = resources()
    task_ids = {task["id"] for task in tasks}
    return dict(
        generatedAt=datetime.now(timezone.utc).isoformat(), reportStage=stage,
        scope="Recorded local business task results, actual files and browser evidence; no cloud inference or API calls by this generator",
        **git_state(), projectId=run.get("projectId"), runStage=run.get("stage"),
        technicalStatus="Passed" if stage == "final" else run.get("technicalStatus", "Blocked"),
        contentStatus="NeedReview", publicationStatus="Blocked", finalTaskId=run.get("finalTaskId"),
        finalPath=run.get("finalPath"), finalSha256=run.get("finalSha256"), previousPath=run.get("previousPath"),
        previousSha256=run.get("previousSha256"), timeline=run.get("timeline", audio.get("timeline", [])),
        shots=run.get("shots", audio.get("shots", [])), workflowPlan=read(FOLDER / "workflow-plan.json"),
        referenceManifest=read(FOLDER / "reference-manifest.json"), audioPreparation=read(FOLDER / "audio" / "preparation.json"),
        roomMix=read(FOLDER / "audio" / "room-mix.json"), speechAudit=read(FOLDER / "audio" / "speech-audit.json"),
        tasks=tasks, taskReferences={str(k): v for k, v in references.items()},
        unresolvedTaskSnapshots=[dict(taskId=key, fields=value,
                                    lastObserved=resource["latestTaskObservations"].get(key))
                                 for key, value in sorted(references.items()) if key not in task_ids],
        gpuDurationMs=sum(task.get("durationMs") or 0 for task in tasks if task.get("resourceClass") == "GPU"),
        cpuDurationMs=sum(task.get("durationMs") or 0 for task in tasks if task.get("resourceClass") == "CPU"),
        durationScope="Sum of actual recorded task durationMs, including preserved attempts; excludes incomplete tasks and initial downloads",
        maxCompletedGpuTaskConcurrency=completed_gpu_concurrency(tasks), resources=resource,
        deliveryVerification=verification, browserPlayback=browser,
    )


def number(value, places=3):
    return "尚无记录" if value is None else f"{value:.{places}f}".rstrip("0").rstrip(".")


def cell(value):
    return str(value if value is not None else "尚无记录").replace("|", "\\|").replace("\n", " ")


def render(value):
    final = value["reportStage"] == "final"
    lines = [
        f"更新于 `{value['generatedAt']}`。",
        "",
        f"当前阶段：`{value['runStage']}`；技术状态 `{value['technicalStatus']}`；内容 `NeedReview`；发布 `Blocked`。",
        "完成验收，已可供用户观看。" if final else "本轮仍在执行；以下只记录已有证据，不代表完整成片已通过验收。",
        "",
        f"项目 `{value['projectId']}`，当前分支 `{value['branch']}`，HEAD `{value['head']}`。分支和提交来自本次实际 Git 查询；不代表工作区已提交。",
        "",
        "### 对白与三镜头安排",
        "",
        "| 句 | 人物/声音 | 原台词 | 成片时间（秒） | 选用任务/候选 |",
        "|---|---|---|---|---|",
    ]
    for item in value["timeline"]:
        lines.append(f"| {item['index']} | {cell(item['role'])}/{cell(item['voice'])} | {cell(item['text'])} | "
                     f"{number(item['startSeconds'])}–{number(item['endSeconds'])} | {item.get('taskId')} / {item.get('attempt', 1)} |")
    gaps = (value.get("audioPreparation") or {}).get("responseGapsSeconds")
    lines += ["", f"非统一换人间隔：`{gaps}` 秒；原速原音高。只允许裁去句子外部低电平边缘，内部发音与停顿保持。",
              "本地 ASR 提供文字核查证据，不能证明情绪、音色或口型表演已经正确。", "",
              "| 镜头 | 构图 | 成片区间（秒） | 原生生成帧数/时长 |", "|---|---|---|---|"]
    plans = {p["index"]: p for p in value.get("workflowPlan") or []}
    for shot in value["shots"]:
        plan = plans.get(shot["index"], {})
        lines.append(f"| {shot['index']} | {cell(shot.get('label') or shot.get('composition'))} | "
                     f"{number(shot['startSeconds'])}–{number(shot['endSeconds'])} | "
                     f"{plan.get('nativeFrames', '尚无记录')} / {number(plan.get('nativeDurationSeconds'))} 秒 |")
    lines += ["", "人物参考来自原始1536×864首帧1216的确定性裁图，保留同一对虚构成年人物；没有生成新的多视角身份图，也没有复用旧视频冒充新生成。",
              "原生视频为832×480、25FPS。最终720P/24FPS是重新编排、缩放及可选细节修复后的交付规格，不能称为原生720P。",
              "三个全新v1工作流复用既有Wan2.1 I2V Q4、InfiniteTalk Multi Q8、LightX2V蒸馏LoRA、wav2vec2、UMT5和VAE。6步、CFG1、blockswap30，GPU串行；本轮未改变旧服务超时规则。",
              "",
              "### 实际任务与资源", "", "| 任务 | 类型/资源 | 服务状态 | 实际耗时（秒） | 结果证据 |", "|---|---|---|---|---|"]
    for task in value["tasks"]:
        duration = task.get("durationMs")
        lines.append(f"| {task['id']} | {cell(task.get('taskType'))}/{cell(task.get('resourceClass'))} | {cell(task.get('status'))} | "
                     f"{number(duration / 1000 if duration is not None else None)} | `{task['evidence']}` |")
    pending = value["unresolvedTaskSnapshots"]
    if pending:
        lines += ["", "已记录ID、尚无终态结果快照的任务：" + "；".join(
            f"{x['taskId']}（最后采样：{(x.get('lastObserved') or {}).get('status', '暂无')}）" for x in pending) + "。"]
    resource = value["resources"]
    lines += ["", f"已记录GPU任务耗时合计 `{value['gpuDurationMs'] / 1000:.3f}` 秒；CPU合计 `{value['cpuDurationMs'] / 1000:.3f}` 秒，含保留候选，不含未完成任务。",
              f"资源采样 `{resource['sampleCount']}` 条：整卡采样显存峰值 `{resource['sampledPeakDeviceMiB']}` MiB，系统最低可用内存 `{resource['sampledMinimumAvailableRamMiB']}` MiB。这是采样值，不能视为进程精确峰值或连续监控。",
              f"已有完整起止时间的GPU任务最大重叠数：`{value['maxCompletedGpuTaskConcurrency']}`；未完成任务不计入该值。",
              "", "### 交付、核验与限制", ""]
    if value.get("finalPath"):
        lines += [f"成片：`{value['finalPath']}`。", f"SHA256：`{value['finalSha256']}`。", f"最终业务任务：`{value['finalTaskId']}`。", ""]
    else:
        lines += ["最终视频尚未记录；不以计划规格冒充实际输出。", ""]
    verification = value.get("deliveryVerification")
    if verification:
        lines += [f"`delivery-verification.json`：`{verification.get('status')}`，仅覆盖 `{verification.get('scope')}`。",
                  f"实际解码帧数 `{verification.get('decodedFrames')}`，独立帧哈希数 `{verification.get('uniqueDecodedHashes')}`，旧媒体保持核验数 `{verification.get('preservedFiles')}`。", ""]
    browser = value.get("browserPlayback")
    if browser:
        lines += [f"实际浏览器播放记录：`{browser.get('status')}`，ended=`{browser.get('ended')}`，muted=`{browser.get('muted')}`，volume=`{browser.get('volumePercent')}`。", ""]
    room = value.get("roomMix")
    if room:
        lines += ["音频空间处理为程序合成的轻微单声道室内脉冲响应，不是录制环境声或实测房间响应；没有额外加入动作拟音。", ""]
    lines += ["细微情绪、真实感、身份连续性、视线反应、牙齿与逐音节口型仍需观看试听；技术Passed不能替代内容人工判断。",
              "初次与修复候选全部保留，不把未选用或失败候选重命名为通过。本轮没有发布或云推理授权。",
              "", "恢复时先读取 `Data/DialogueThreeShot20261023/run.json` 和 `audio/run.json`，核对已有任务ID。ReadyForUserPreview后仅核验旧结果，不自动新增生成。",
              "详细机器证据：`Data/DialogueThreeShot20261023/execution-summary.json`；媒体、工作流、资源采样和验收JSON保存在同目录。"]
    return "\n".join(lines)


def bounded(text, start, end, body):
    block = start + "\n" + body.rstrip() + "\n" + end
    if (start in text) != (end in text):
        raise RuntimeError("Incomplete bounded documentation markers")
    if text.count(start) > 1 or text.count(end) > 1:
        raise RuntimeError("Duplicate bounded documentation markers")
    if start in text:
        first, last = text.index(start), text.index(end)
        if last < first:
            raise RuntimeError("Reversed bounded documentation markers")
        return text[:first] + block + text[last + len(end):]
    return block + "\n\n" + text


def write_report(value):
    text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else "# 同人物同台词：纯本地10秒三镜头样片\n\n"
    REPORT.write_text(bounded(text, GENERATED_START, GENERATED_END, render(value)), encoding="utf-8")


def sync_handoff(value):
    resource = value["resources"]
    text = (f"2026-10-23交付：项目{value['projectId']}同人物、同四句台词的纯本地三镜头样片，最终任务{value['finalTaskId']}实际1280×720/24FPS/240帧/10秒。"
            "先调整Qwen逐句语气与非统一停顿，再生成女近景、男反打、双人收尾；原生832×480/25FPS，720P为后期交付。"
            "最终技术和真实浏览器完整播放Passed；情绪/人物反应/精细口型仍待用户复核，发布Blocked。"
            f"GPU任务耗时合计{value['gpuDurationMs'] / 1000:.3f}秒（含保留候选），采样显存峰值{resource['sampledPeakDeviceMiB']}MiB。"
            "恢复Data/DialogueThreeShot20261023/run.json为ReadyForUserPreview，仅核验、不重提。")
    names = ["项目状态.md", "待办事项.md", "变更记录.md", "PROJECT_STATE.md", "NEXT_STAGE.md", "CHANGELOG.md",
             "docs/ACCEPTANCE_REPORT.md", "docs/FIX_HISTORY.md"]
    # Preflight every marker before the first edit; write Chinese authority files before compatibility entries.
    changes = []
    for name in names:
        path = ROOT / name
        original = path.read_text(encoding="utf-8")
        link = "DIALOGUE_THREE_SHOT_20261023.md" if name.startswith("docs/") else "docs/DIALOGUE_THREE_SHOT_20261023.md"
        changes.append((path, original, bounded(original, START, END, "> " + text + f" 见[本轮记录]({link})。")))
    for path, original, updated in changes:
        if path.read_text(encoding="utf-8") != original:
            raise RuntimeError("Documentation changed concurrently; preserved " + str(path))
        if updated != original:
            path.write_text(updated, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("progress", "final"), required=True)
    args = parser.parse_args()
    value = summary(args.stage)
    save(FOLDER / "execution-summary.json", value)
    write_report(value)
    if args.stage == "final":
        sync_handoff(value)
    print(json.dumps(dict(reportStage=args.stage, runStage=value["runStage"], projectId=value["projectId"],
                          recordedTasks=len(value["tasks"]), unresolvedSnapshots=len(value["unresolvedTaskSnapshots"]),
                          rootDocumentsUpdated=args.stage == "final", newTasksSubmitted=False), ensure_ascii=False))


if __name__ == "__main__":
    main()
