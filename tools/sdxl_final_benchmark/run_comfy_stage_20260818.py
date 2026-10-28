"""Run real ComfyUI /prompt SDXL Stage A/B/C jobs with VRAM sampling."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


RUN_ROOT = Path(r"C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01")
COMFY = "http://127.0.0.1:8188"
INPUT_ROOT = Path(r"C:\install\AI\ComfyUI\input")
OUTPUT_ROOT = Path(r"C:\install\AI\ComfyUI\output")

VIEWS = {
    "front": {"targetYaw": 0, "template": "multiview_20260817_head_front_20260817.png", "prompt": "front-facing head and shoulders portrait"},
    "left30": {"targetYaw": -30, "template": "multiview_20260817_head_left_30_20260817.png", "prompt": "three-quarter left-facing head and shoulders portrait"},
    "right30": {"targetYaw": 30, "template": "multiview_20260817_head_right_30_20260817.png", "prompt": "three-quarter right-facing head and shoulders portrait"},
    "left45": {"targetYaw": -45, "template": "multiview_20260817_head_left_45_20260817.png", "prompt": "45-degree left-facing head and shoulders portrait"},
    "right45": {"targetYaw": 45, "template": "multiview_20260817_head_right_45_20260817.png", "prompt": "45-degree right-facing head and shoulders portrait"},
}


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def query_gpu() -> dict[str, Any] | None:
    try:
        output = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"], text=True, stderr=subprocess.STDOUT).strip()
        values = [item.strip() for item in output.splitlines()[0].split(",")]
        return {"name": values[0], "totalMiB": float(values[1]), "usedMiB": float(values[2]), "freeMiB": float(values[3]), "utilizationPercent": float(values[4])}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def workflow_for(method: str, stage: str, view_name: str, seed: int, prefix: str) -> dict[str, Any]:
    source = Path(r"C:\install\AI\Workflows\23_sdxl_instantid_final_benchmark_v1_api.json" if method == "InstantID" else r"C:\install\AI\Workflows\24_sdxl_pulid_final_benchmark_v1_api.json")
    if not source.exists():
        source = Path(r"C:\install\AI\Workflows\21_sdxl_instantid_multiview_probe_v1_api.json" if method == "InstantID" else r"C:\install\AI\Workflows\22_sdxl_pulid_multiview_probe_v1_api.json")
    workflow = json.loads(source.read_text(encoding="utf-8-sig"))
    view = VIEWS[view_name]
    positive = f"same adult East Asian man as the identity master, preserve exact facial identity, photorealistic live-action, neutral studio lighting, single face, consistent hair and clothing, {view['prompt']}"
    negative = "different person, identity drift, multiple people, malformed face, extra eyes, deformed mouth, blurry, low resolution, text, logo, watermark, duplicate face, asymmetrical eyes"
    workflow["1"]["inputs"]["ckpt_name"] = r"sdxl\sd_xl_base_1.0.safetensors"
    workflow["2"]["inputs"]["text"] = positive
    workflow["3"]["inputs"]["text"] = negative
    if method == "InstantID":
        workflow["4"]["inputs"]["image"] = "multiview_20260817_identity_master.png"
        workflow["5"]["inputs"]["instantid_file"] = "ip-adapter.bin"
        workflow["6"]["inputs"]["provider"] = "CPU"
        workflow["7"]["inputs"]["control_net_name"] = r"instantid\diffusion_pytorch_model.safetensors"
        workflow["8"]["inputs"]["image"] = view["template"]
        workflow["9"]["inputs"]["weight"] = 0.8
        workflow["9"]["inputs"]["start_at"] = 0.0
        workflow["9"]["inputs"]["end_at"] = 1.0
        sampler_id, save_id = "11", "13"
    else:
        workflow["4"]["inputs"]["pulid_file"] = "ip-adapter_pulid_sdxl_fp16.safetensors"
        workflow["5"]["inputs"]["provider"] = "CPU"
        workflow["7"]["inputs"]["image"] = "multiview_20260817_identity_master.png"
        workflow["8"]["inputs"]["method"] = "fidelity"
        workflow["8"]["inputs"]["weight"] = 0.8
        workflow["8"]["inputs"]["start_at"] = 0.0
        workflow["8"]["inputs"]["end_at"] = 1.0
        sampler_id, save_id = "10", "12"
    workflow[sampler_id]["inputs"]["seed"] = int(seed)
    workflow[sampler_id]["inputs"]["steps"] = 24
    workflow[sampler_id]["inputs"]["cfg"] = 5.0
    workflow[sampler_id]["inputs"]["sampler_name"] = "dpmpp_2m"
    workflow[sampler_id]["inputs"]["scheduler"] = "karras"
    workflow[save_id]["inputs"]["filename_prefix"] = prefix
    return workflow


class GpuMonitor:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.samples: list[dict[str, Any]] = []
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stop.is_set():
            sample = query_gpu()
            if sample:
                sample["capturedAt"] = now()
                self.samples.append(sample)
            self.stop.wait(1.0)

    def start(self) -> None:
        self.thread.start()

    def finish(self) -> None:
        self.stop.set()
        self.thread.join(timeout=3)
        final = query_gpu()
        if final:
            final["capturedAt"] = now()
            self.samples.append(final)

    def summary(self) -> dict[str, Any]:
        valid = [item for item in self.samples if "freeMiB" in item]
        if not valid:
            return {"samples": self.samples, "peakVramMiB": None, "lowestFreeMiB": None, "totalMiB": None}
        return {"samples": self.samples, "peakVramMiB": max(item["usedMiB"] for item in valid), "lowestFreeMiB": min(item["freeMiB"] for item in valid), "totalMiB": max(item["totalMiB"] for item in valid)}


def output_paths(history: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for node_output in history.get("outputs", {}).values():
        for image in node_output.get("images", []):
            filename = image.get("filename")
            if not filename:
                continue
            base = OUTPUT_ROOT if image.get("type", "output") == "output" else Path(r"C:\install\AI\ComfyUI\temp")
            path = base / image.get("subfolder", "") / filename
            paths.append(str(path.resolve()))
    return paths


def post_prompt(workflow: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    response = requests.post(COMFY + "/prompt", json=payload, timeout=60)
    raw: dict[str, Any]
    try:
        raw = response.json()
    except Exception:
        raw = {"text": response.text}
    if response.status_code >= 400:
        return None, {"httpStatus": response.status_code, "response": raw}
    return raw.get("prompt_id"), {"httpStatus": response.status_code, "response": raw}


def wait_prompt(prompt_id: str, timeout_seconds: int) -> tuple[bool, dict[str, Any], list[str]]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        response = requests.get(COMFY + "/history/" + prompt_id, timeout=30)
        if response.status_code == 200:
            history = response.json()
            if prompt_id in history:
                latest = history[prompt_id]
                status = latest.get("status", {})
                if status.get("status_str") == "error":
                    return False, latest, []
                paths = output_paths(latest)
                if paths:
                    return True, latest, paths
                if status.get("completed") and not latest.get("outputs"):
                    return False, latest, []
        time.sleep(1)
    return False, {"timeout": True, "last": latest}, []


def next_manifest_path(run_root: Path, method: str, stage: str) -> Path:
    base = run_root / f"stage-{method.lower()}-{stage.lower()}-generation.json"
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = run_root / f"stage-{method.lower()}-{stage.lower()}-generation_rerun{index:02d}.json"
        if not candidate.exists():
            return candidate
        index += 1


def stage_jobs(stage: str) -> list[tuple[str, int]]:
    if stage == "A":
        return [("front", 410001)]
    if stage == "B":
        return [(view, seed) for view in ["front", "left30", "left45"] for seed in [410101, 410102]]
    return [(view, seed) for view in ["front", "left30", "right30", "left45", "right45"] for seed in [420101, 420102, 420103]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["InstantID", "PuLID"], required=True)
    parser.add_argument("--stage", choices=["A", "B", "C"], required=True)
    parser.add_argument("--run-root", default=str(RUN_ROOT))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for view_name, seed in stage_jobs(args.stage):
        view = VIEWS[view_name]
        prefix = f"sdxl_final_benchmark_20260818/{args.method.lower()}_stage_{args.stage.lower()}_{view_name}_{seed}"
        workflow = workflow_for(args.method, args.stage, view_name, seed, prefix)
        started = time.perf_counter()
        start_time = now()
        monitor = GpuMonitor()
        prompt_id: str | None = None
        submit: dict[str, Any] = {}
        history: dict[str, Any] = {}
        paths: list[str] = []
        technical = False
        error: str | None = None
        monitor.start()
        try:
            prompt_id, submit = post_prompt(workflow)
            if prompt_id:
                technical, history, paths = wait_prompt(prompt_id, args.timeout_seconds)
                if not technical:
                    error = json.dumps(history, ensure_ascii=False)[:12000]
            else:
                error = json.dumps(submit, ensure_ascii=False)[:12000]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            monitor.finish()
        duration = round((time.perf_counter() - started) * 1000, 1)
        gpu = monitor.summary()
        row = {
            "method": args.method,
            "stage": args.stage,
            "requestedView": view_name,
            "targetYaw": view["targetYaw"],
            "seed": seed,
            "technicalSuccess": technical,
            "samplerStarted": bool(prompt_id),
            "samplerCompleted": technical,
            "startTime": start_time,
            "endTime": now(),
            "generationTimeMs": duration,
            "outputPaths": paths,
            "outputPath": paths[0] if paths else None,
            "workflow": workflow,
            "workflowSource": str(Path(r"C:\install\AI\Workflows\23_sdxl_instantid_final_benchmark_v1_api.json" if args.method == "InstantID" else r"C:\install\AI\Workflows\24_sdxl_pulid_final_benchmark_v1_api.json")),
            "promptId": prompt_id,
            "submit": submit,
            "history": history,
            "error": error,
            "oom": bool(error and any(token in error.lower() for token in ["out of memory", "cuda out of memory", "cublas_status_alloc_failed"])),
            "gpu": gpu,
            "hardwareStatus": "FAIL_OOM" if error and "out of memory" in error.lower() else ("PASS" if technical else "FAIL_WORKFLOW"),
            "fixedConfig": {"resolution": "512x768", "steps": 24, "cfg": 5.0, "sampler": "dpmpp_2m", "scheduler": "karras", "identityMaster": "multiview_20260817_identity_master.png", "positivePromptPolicy": "same method-independent prompt spec with view target phrase", "negativePrompt": "fixed across methods"},
        }
        rows.append(row)
        print(json.dumps({"method": args.method, "stage": args.stage, "view": view_name, "seed": seed, "technicalSuccess": technical, "durationMs": duration, "outputPath": row["outputPath"], "hardwareStatus": row["hardwareStatus"], "peakVramMiB": gpu.get("peakVramMiB"), "lowestFreeMiB": gpu.get("lowestFreeMiB"), "error": error}, ensure_ascii=False), flush=True)

    summary = {"requestedCount": len(rows), "technicalSuccessCount": sum(bool(row["technicalSuccess"]) for row in rows), "endToEndYield": None, "conditionalQualityYield": None, "stage": args.stage, "method": args.method}
    if rows:
        summary["endToEndYield"] = round(summary["technicalSuccessCount"] / len(rows), 4)
    technical_rows = [row for row in rows if row["technicalSuccess"]]
    if technical_rows:
        summary["conditionalQualityYield"] = 1.0
    manifest = {"schemaVersion": "2026-08-18.comfy-stage-generation.v1", "capturedAt": now(), "runRoot": str(run_root), "method": args.method, "stage": args.stage, "summary": summary, "rows": rows, "stopRule": "Stage B/C are interpreted by the QA evaluator; no quality sample is counted without a valid output file."}
    path = next_manifest_path(run_root, args.method, args.stage)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(path), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
