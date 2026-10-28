"""Verify files and live ComfyUI schemas without loading models or queueing work."""

import argparse
import datetime
import json
from pathlib import Path
import shutil
import urllib.request

from download_models import ARTIFACTS, MODEL_ROOT, EVIDENCE_ROOT, file_hash
from prepare import build_workflow, MODELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy", default="http://127.0.0.1:8188")
    parser.add_argument("--hash", action="store_true")
    args = parser.parse_args()
    if args.comfy.rstrip("/") != "http://127.0.0.1:8188":
        raise ValueError("This pilot is restricted to the existing loopback ComfyUI server")
    graph = build_workflow("explicit_input_placeholder.png", "preflight only", 20261024)
    report = {"time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "gpu_submitted": False, "files": [], "nodes": []}
    for artifact in ARTIFACTS:
        path = MODEL_ROOT / artifact["role"] / artifact["name"]
        passed = path.is_file() and path.stat().st_size == artifact["size"]
        if args.hash and passed:
            passed = file_hash(path) == artifact["sha256"]
        report["files"].append({"name": artifact["name"], "passed": passed, "sha256_checked": args.hash})
    for class_type in sorted({n["class_type"] for n in graph.values()}):
        with urllib.request.urlopen(args.comfy + "/object_info/" + class_type, timeout=20) as response:
            schema = json.load(response).get(class_type)
        row = {"class_type": class_type, "passed": schema is not None}
        if schema:
            required = schema["input"].get("required", {})
            example = next(n for n in graph.values() if n["class_type"] == class_type)
            row["missing_inputs"] = sorted(set(required) - set(example["inputs"]))
            declared = set(required) | set(schema["input"].get("optional", {}))
            row["unknown_inputs"] = sorted(set(example["inputs"]) - declared)
            row["passed"] = not row["missing_inputs"] and not row["unknown_inputs"]
            if class_type in ("UNETLoader", "CLIPLoader", "VAELoader"):
                key = {"UNETLoader": "unet_name", "CLIPLoader": "clip_name", "VAELoader": "vae_name"}[class_type]
                choices = required[key][0]
                row["model_visible"] = example["inputs"][key] in choices
                row["passed"] = row["passed"] and row["model_visible"]
        report["nodes"].append(row)
    report["free_bytes"] = shutil.disk_usage(MODEL_ROOT.parent).free
    report["status"] = "Passed" if all(r["passed"] for r in report["files"] + report["nodes"]) and report["free_bytes"] >= 30 * 1024**3 else "Blocked"
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (EVIDENCE_ROOT / ("preflight_" + stamp + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    raise SystemExit(0 if report["status"] == "Passed" else 2)


if __name__ == "__main__":
    main()
