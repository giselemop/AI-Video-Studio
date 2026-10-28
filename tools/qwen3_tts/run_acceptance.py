"""Generate one reviewable Chinese sample through the real VideoStudio queue; safe to resume."""
from __future__ import annotations

import json
from pathlib import Path
import time
import requests

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT.parent / "Data/Qwen3Tts20261022"
BASE = "http://127.0.0.1:18080"
TEXT = "午后的阳光穿过树叶，落在安静的校园里。林夏拾起长椅上的红色笔记本，轻声喊道：同学，你的本子忘拿了。"
INSTRUCTION = "用温柔、自然的普通话讲述，语速稍慢，句间停顿清晰，像在讲一个校园故事。"


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    state_path = EVIDENCE / "run.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    session = requests.Session()
    session.trust_env = False
    def api(path, body=None):
        headers = {"Idempotency-Key": "qwen3-local-chinese-preview-20261022-v1"} if body is not None else {}
        response = session.request("POST" if body is not None else "GET", BASE + path, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    def save(**values):
        state.update(values)
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(state_path)
    # Use the existing authorized local-only session, with CSRF; never print its credentials.
    access = api("/api/auth/status")
    if access.get("loginRequired", True):
        raise RuntimeError("Human login is required; no credentials were bypassed")
    session.headers["X-CSRF-Token"] = access["csrfToken"]
    catalog = api("/api/audio/voices")
    if not catalog.get("qwenAvailable"):
        raise RuntimeError(catalog.get("qwenMessage", "Qwen model is not ready"))
    if not state.get("projectId"):
        name = "Qwen3-TTS 本地中文试听 2026-10-22"
        existing = [p for p in api("/api/projects") if p["name"] == name]
        project_id = existing[0]["id"] if existing else api("/api/projects", {"name": name, "description": "Qwen3-TTS 本地中文配音接入与试听，内容等待人工听审。"})["id"]
        save(projectId=project_id, text=TEXT, instruction=INSTRUCTION, voiceId="qwen3:Vivian", stage="Prepared")
    if not state.get("taskId"):
        save(stage="Submitting")
        result = api("/api/audio/tts", {"projectId": state["projectId"], "voiceId": state["voiceId"], "text": state["text"],
            "instruction": state["instruction"], "speed": 1, "pitch": 0, "outputName": "qwen3_chinese_preview.wav"})
        save(taskId=result["taskId"], stage="Generating")
        print("taskId=" + str(result["taskId"]), flush=True)
    started = time.monotonic()
    while time.monotonic() - started < 900:
        detail = api(f"/api/tasks/{state['taskId']}")
        status = detail["task"]["status"]
        if status in {"Failed", "Cancelled"}:
            save(stage=status, task=detail["task"])
            raise RuntimeError(detail["task"].get("errorMessage") or status)
        if status == "Succeeded":
            audio = next(r for r in detail["results"] if r.get("available") and str(r.get("assetPath", "")).endswith(".wav"))
            receipt = next(r for r in detail["results"] if r.get("available") and str(r.get("assetPath", "")).endswith(".json"))
            metadata_response = session.get(BASE + receipt["mediaUrl"], timeout=30)
            metadata_response.raise_for_status()
            metadata = metadata_response.json()
            (EVIDENCE / "inference.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            save(stage="ReadyForUserPreview", task=detail["task"], audio=audio, receipt=receipt,
                 contentReview="NeedReview", durationSeconds=metadata["durationSeconds"])
            print(json.dumps({"stage": state["stage"], "taskId": state["taskId"], "assetPath": audio["assetPath"],
                "durationSeconds": metadata["durationSeconds"], "inferenceSeconds": metadata["inferenceSeconds"],
                "peakReservedMiB": metadata["peakReservedMiB"]}), flush=True)
            return
        time.sleep(2)
    raise RuntimeError("Sample is still pending; resume to query the same task")


if __name__ == "__main__":
    main()
