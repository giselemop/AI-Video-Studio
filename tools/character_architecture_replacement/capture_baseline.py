from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(r"C:\install\AI")
VIDEO_STUDIO_ROOT = PROJECT_ROOT / "VideoStudio"
COMFY_PYTHON = PROJECT_ROOT / "ComfyUI" / "venv" / "Scripts" / "python.exe"
MASTER = Path(
    r"C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01\worker_inputs\identity_master_6e39fe49dae7.png"
)


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 30) -> dict[str, Any]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": cmd,
            "returnCode": p.returncode,
            "stdout": p.stdout.strip(),
            "stderr": p.stderr.strip(),
        }
    except Exception as exc:  # pragma: no cover - diagnostic collector
        return {"command": cmd, "returnCode": None, "stdout": "", "stderr": repr(exc)}


def json_from_command(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> Any:
    result = run(cmd, cwd=cwd, timeout=timeout)
    if result["returnCode"] == 0:
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"raw": result["stdout"], "stderr": result["stderr"]}
    return {"error": result["stderr"], "returnCode": result["returnCode"]}


def http_json(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(body)
            except json.JSONDecodeError:
                parsed = body[:2000]
            return {
                "url": url,
                "status": response.status,
                "elapsedMs": round((time.perf_counter() - started) * 1000, 2),
                "body": parsed,
            }
    except Exception as exc:
        return {
            "url": url,
            "status": None,
            "elapsedMs": round((time.perf_counter() - started) * 1000, 2),
            "error": repr(exc),
        }


def file_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if path.is_file():
        stat = path.stat()
        record.update({"sizeBytes": stat.st_size, "mtimeUtc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        record["sha256"] = digest.hexdigest()
    return record


def dir_size(path: Path) -> dict[str, Any]:
    total = 0
    files = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                    files += 1
                except OSError:
                    pass
    return {"path": str(path), "exists": path.exists(), "files": files, "sizeBytes": total}


def capture_python() -> dict[str, Any]:
    probe = (
        "import json,sys; "
        "x={'python':sys.version,'executable':sys.executable}; "
        "\ntry:\n import torch; x.update({'torch':torch.__version__,'torchCuda':torch.version.cuda,'cudaAvailable':bool(torch.cuda.is_available()),'gpuCount':torch.cuda.device_count(),'gpuName':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}); "
        "\nexcept Exception as e: x.update({'torchError':repr(e)}); "
        "print(json.dumps(x,ensure_ascii=False))"
    )
    return json_from_command([str(COMFY_PYTHON), "-c", probe], timeout=60)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    args = parser.parse_args()
    run_root = Path(args.run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    git_status = run(["git", "-C", str(VIDEO_STUDIO_ROOT), "status", "--short"], timeout=30)
    git_branch = run(["git", "-C", str(VIDEO_STUDIO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"], timeout=30)
    git_head = run(["git", "-C", str(VIDEO_STUDIO_ROOT), "rev-parse", "HEAD"], timeout=30)
    dirty_lines = [line for line in git_status["stdout"].splitlines() if line.strip()]

    drive = shutil.disk_usage(PROJECT_ROOT.drive + os.sep)
    env = {
        "schema": "character-architecture-replacement.environment.v1",
        "capturedAtUtc": now,
        "runRoot": str(run_root),
        "projectRoot": str(PROJECT_ROOT),
        "videoStudioRoot": str(VIDEO_STUDIO_ROOT),
        "git": {
            "branch": git_branch["stdout"],
            "head": git_head["stdout"],
            "dirtyCount": len(dirty_lines),
            "statusCommand": git_status,
            "preservationRule": "Existing dirty work is user-owned and must not be reset, cleaned, or overwritten.",
        },
        "disk": {
            "drive": PROJECT_ROOT.drive,
            "totalBytes": drive.total,
            "usedBytes": drive.total - drive.free,
            "freeBytes": drive.free,
            "freeGiB": round(drive.free / 1024**3, 2),
            "trackedDirectories": [
                dir_size(PROJECT_ROOT / "Models"),
                dir_size(PROJECT_ROOT / "HF_HOME"),
                dir_size(PROJECT_ROOT / "CharacterArchitectures"),
            ],
        },
        "hardware": {
            "nvidiaSmi": run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,memory.free,driver_version,temperature.gpu,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                timeout=30,
            ),
            "comfyPython": capture_python(),
        },
        "services": {
            "comfy": http_json("http://127.0.0.1:8188/system_stats"),
            "mainApi": http_json("http://127.0.0.1:18080/api/health"),
            "identityWorker": http_json("http://127.0.0.1:18084/health"),
        },
        "referenceAssets": {
            "identityMaster": file_record(MASTER),
            "previousSdxlEvidence": str(PROJECT_ROOT / "Data" / "QA" / "sdxl_identity_final_benchmark_20260818" / "run_01"),
        },
        "candidateIsolation": {
            "root": str(PROJECT_ROOT / "CharacterArchitectures"),
            "mainApiRestarted": False,
            "identityWorkerModified": False,
            "modelRouterModified": False,
            "comfyMainProcessModified": False,
        },
    }

    baseline = {
        "schema": "character-architecture-replacement.baseline.v1",
        "capturedAtUtc": now,
        "decisionInheritedFromPreviousBenchmark": "REPLACE_CHARACTER_GENERATION_ARCHITECTURE",
        "historicalBaselines": {
            "instantId": {"status": "REJECTED_AS_MAIN_CANDIDATE", "dualPass": "0/6", "medianIdentityCosine": 0.24825968},
            "puLid": {"status": "REJECTED_AS_MAIN_CANDIDATE", "dualPass": "1/6", "medianIdentityCosine": 0.64855647},
            "sourceEvidence": str(PROJECT_ROOT / "Data" / "QA" / "sdxl_identity_final_benchmark_20260818" / "run_01"),
        },
        "newArchitectureAcceptance": {
            "identityRawCosineMin": 0.5,
            "frontAbsYawMaxDegreesExclusive": 15,
            "yaw30RangeDegrees": [12, 40],
            "yaw45RangeDegrees": [27, 62],
            "coreViews": ["front", "left30", "right30", "left45", "right45"],
            "crossViewPairs": [
                "front-left30", "front-right30", "front-left45", "front-right45",
                "left30-left45", "right30-right45",
            ],
            "viewPassMinimumCount": 4,
            "dualPassMinimumRatio": 0.5,
            "strongDualPassRatio": 0.7,
            "strongMultiViewSetPassRatio": 0.5,
            "crossViewConsistencyThreshold": "record threshold and applied value in 10-multiview-mini-benchmark.json",
        },
        "scope": {
            "allowed": ["survey", "isolated deployment audit", "real candidate sampling", "multi-view mini benchmark", "comparison and decision"],
            "prohibited": ["Character LoRA training", "I2V", "Wan Animate", "HunyuanVideo action tests", "TTS", "subtitles", "25s/60s video", "new episode", "production Master", "rebenchmarking InstantID/PuLID/FaceID as main candidates"],
        },
        "requiredDecisionStates": ["ARCHITECTURE_SELECTED_FOR_POC", "ARCHITECTURE_CONDITIONAL", "NO_LOCAL_ARCHITECTURE_READY", "CLOUD_GPU_REQUIRED_FOR_NEXT_POC", "ARCHITECTURE_SELECTION_INSUFFICIENT"],
    }

    (run_root / "01-environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "02-current-architecture-baseline.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"environment": str(run_root / "01-environment.json"), "baseline": str(run_root / "02-current-architecture-baseline.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
