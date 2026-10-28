"""Verify the deployed API against the completed sample without new model inference."""
import hashlib
import json
from pathlib import Path
import time
import requests

DATA = Path(__file__).resolve().parents[3] / "Data"
EVIDENCE = DATA / "Qwen3Tts20261022"
BASE = "http://127.0.0.1:18080"


def main():
    state = json.loads((EVIDENCE / "run.json").read_text(encoding="utf-8"))
    if state.get("stage") != "ReadyForUserPreview":
        raise RuntimeError("A completed real sample is required")
    session = requests.Session()
    session.trust_env = False
    access = session.get(BASE + "/api/auth/status", timeout=10).json()
    session.headers["X-CSRF-Token"] = access["csrfToken"]
    body = {"projectId": state["projectId"], "voiceId": state["voiceId"], "text": state["text"],
        "instruction": state["instruction"], "speed": 1, "pitch": 0, "outputName": "qwen3_chinese_preview.wav"}
    checks = []
    def check(condition, name):
        if not condition: raise AssertionError(name)
        checks.append({"name": name, "status": "Passed"})
    existing = session.post(BASE + "/api/audio/tts", json=body, headers={"Idempotency-Key": "qwen3-local-chinese-preview-20261022-v1"}, timeout=20)
    check(existing.status_code == 202 and existing.json()["taskId"] == state["taskId"], "same request returns the existing task")
    changed = session.post(BASE + "/api/audio/tts", json={**body, "text": "这是不同的文本。"}, headers={"Idempotency-Key": "qwen3-local-chinese-preview-20261022-v1"}, timeout=20)
    check(changed.status_code == 409, "changed payload cannot reuse an idempotency key")
    before_ids = {x["id"] for x in session.get(BASE + "/api/audio/history?limit=100", timeout=10).json()}
    for name, patch, status in [
        ("unknown voice", {"voiceId": "qwen3:missing"}, 422), ("empty text", {"text": ""}, 400),
        ("overlong text", {"text": "中" * 501}, 422), ("overlong instruction", {"instruction": "中" * 301}, 422),
        ("unsupported numeric speed", {"speed": 1.2}, 422), ("unsupported numeric pitch", {"pitch": 1}, 422),
        ("missing project", {"projectId": None}, 400)
    ]:
        response = session.post(BASE + "/api/audio/tts", json={**body, **patch}, timeout=20)
        check(response.status_code == status, name)
    after_ids = {x["id"] for x in session.get(BASE + "/api/audio/history?limit=100", timeout=10).json()}
    check(before_ids == after_ids, "rejected requests do not create generation tasks")
    catalog = session.get(BASE + "/api/audio/voices", timeout=10).json()
    generic = {"projectId": state["projectId"], "taskType": "Audio", "resourceClass": "CPU", "parameters": {**body, "engineVersion": catalog["engineVersion"]}}
    preflight = session.post(BASE + "/api/tasks/preflight", json=generic, timeout=20).json()
    check(not preflight["passed"], "Qwen on CPU queue is rejected")
    generic["resourceClass"] = "GPU"
    generic["parameters"]["engineVersion"] = "outdated-version"
    preflight = session.post(BASE + "/api/tasks/preflight", json=generic, timeout=20).json()
    check(not preflight["passed"], "stale engine version is rejected")
    windows = session.post(BASE + "/api/audio/preflight", json={"voiceId": "Huihui"}, timeout=20).json()
    check(windows["passed"], "existing Windows Chinese TTS still synthesizes a valid preflight WAV")

    cached = session.post(BASE + "/api/audio/tts", json=body, headers={"Idempotency-Key": "qwen3-local-cache-check-20261022-v1"}, timeout=20)
    check(cached.status_code == 202, "cached-copy task submitted through the formal queue")
    task_id = cached.json()["taskId"]
    for _ in range(60):
        detail = session.get(BASE + f"/api/tasks/{task_id}", timeout=10).json()
        if detail["task"]["status"] in {"Succeeded", "Failed", "Cancelled"}: break
        time.sleep(1)
    check(detail["task"]["status"] == "Succeeded", "cached-copy task succeeded")
    audio = next(r for r in detail["results"] if str(r.get("assetPath", "")).endswith(".wav"))
    receipt = next(r for r in detail["results"] if str(r.get("assetPath", "")).endswith(".json"))
    metadata = session.get(BASE + receipt["mediaUrl"], timeout=10).json()
    check(metadata["cacheHit"] is True, "same text, voice and instruction reuse validated audio without model inference")
    original = DATA / state["audio"]["assetPath"]
    repeated = DATA / audio["assetPath"]
    check(hashlib.sha256(original.read_bytes()).digest() == hashlib.sha256(repeated.read_bytes()).digest(), "cached WAV is byte-identical")
    report = {"checks": checks, "cacheTaskId": task_id, "cacheDurationMs": detail["task"]["durationMs"]}
    (EVIDENCE / "api-checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": len(checks), "cacheTaskId": task_id, "cacheDurationMs": detail["task"]["durationMs"]}))


if __name__ == "__main__": main()
