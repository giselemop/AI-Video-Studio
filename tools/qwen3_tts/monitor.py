"""Bounded, sampled GPU evidence for the real queued preview; no model execution."""
import csv
import json
from pathlib import Path
import subprocess
import time

evidence = Path(__file__).resolve().parents[3] / "Data/Qwen3Tts20261022"
evidence.mkdir(parents=True, exist_ok=True)
samples = []
started = time.monotonic()
while time.monotonic() - started < 900:
    state_path = evidence / "run.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state.get("stage") in {"ReadyForUserPreview", "Failed", "Cancelled"}: break
    result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu,power.draw", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    row = next(csv.reader(result.stdout.splitlines()))
    sample = {"epochSeconds": time.time(), "stage": state.get("stage", "Waiting"),
        "usedMiB": int(row[0]), "freeMiB": int(row[1]), "utilizationPercent": int(row[2]), "powerWatts": float(row[3])}
    samples.append(sample)
    with (evidence / "gpu-samples.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(sample) + "\n")
    time.sleep(1)
report = {"intervalSeconds": 1, "samples": len(samples), "wholeCardPeakUsedMiB": max((s["usedMiB"] for s in samples), default=None),
    "minimumFreeMiB": min((s["freeMiB"] for s in samples), default=None)}
(evidence / "gpu-summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report), flush=True)
