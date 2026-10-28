"""One local acceptance run through VideoStudio APIs and its real task queue.

Creates fresh SD1.5/LTX/TTS baseline assets, waits for pinned H3 downloads,
then submits one H3 audio-video job. Never approves content or publication.
No password/API key is read, reset or stored. Requires explicit LocalOnly mode.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse
import uuid

import requests
from download_assets import atomic_replace, download_lock


class TaskFailure(RuntimeError):
    def __init__(self, task_id: int, status: str, message: str):
        super().__init__(message)
        self.task_id = task_id
        self.status = status


class Acceptance:
    def __init__(self, base: str, report: Path):
        url = urlparse(base)
        if url.scheme not in {"http", "https"} or url.username or url.password or url.query or url.fragment:
            raise ValueError("A plain loopback API endpoint is required")
        if url.hostname != "localhost" and not ipaddress.ip_address(url.hostname or "").is_loopback:
            raise ValueError("Only the local VideoStudio API can be used")
        self.base = base.rstrip("/")
        self.report = report.resolve()
        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.trust_env = False
        if report.exists():
            self.state = json.loads(report.read_text(encoding="utf-8"))
            if self.state.get("schemaVersion") != 1 or not self.state.get("runId"):
                raise ValueError("Unrecognized existing acceptance report; preserved")
        else:
            self.state = {"schemaVersion": 1, "runId": uuid.uuid4().hex, "stage": "Starting", "technicalStatus": "Blocked", "contentStatus": "NeedReview", "publicationStatus": "Blocked"}

    def save(self, stage: str | None = None, **values):
        changed = stage is not None and stage != self.state.get("stage")
        if stage is not None:
            self.state["stage"] = stage
        self.state.update(values)
        self.state["updatedAt"] = datetime.now(timezone.utc).isoformat()
        temporary = self.report.with_name(self.report.name + ".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        atomic_replace(temporary, self.report)
        if changed:
            print(f"acceptance stage={stage}", flush=True)

    def api(self, path: str, body: dict | None = None, key: str | None = None, timeout: int = 30):
        headers = {"Origin": self.base}
        if key:
            headers["Idempotency-Key"] = f"minimax-acceptance:{self.state['runId']}:{key}"
        try:
            response = self.session.request("POST" if body is not None else "GET", self.base + path, json=body, headers=headers, timeout=timeout)
        except requests.RequestException:
            raise RuntimeError("Local API response unavailable; query the recorded task before retrying. No automatic submission retry was performed.") from None
        try:
            data = response.json()
        except ValueError:
            raise RuntimeError(f"Local API returned non-JSON: HTTP {response.status_code}") from None
        if not response.ok:
            checks = data.get("preflight", {}).get("issues", [])
            detail = "; ".join(str(issue) for issue in checks)
            raise RuntimeError(f"Local API HTTP {response.status_code}: {str(data.get('error', 'request rejected'))[:300]} {detail[:500]}")
        return data

    def access(self):
        status = self.api("/api/auth/status")
        if status.get("loginRequired", True) or status.get("accessMode") != "LocalOnly":
            raise RuntimeError("This run needs the user-authorized LocalOnly access mode; no login will be bypassed")
        self.session.headers["X-CSRF-Token"] = status["csrfToken"]
        if not self.api("/api/production/schema").get("ready"):
            raise RuntimeError("Production queue schema is not ready; no migration was attempted")
        if not self.api("/api/minimax/local/status")["queue"]["enabled"]:
            raise RuntimeError("The existing generation Worker must be enabled before this acceptance run")

    def poll(self, task_id: int, limit: int = 2100):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            detail = self.api(f"/api/tasks/{task_id}")
            status = detail["task"]["status"]
            if status == "Succeeded":
                return detail
            if status in {"Failed", "Cancelled"}:
                raise TaskFailure(task_id, status, f"Task {task_id} ended as {status}: {str(detail['task'].get('errorMessage') or '')[:500]}; no automatic regeneration")
            time.sleep(3)
        raise RuntimeError(f"Task {task_id} is still unresolved; inspect its state before retrying")

    def task(self, field: str, stage: str, payload: dict):
        if not self.state.get(field):
            self.save(stage)
            payload["requestId"] = f"{self.state['runId']}:{field}"
            result = self.api("/api/tasks", payload, key=field, timeout=120)
            self.save(**{field: result.get("id") or result.get("taskId")})
        return self.poll(self.state[field])

    @staticmethod
    def result(detail: dict, extensions: tuple[str, ...]):
        return next((item for item in detail["results"] if item.get("available") and str(item.get("assetPath") or "").lower().endswith(extensions)), None)

    def run(self):
        if self.state.get("stage") == "AwaitingContentReview":
            print("Existing acceptance run is complete; generated assets and report preserved.", flush=True)
            return
        self.access()
        self.save(error=None)
        workflows = self.api("/api/workflows")
        lookup = {item["name"]: item["id"] for item in workflows}
        scene = lookup.get("06_scene_keyframe_quality_api")
        ltx = lookup.get("02_ltx_i2v_quality_api")
        if not scene or not ltx:
            raise RuntimeError("The existing SD1.5/LTX baseline workflows are not registered")
        if not self.state.get("projectId"):
            name = "MiniMax本地接入验收_" + self.state["runId"][:8]
            existing = [item for item in self.api("/api/projects") if item["name"] == name]
            if len(existing) == 1:
                self.save(projectId=existing[0]["id"])
            elif self.state.get("projectSubmissionStarted"):
                raise RuntimeError("Project submission outcome is unresolved; inspect projects before creating another")
            else:
                self.save("CreatingProject", projectSubmissionStarted=True)
                created = self.api("/api/projects", {"name": name, "description": "Fresh local integration fixtures. Technical execution, content review and release eligibility remain separate.", "defaultWidth": 1280, "defaultHeight": 720, "defaultFps": 24})
                self.save(projectId=created["id"])
        project = self.state["projectId"]
        still_prompt = "Cinematic medium shot of one fictional adult woman with short black hair, plain blue shirt, seated near a bright window. Her face and both hands are visible, hands resting naturally. Calm expression, natural skin, soft daylight, coherent room, wide horizontal composition."
        motion = "One continuous locked camera shot. The woman keeps the same identity, clothes and room. She slowly raises her right hand, makes one small friendly wave, then lowers it. Natural subtle motion."
        frame = self.task("keyframeTaskId", "GeneratingKeyframe", {
            "projectId": project, "taskType": "Image", "resourceClass": "GPU", "workflowId": scene,
            "stage": "MiniMax-Benchmark-Keyframe", "maxRetries": 0,
            "parameters": {"prompt": still_prompt, "negative": "multiple people, extra limbs, deformed hands, watermark, text, collage, blurry face", "width": 864, "height": 480, "seed": 2026101801, "steps": 25, "cfg": 6}
        })
        image = self.result(frame, (".png", ".jpg", ".webp"))
        if image is None or image.get("width") != 864 or image.get("height") != 480:
            raise RuntimeError("Fresh first frame did not meet the declared 864x480 geometry; no implicit resize or old media reuse")
        image_path = image["assetPath"]
        self.save(frameAssetPath=image_path)
        try:
            baseline = self.task("baselineV2TaskId", "GeneratingBaseline", {
                "projectId": project, "taskType": "ImageToVideo", "resourceClass": "GPU", "workflowId": ltx,
                "inputImagePath": image_path, "stage": "MiniMax-Baseline-LTX", "maxRetries": 0,
                "parameters": {"workflowVersion": "02_ltx_i2v_quality_api.comfy031-v2", "inputSlots": {"firstFrame": image_path}, "prompt": motion,
                               "changeReason": "ComfyUI 0.31 unguided LTX mapping: execute the full 121 frames; previous task 1157 emitted 113 and failed the exact-frame gate.",
                               "width": 512, "height": 320, "frames": 121, "fps": 24, "steps": 8, "seed": 2026101802, "qualityReferenceImagePath": image_path}
            })
            baseline_video = self.result(baseline, (".mp4",))
            if baseline_video is None:
                raise RuntimeError("The LTX task completed without an available MP4 artifact")
            self.save(baselineTechnicalStatus="Passed", baselineVersion="02_ltx_i2v_quality_api.comfy031-v2", baselineError=None, baselineVideoAssetPath=baseline_video["assetPath"])
        except RuntimeError as error:
            self.save(baselineTechnicalStatus="Failed", baselineError=str(error)[:500])
        try:
            if not self.state.get("localTtsTaskId"):
                self.save("GeneratingLocalTts")
                tts = self.api("/api/audio/tts", {"projectId": project, "text": "你好，我会轻轻挥手，欢迎来到本地视频工作台。", "voiceId": "", "speed": 1, "pitch": 0}, key="local-tts", timeout=120)
                self.save(localTtsTaskId=tts.get("taskId") or tts.get("id"))
            spoken = self.poll(self.state["localTtsTaskId"])
            spoken_audio = self.result(spoken, (".wav", ".mp3"))
            if spoken_audio is None:
                raise RuntimeError("The local TTS task completed without an available audio artifact")
            self.save(localTtsTechnicalStatus="Passed", localTtsAudioAssetPath=spoken_audio["assetPath"])
        except RuntimeError as error:
            self.save(localTtsTechnicalStatus="Failed", localTtsError=str(error)[:500])
        self.save("WaitingForModels", baselineContentStatus="NeedReview")
        deadline = time.monotonic() + 12 * 60 * 60
        while time.monotonic() < deadline:
            status = self.api("/api/minimax/local/status")
            self.save(downloadedBytes=status["downloadedBytes"], totalBytes=status["totalBytes"])
            if status["modelsPresent"]:
                break
            time.sleep(30)
        else:
            raise RuntimeError("Pinned models are still incomplete after the bounded wait; preserve partial downloads and resume explicitly")
        self.access()
        self.save("VerifyingModels")
        self.api("/api/minimax/local/register", {})
        self.api("/api/minimax/local/verify", {}, timeout=600)
        self.save("GeneratingH3")
        if not self.state.get("h3TaskId"):
            h3 = self.api("/api/minimax/local/video", {"projectId": project, "inputImagePath": image_path, "seed": 2026101802,
                          "prompt": motion + ' Audio: quiet room ambience. During the wave she clearly says in Mandarin, "你好，欢迎一起学习。" Calm natural voice. No music, no other speakers, no subtitles.'}, key="h3", timeout=600)
            self.save(h3TaskId=h3["id"])
        generated = self.poll(self.state["h3TaskId"])
        video = self.result(generated, (".mp4",))
        audio = self.result(generated, (".wav",))
        if video is None or audio is None:
            raise RuntimeError("H3 task lacks separately registered video/audio artifacts")
        self.save("AwaitingContentReview", technicalStatus="Passed", contentStatus="NeedReview", publicationStatus="Blocked",
                  h3VideoAssetPath=video["assetPath"], h3AudioAssetPath=audio["assetPath"])
        print("Technical H3 audio/video execution completed. Human content review is required; no publishing approval was granted.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--report", type=Path, default=Path(r"C:\install\AI\Data\MiniMaxLocal\integration-run.json"))
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(args.report.parent, ".minimax-acceptance.lock", "Another local acceptance run is already active"):
        run = Acceptance(args.base_url, args.report)
        try:
            run.run()
        except Exception as error:
            result = "Failed" if isinstance(error, TaskFailure) and error.status == "Failed" else "Blocked"
            values = {"error": str(error)[:1000], "technicalStatus": result}
            if isinstance(error, TaskFailure):
                values.update(failedTaskId=error.task_id, executionStatus=error.status)
            run.save(result, **values)
            print(f"Acceptance {result}: {type(error).__name__}: {str(error)[:500]}", flush=True)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
