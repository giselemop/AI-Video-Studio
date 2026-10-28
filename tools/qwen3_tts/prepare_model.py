"""Fetch the pinned public Qwen model. Weights use the existing resumable downloader."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/minimax"))
from download_assets import download, download_lock, digest


def main():
    config = json.loads((ROOT / "config/qwen3-tts.json").read_text(encoding="utf-8-sig"))
    destination = Path(config["modelDirectory"])
    destination.mkdir(parents=True, exist_ok=True)
    receipt = {"repository": config["repository"], "revision": config["revision"], "files": []}
    with download_lock(destination, ".qwen3-download.lock"):
        for name in config["files"]:
            path = destination / name
            url = f"https://huggingface.co/{config['repository']}/resolve/{config['revision']}/{name}"
            response = requests.get(url, timeout=(20, 90))
            response.raise_for_status()
            data = response.content
            if path.exists() and path.read_bytes() != data:
                raise RuntimeError(f"Existing model file differs; preserved: {name}")
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.with_suffix(path.suffix + ".part").write_bytes(data)
                path.with_suffix(path.suffix + ".part").rename(path)
            receipt["files"].append({"file": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            print(f"verified {name}", flush=True)
        for entry in config["weights"]:
            download({**entry, "target": entry["file"], "repository": config["repository"], "revision": config["revision"]},
                     destination, workers=4, chunk_size=32 * 1024 * 1024)
            receipt["files"].append({"file": entry["file"], "size": entry["size"], "sha256": digest(destination / entry["file"])})
        (destination / "deployment.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print("QWEN3_MODEL_VERIFIED", flush=True)


if __name__ == "__main__":
    main()
