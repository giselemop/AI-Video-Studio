"""Offline per-task Qwen inference. Invoked by VideoStudio under its GPU lease."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

# Never download a model or send text to an external service during synthesis.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    request = json.loads(sys.stdin.read())
    text = request["text"].strip()
    instruction = request.get("instruction", "").strip()
    if not text or len(text) > config["maxTextCharacters"] or len(instruction) > config["maxInstructionCharacters"]:
        raise ValueError("Text or instruction exceeds the configured limit")
    data_root = (args.config.resolve().parents[2] / "Data").resolve()
    output = Path(request["output"]).resolve()
    if not output.is_relative_to(data_root) or output.exists() or output.is_symlink():
        raise ValueError("Output must be a new file inside the governed Data directory")

    model_directory = Path(config["modelDirectory"])
    for entry in config["weights"]:
        with (model_directory / entry["file"]).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                raise RuntimeError("Pinned Qwen model checksum mismatch")

    started = time.perf_counter()
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the selected Qwen deployment")
    free, _ = torch.cuda.mem_get_info()
    if free / 1024**2 < config["minFreeVramMiB"]:
        raise RuntimeError("Insufficient free VRAM for the selected Qwen model; no fallback model was loaded")
    torch.set_num_threads(4)
    torch.manual_seed(20261021)
    torch.cuda.reset_peak_memory_stats()
    loaded_at = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(config["modelDirectory"], device_map="cuda:0",
        dtype=getattr(torch, config["dtype"]), attn_implementation=config["attention"], local_files_only=True)
    speaker = request["speaker"]
    if speaker.lower() not in {v.lower() for v in model.get_supported_speakers()}:
        raise ValueError("Unsupported Qwen speaker")
    inference_started = time.perf_counter()
    with torch.inference_mode():
        waves, sample_rate = model.generate_custom_voice(text=text, language="Chinese", speaker=speaker,
            instruct=instruction or None, max_new_tokens=config["maxNewTokens"])
    torch.cuda.synchronize()
    audio = np.asarray(waves[0], dtype=np.float32)
    if not audio.size or not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-5:
        raise RuntimeError("Qwen generated empty, silent or invalid audio")
    output.parent.mkdir(parents=True, exist_ok=True)
    # File is private staging data until the .NET manifest publisher validates it.
    sf.write(str(output), audio, sample_rate, subtype="PCM_16", format="WAV")
    receipt = {"provider": "Qwen3TTSLocal", "repository": config["repository"], "revision": config["revision"],
        "voice": speaker, "language": "Chinese", "instruction": instruction, "seed": 20261021,
        "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "textCharacters": len(text),
        "durationSeconds": len(audio) / sample_rate, "sampleRate": sample_rate,
        "totalSeconds": time.perf_counter() - started, "modelLoadSeconds": inference_started - loaded_at,
        "inferenceSeconds": time.perf_counter() - inference_started,
        "peakAllocatedMiB": torch.cuda.max_memory_allocated() / 1024**2,
        "peakReservedMiB": torch.cuda.max_memory_reserved() / 1024**2,
        "gpu": torch.cuda.get_device_name(), "torch": torch.__version__, "attention": config["attention"],
        "dtype": config["dtype"], "cacheHit": False, "contentReview": "NeedReview", "cloudCalls": 0}
    Path(str(output) + ".qwen.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
