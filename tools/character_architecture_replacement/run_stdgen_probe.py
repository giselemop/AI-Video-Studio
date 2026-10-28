from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def nvidia_snapshot() -> dict:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        line = completed.stdout.strip().splitlines()[0]
        fields = [part.strip() for part in line.split(",")]
        names = ["name", "totalMiB", "usedMiB", "freeMiB", "utilizationPct", "temperatureC"]
        result: dict = {}
        for name, value in zip(names, fields):
            try:
                result[name] = float(value) if name != "name" else value
            except ValueError:
                result[name] = value
        return result
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def collect_images(output_dir: Path) -> list[str]:
    return [str(path.resolve()) for path in sorted(output_dir.rglob("color_*.png"))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--sidecar", required=True)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--width", type=int, default=288)
    parser.add_argument("--num-views", type=int, default=6)
    parser.add_argument("--num-levels", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    model = Path(args.model).resolve()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "candidate-b-execution.json"
    stdout_path = output_dir / "candidate-b-stdout.log"
    stderr_path = output_dir / "candidate-b-stderr.log"
    result: dict = {
        "schema": "character-architecture-replacement.candidate-execution.v1",
        "capturedAtUtc": now(),
        "candidate": "StdGEN",
        "alias": "candidate-b",
        "repo": str(repo),
        "repoHead": None,
        "model": str(model),
        "inputDir": str(input_dir),
        "outputDir": str(output_dir),
        "requested": {
            "stage": "multiview_diffusion",
            "views": args.num_views,
            "levels": args.num_levels,
            "height": args.height,
            "width": args.width,
            "inputContract": "single_png_head_portrait_used_as_direct_multiview_input; official pipeline normally expects canonicalized full-body input",
        },
        "pipelineBoundary": {
            "attempted": ["official StdGEN multiview diffusion inference", "six-view color/normal output"],
            "notAttempted": ["canonicalization stage", "S-LRM reconstruction", "texture refinement", "full-body input validation"],
            "reason": "The frozen master is head-and-shoulders only; this probe isolates the multiview stage and records the input-contract limitation.",
        },
        "status": "STARTED",
        "startedAtUtc": now(),
        "beforeGpu": nvidia_snapshot(),
        "images": [],
    }
    try:
        try:
            result["repoHead"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=30).strip()
        except Exception:
            pass
        command = [
            str(args.python),
            str(repo / "infer_multiview.py"),
            "--pretrained_path", str(model),
            "--input_dir", str(input_dir),
            "--output_dir", str(output_dir / "multiview"),
            "--height", str(args.height),
            "--width", str(args.width),
            "--low_vram",
            "--num_views", str(args.num_views),
            "--num_levels", str(args.num_levels),
            "--seed", "410101",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(Path(args.sidecar).resolve()), str(repo), env.get("PYTHONPATH", "")])
        env["PYTHONUNBUFFERED"] = "1"
        result["command"] = command
        result["environment"] = {"PYTHONPATH": env["PYTHONPATH"], "PYTHONUNBUFFERED": env["PYTHONUNBUFFERED"]}
        started = time.perf_counter()
        result["gpuSamples"] = []
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr:
            process = subprocess.Popen(command, cwd=str(repo), env=env, stdout=stdout, stderr=stderr)
            result["pid"] = process.pid
            while True:
                code = process.poll()
                if code is not None:
                    break
                result["gpuSamples"].append({"elapsedSeconds": round(time.perf_counter() - started, 3), "snapshot": nvidia_snapshot()})
                if time.perf_counter() - started > args.timeout_seconds:
                    process.kill()
                    process.wait(timeout=30)
                    result["status"] = "TIMEOUT"
                    result["error"] = f"Probe exceeded {args.timeout_seconds} seconds"
                    break
                time.sleep(5)
            else:
                code = None
        result["returnCode"] = code
        result["elapsedSeconds"] = round(time.perf_counter() - started, 3)
        result["afterGpu"] = nvidia_snapshot()
        used_values = [sample["snapshot"].get("usedMiB") for sample in result.get("gpuSamples", []) if isinstance(sample.get("snapshot", {}).get("usedMiB"), (int, float))]
        result["peakVramMiB"] = max(used_values) if used_values else None
        result["stdoutPath"] = str(stdout_path.resolve())
        result["stderrPath"] = str(stderr_path.resolve())
        result["images"] = collect_images(output_dir / "multiview")
        if result.get("status") != "TIMEOUT":
            result["status"] = "GENERATED" if result["returnCode"] == 0 and result["images"] else "FAILED"
    except Exception as exc:
        result["status"] = "FAILED"
        result["error"] = repr(exc)
        result["traceback"] = traceback.format_exc()
        result["afterGpu"] = nvidia_snapshot()
    result["finishedAtUtc"] = now()
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "result": str(result_path), "images": len(result.get("images", [])), "elapsedSeconds": result.get("elapsedSeconds")}, ensure_ascii=False))
    return 0 if result["status"] == "GENERATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
