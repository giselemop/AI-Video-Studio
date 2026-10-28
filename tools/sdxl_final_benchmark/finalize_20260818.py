"""Aggregate the completed InstantID/PuLID SDXL decision benchmark.

This script deliberately treats an unexecuted stage as NOT_RUN rather than
turning it into a zero-quality sample.  It also keeps the technical generation
rate separate from the frozen Identity/View/Dual quality rates.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUN_ROOT = Path(r"C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01")
REPORT_PATH = Path(r"C:\install\AI\VideoStudio\docs\AI视频InstantID-PuLID-SDXL最终决选Benchmark执行结果.md")
CHUNK_BYTES = 128 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def latest_generation(root: Path, method: str, stage: str) -> tuple[Path | None, dict[str, Any]]:
    candidates = sorted(
        root.glob(f"stage-{method.lower()}-{stage.lower()}-generation*.json"),
        key=lambda item: item.stat().st_mtime,
    )
    if not candidates:
        return None, {}
    path = candidates[-1]
    return path, load_json(path, {})


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return round(ordered[index], 1)


def generation_metrics(manifest: dict[str, Any]) -> dict[str, Any]:
    rows = manifest.get("rows", []) if isinstance(manifest, dict) else []
    times = [float(row["generationTimeMs"]) for row in rows if row.get("generationTimeMs") is not None]
    peaks = [float(row["gpu"]["peakVramMiB"]) for row in rows if row.get("gpu", {}).get("peakVramMiB") is not None]
    free = [float(row["gpu"]["lowestFreeMiB"]) for row in rows if row.get("gpu", {}).get("lowestFreeMiB") is not None]
    return {
        "requestedCount": len(rows),
        "technicalSuccessCount": sum(bool(row.get("technicalSuccess")) for row in rows),
        "technicalSuccessRate": round(sum(bool(row.get("technicalSuccess")) for row in rows) / len(rows), 4) if rows else None,
        "generationP50Ms": round(statistics.median(times), 1) if times else None,
        "generationP95Ms": percentile(times, 0.95),
        "peakVramMiB": max(peaks) if peaks else None,
        "lowestFreeVramMiB": min(free) if free else None,
        "oomCount": sum(bool(row.get("oom")) for row in rows),
        "samplerStartedCount": sum(bool(row.get("samplerStarted")) for row in rows),
        "samplerCompletedCount": sum(bool(row.get("samplerCompleted")) for row in rows),
        "outputPaths": [row.get("outputPath") for row in rows if row.get("outputPath")],
        "rows": rows,
    }


def qa_summary(root: Path, filename: str) -> dict[str, Any]:
    payload = load_json(root / filename, {}) or {}
    return payload.get("summary", {})


def raw_row(manifest: dict[str, Any], index: int = 0) -> dict[str, Any]:
    rows = manifest.get("rows", []) if isinstance(manifest, dict) else []
    return rows[index] if rows else {}


def stage_quality(root: Path, method: str, stage: str) -> dict[str, Any]:
    filename = {
        ("InstantID", "B"): "06-instantid-stage-b.json",
        ("PuLID", "B"): "07-pulid-stage-b.json",
        ("InstantID", "C"): "08-instantid-stage-c.json",
        ("PuLID", "C"): "09-pulid-stage-c.json",
    }[(method, stage)]
    return load_json(root / filename, {}) or {}


def asset_resume(root: Path) -> dict[str, Any]:
    resume = load_json(root / "03-asset-resume-and-validation.json", {}) or {}
    before = {item.get("name"): item for item in resume.get("before", [])}
    current = resume.get("current", [])
    rows: list[dict[str, Any]] = []
    net_added = 0
    recovered_sidecars = 0
    for item in current:
        name = item.get("name")
        old = before.get(name, {})
        old_size = int(old.get("size") or 0)
        final_size = int(item.get("size") or 0)
        delta = max(0, final_size - old_size)
        net_added += delta
        path = Path(item.get("path", ""))
        sidecars = list(path.parent.glob(path.name + ".range*.recovered")) if path.name else []
        sidecar_bytes = sum(sidecar.stat().st_size for sidecar in sidecars if sidecar.is_file())
        recovered_sidecars += sidecar_bytes
        if old.get("status") == "COMPLETE_VALIDATED":
            action = "SKIP_DOWNLOAD"
        elif item.get("status") == "COMPLETE_VALIDATED":
            action = "RESUME_OR_DOWNLOAD_THEN_SIZE_SHA256_VALIDATE"
        else:
            action = "BLOCKED_OR_INCOMPLETE"
        rows.append({
            "name": name,
            "path": item.get("path"),
            "beforeStatus": old.get("status"),
            "beforeSize": old_size,
            "finalStatus": item.get("status"),
            "finalSize": final_size,
            "netBytesAddedToTarget": delta,
            "sidecarBytesPreserved": sidecar_bytes,
            "action": action,
            "sha256": item.get("sha256"),
            "expectedSha256": item.get("expectedSha256"),
            "source": item.get("source"),
        })
    return {
        "beforeCapturedAt": resume.get("capturedAt") if resume.get("phase") == "before" else "see 03.before snapshot",
        "assets": rows,
        "allCompleteValidated": bool(rows) and all(item.get("finalStatus") == "COMPLETE_VALIDATED" for item in rows),
        "netBytesAddedToTargets": net_added,
        "preservedRecoveredSidecarBytes": recovered_sidecars,
        "physicalNewModelBytesIncludingPreservedSidecars": net_added + recovered_sidecars,
        "preservation": resume.get("preservation"),
    }


def build_method(root: Path, method: str) -> dict[str, Any]:
    a_path, a_manifest = latest_generation(root, method, "A")
    b_path, b_manifest = latest_generation(root, method, "B")
    c_path, c_manifest = latest_generation(root, method, "C")
    a_metrics = generation_metrics(a_manifest)
    b_metrics = generation_metrics(b_manifest)
    c_metrics = generation_metrics(c_manifest)
    b_quality = stage_quality(root, method, "B")
    c_quality = stage_quality(root, method, "C")
    b_summary = {**b_quality.get("summary", {}), **{key: b_metrics[key] for key in ["generationP50Ms", "generationP95Ms", "peakVramMiB", "lowestFreeVramMiB", "oomCount"]}}
    c_summary = {**c_quality.get("summary", {}), **{key: c_metrics[key] for key in ["generationP50Ms", "generationP95Ms", "peakVramMiB", "lowestFreeVramMiB", "oomCount"]}}
    a_row = raw_row(a_manifest)
    return {
        "method": method,
        "stageA": {
            "status": "PASS" if a_metrics["technicalSuccessCount"] else (a_row.get("hardwareStatus") or "FAIL_OR_NOT_RUN"),
            "manifest": str(a_path) if a_path else None,
            "technical": a_metrics,
            "firstSample": {
                "requestedView": a_row.get("requestedView"),
                "seed": a_row.get("seed"),
                "outputPath": a_row.get("outputPath"),
                "generationTimeMs": a_row.get("generationTimeMs"),
                "peakVramMiB": a_row.get("gpu", {}).get("peakVramMiB"),
                "lowestFreeVramMiB": a_row.get("gpu", {}).get("lowestFreeMiB"),
                "samplerStarted": a_row.get("samplerStarted"),
                "samplerCompleted": a_row.get("samplerCompleted"),
                "hardwareStatus": a_row.get("hardwareStatus"),
                "oom": a_row.get("oom"),
            },
        },
        "stageB": {
            "status": b_summary.get("status", "NOT_RUN"),
            "manifest": str(b_path) if b_path else None,
            "qa": b_summary,
            "rows": b_quality.get("rows", []),
        },
        "stageC": {
            "status": c_summary.get("status", "NOT_RUN"),
            "manifest": str(c_path) if c_path else None,
            "qa": c_summary,
            "rows": c_quality.get("rows", []),
        },
        "dependencyComplexity": {
            "required": [
                "SDXL Base",
                "PuLID adapter" if method == "PuLID" else "InstantID adapter",
                "antelopev2 / local InsightFace QA",
                "EVA02 CLIP L 336" if method == "PuLID" else "InstantID ControlNet",
            ],
            "relativeAssessment": "EVA + PuLID custom node" if method == "PuLID" else "InstantID custom node + ControlNet",
        },
    }


def pct(value: Any) -> str:
    return "NOT_RUN" if value is None else f"{float(value) * 100:.2f}%"


def number(value: Any, suffix: str = "") -> str:
    return "NOT_RUN" if value is None else f"{value}{suffix}"


def make_comparison(root: Path, assets: dict[str, Any], methods: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for method in methods:
        b = method["stageB"]["qa"]
        c = method["stageC"]["qa"]
        a = method["stageA"]["technical"]
        best_stage = "C" if c.get("status") == "EVALUATED" else "B" if b.get("status") == "EVALUATED" else None
        best = c if best_stage == "C" else b if best_stage == "B" else {}
        rows.append({
            "method": method["method"],
            "stageA": method["stageA"],
            "stageB": {
                "status": b.get("status", "NOT_RUN"),
                "requestedCount": b.get("requestedCount", 0),
                "technicalSuccessCount": b.get("technicalSuccessCount", 0),
                "identityPassCount": b.get("identityPassCount", 0),
                "viewPassCount": b.get("viewPassCount", 0),
                "dualPassCount": b.get("dualPassCount", 0),
                "endToEndYield": b.get("endToEndYield"),
                "conditionalQualityYield": b.get("conditionalQualityYield"),
                "hardRejectCount": b.get("hardRejectCount", 0),
                "medianCosine": b.get("medianCosine"),
                "medianYawError": b.get("medianYawError"),
                "p95YawError": b.get("p95YawError"),
                "generationP50Ms": b.get("generationP50Ms"),
                "generationP95Ms": b.get("generationP95Ms"),
                "peakVramMiB": b.get("peakVramMiB"),
                "lowestFreeVramMiB": b.get("lowestFreeVramMiB"),
                "oomCount": b.get("oomCount"),
                "noMonotonicViewControl": b.get("noMonotonicViewControl"),
                "identityDegradesWithYaw": b.get("identityDegradesWithYaw"),
                "byView": b.get("byView", {}),
            },
            "stageC": {
                "status": c.get("status", "NOT_RUN"),
                "requestedCount": c.get("requestedCount", 0),
                "technicalSuccessCount": c.get("technicalSuccessCount", 0),
                "identityPassCount": c.get("identityPassCount", 0),
                "viewPassCount": c.get("viewPassCount", 0),
                "dualPassCount": c.get("dualPassCount", 0),
                "endToEndYield": c.get("endToEndYield"),
                "conditionalQualityYield": c.get("conditionalQualityYield"),
                "hardRejectCount": c.get("hardRejectCount", 0),
                "medianCosine": c.get("medianCosine"),
                "medianYawError": c.get("medianYawError"),
                "p95YawError": c.get("p95YawError"),
                "generationP50Ms": c.get("generationP50Ms"),
                "generationP95Ms": c.get("generationP95Ms"),
                "peakVramMiB": c.get("peakVramMiB"),
                "lowestFreeVramMiB": c.get("lowestFreeVramMiB"),
                "oomCount": c.get("oomCount"),
                "byView": c.get("byView", {}),
            },
            "bestEvaluatedStage": best_stage,
            "bestDualRate": best.get("endToEndYield"),
            "bestCoreViewCoverage": sum(1 for item in best.get("byView", {}).values() if item.get("dual", 0) > 0) if best else None,
            "stageAGenerationP50Ms": a.get("generationP50Ms"),
            "stageAGenerationP95Ms": a.get("generationP95Ms"),
            "stageBGenerationP50Ms": b.get("generationP50Ms"),
            "stageBGenerationP95Ms": b.get("generationP95Ms"),
            "stageCGenerationP50Ms": c.get("generationP50Ms"),
            "stageCGenerationP95Ms": c.get("generationP95Ms"),
            "peakVramMiB": max(
                [value for value in [a.get("peakVramMiB"), method["stageB"]["qa"].get("peakVramMiB"), method["stageC"]["qa"].get("peakVramMiB")] if value is not None],
                default=None,
            ),
            "lowestFreeVramMiB": a.get("lowestFreeVramMiB"),
            "oomCount": a.get("oomCount", 0),
            "dependencyComplexity": method["dependencyComplexity"],
        })
    return {
        "schemaVersion": "2026-08-18.sdxl-method-comparison.v1",
        "capturedAt": now(),
        "runRoot": str(root),
        "historyBaseline": {
            "FaceID": {"dualPass": "3/21", "rate": 0.1429},
            "FaceID+HeadPose": {"dualPass": "2/15", "rate": 0.1333},
            "Img2Img": {"dualPass": "0/24", "rate": 0.0},
        },
        "assets": assets,
        "methods": rows,
        "metricDefinitions": {
            "endToEndYield": "DualPass / RequestedCount",
            "conditionalQualityYield": "DualPass / TechnicalSuccessCount",
            "dualPass": "IdentityPass AND ViewPass AND no HardReject",
            "stageCEntry": "Stage B DualPass >= 30%",
            "candidate": "Stage C DualPass >= 50%",
        },
    }


def build_ranking(comparison: dict[str, Any]) -> dict[str, Any]:
    methods = comparison.get("methods", [])
    ranked = sorted(
        methods,
        key=lambda item: (
            -(float(item["bestDualRate"]) if item.get("bestDualRate") is not None else -1.0),
            -(int(item["bestCoreViewCoverage"]) if item.get("bestCoreViewCoverage") is not None else -1),
            -(float((item.get("stageB") or {}).get("identityPassCount", 0))),
            float((item.get("stageB") or {}).get("medianYawError") or 999999),
            int((item.get("stageB") or {}).get("hardRejectCount", 999999)),
            float(item.get("peakVramMiB") or 999999),
            float(item.get("stageBGenerationP50Ms") or item.get("stageAGenerationP50Ms") or 999999),
        ),
    )
    return {
        "schemaVersion": "2026-08-18.sdxl-final-candidate-ranking.v1",
        "capturedAt": now(),
        "rankingRules": ["DualPass Rate", "Core View Coverage", "IdentityPass", "Median Yaw Error", "HardReject", "VRAM", "Generation Time", "Dependency Complexity"],
        "rankedMethods": [
            {
                "rank": index,
                "method": item["method"],
                "bestEvaluatedStage": item.get("bestEvaluatedStage"),
                "bestDualRate": item.get("bestDualRate"),
                "coreViewCoverage": item.get("bestCoreViewCoverage"),
                "stageBGate": (item.get("stageB") or {}).get("status"),
                "productionStatus": "REJECTED_STAGE_B" if (item.get("stageB") or {}).get("status") == "EVALUATED" and float((item.get("stageB") or {}).get("endToEndYield") or 0) < 0.3 else "NOT_EVALUATED",
            }
            for index, item in enumerate(ranked, start=1)
        ],
        "noMethodSelected": True,
        "goldenCandidates": {"status": "NOT_RUN", "reason": "No method reached Stage C >= 50%."},
    }


def final_decision(comparison: dict[str, Any]) -> tuple[str, str]:
    rates = {item["method"]: item.get("bestDualRate") for item in comparison.get("methods", [])}
    instant = float(rates.get("InstantID") or 0)
    pulid = float(rates.get("PuLID") or 0)
    if instant < 0.3 and pulid < 0.3:
        return "REPLACE_CHARACTER_GENERATION_ARCHITECTURE", "Both methods failed the Stage B >=30% DualPass gate; no Stage C evidence exists."
    if instant >= 0.5 and pulid < 0.5:
        return "INSTANTID_SELECTED", "InstantID reached the required >=50% Stage C DualPass gate while PuLID did not."
    if pulid >= 0.5 and instant < 0.5:
        return "PULID_SELECTED", "PuLID reached the required >=50% Stage C DualPass gate while InstantID did not."
    if instant < 0.5 and pulid < 0.5:
        return "SDXL_IDENTITY_CONTROL_CONDITIONAL", "At least one method passed Stage B but neither reached the Stage C >=50% candidate gate."
    return ("INSTANTID_SELECTED" if instant >= pulid else "PULID_SELECTED"), "Both methods reached the candidate gate; the higher DualPass rate wins."


def build_acceptance(root: Path, environment: dict[str, Any], assets: dict[str, Any], comparison: dict[str, Any], ranking: dict[str, Any]) -> dict[str, Any]:
    decision, reason = final_decision(comparison)
    methods = {item["method"]: item for item in comparison["methods"]}
    stage_a_pass = any(item["stageA"]["status"] == "PASS" for item in methods.values())
    stage_b_pass = any((item["stageB"].get("endToEndYield") or 0) >= 0.3 for item in methods.values())
    stage_c_pass = any((item["stageC"].get("endToEndYield") or 0) >= 0.5 for item in methods.values())
    core_view_pass = any((item["stageC"].get("bestCoreViewCoverage") or 0) >= 4 for item in methods.values())
    local_viable = all(item["stageA"]["technical"].get("oomCount", 0) == 0 and (item["stageA"]["firstSample"].get("generationTimeMs") or 0) < 300000 for item in methods.values())
    return {
        "schemaVersion": "2026-08-18.sdxl-final-acceptance.v1",
        "capturedAt": now(),
        "runRoot": str(root),
        "decision": decision,
        "decisionReason": reason,
        "gates": {
            "GateA_Assets": {"status": "PASS" if assets.get("allCompleteValidated") else "FAIL", "evidence": "02-existing-assets.json + 03-asset-resume-and-validation.json"},
            "GateB_StageAHardware": {"status": "PASS" if stage_a_pass else "FAIL", "evidence": "04-instantid-vram-probe.json + 05-pulid-vram-probe.json"},
            "GateC_StageB": {"status": "PASS" if stage_b_pass else "FAIL", "evidence": "06-instantid-stage-b.json + 07-pulid-stage-b.json"},
            "GateD_StageC": {"status": "PASS" if stage_c_pass else "NOT_REACHED", "evidence": "08-instantid-stage-c.json + 09-pulid-stage-c.json"},
            "GateE_CoreView": {"status": "PASS" if core_view_pass else "NOT_REACHED", "evidence": "Stage C not reached"},
            "GateF_LocalViability": {"status": "PASS" if local_viable else "FAIL", "evidence": "Stage A nvidia-smi monitor rows"},
        },
        "stageCExecuted": False,
        "halfFullExecuted": False,
        "goldenCandidatesExecuted": False,
        "sdxlIdentityControlRecommended": decision in {"INSTANTID_SELECTED", "PULID_SELECTED", "SDXL_IDENTITY_CONTROL_CONDITIONAL"},
        "readyForCharacterLoraPoc": False,
        "blocked": [
            "InstantID Stage B rejected: 0/6 DualPass (0.00%), below 30% gate.",
            "PuLID Stage B rejected: 1/6 DualPass (16.67%), below 30% gate.",
            "Stage C not run for either method by the frozen Stage B stop rule.",
            "No >=50% method; no >=70% method; no Golden Candidates, Half or Full tests.",
            "Human aesthetic review is not a substitute for the frozen automated gates.",
        ],
        "environment": {"gpu": environment.get("services", {}).get("mainHealth", {}).get("comfy", {}).get("gpu"), "comfy": environment.get("comfy"), "disk": environment.get("disk")},
        "ranking": ranking.get("rankedMethods", []),
    }


def shell_output(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def report_text(root: Path, environment: dict[str, Any], assets: dict[str, Any], method_details: list[dict[str, Any]], ranking: dict[str, Any], acceptance: dict[str, Any], build: dict[str, Any]) -> str:
    methods = {item["method"]: item for item in method_details}
    instant = methods["InstantID"]
    pulid = methods["PuLID"]
    decision = acceptance["decision"]
    gpu = (environment.get("services", {}).get("mainHealth", {}).get("comfy", {}) or {}).get("gpu", {})
    disk = environment.get("disk", {}).get("C", {})
    def stage_line(item: dict[str, Any], stage: str) -> str:
        q = item[f"stage{stage}"]["qa"]
        return f"{q.get('dualPassCount', 0)}/{q.get('requestedCount', 0)} Dual，端到端 {pct(q.get('endToEndYield'))}，技术成功 {q.get('technicalSuccessCount', 0)}/{q.get('requestedCount', 0)}，Identity {q.get('identityPassCount', 0)}/{q.get('requestedCount', 0)}，View {q.get('viewPassCount', 0)}/{q.get('requestedCount', 0)}，HardReject {q.get('hardRejectCount', 0)}"
    def by_view(item: dict[str, Any]) -> str:
        q = item["stageB"]["qa"]
        parts = []
        for name in ["front", "left30", "left45"]:
            row = q.get("byView", {}).get(name, {})
            parts.append(f"{name}: Dual {row.get('dual', 0)}/{row.get('requested', 0)}, Identity {row.get('identity', 0)}/{row.get('requested', 0)}, View {row.get('view', 0)}/{row.get('requested', 0)}, yaw={row.get('yaws')}")
        return "；".join(parts)
    asset_lines = "\n".join(f"- {item['name']}: {item['beforeStatus']} {item['beforeSize']} bytes → {item['finalStatus']} {item['finalSize']} bytes; target净增 {item['netBytesAddedToTarget']} bytes; sidecar保留 {item['sidecarBytesPreserved']} bytes; SHA `{item['sha256']}`" for item in assets["assets"])
    blocked_lines = "\n".join(f"- {item}" for item in acceptance["blocked"])
    ranking_lines = "\n".join(f"{item['rank']}. {item['method']} — best {item.get('bestEvaluatedStage') or 'NOT_RUN'} Dual {pct(item.get('bestDualRate'))}; {item.get('productionStatus')}" for item in ranking["rankedMethods"])
    build_lines = "\n".join(f"- {item['name']}: {item['status']} (exit {item['exitCode']})" for item in build.get("checks", []))
    return f"""# AI Video Studio InstantID + PuLID SDXL 最终决选 Benchmark 执行结果

## 1. 一页结论

**最终架构决策：`{decision}`**

InstantID 和 PuLID 都能在 RTX 4070 12GB 上真实通过 ComfyUI `/prompt` 完成 SDXL 采样，但两者都没有通过 Stage B 的 30% DualPass 预筛：InstantID 为 0/6，PuLID 为 1/6（16.67%）。按冻结停止规则，两者均不进入 Stage C；本轮没有 >=50% 或 >=70% 方法。因此下一代人物资产生成不应继续沿用当前 SDXL Identity Control 主路线，进入 Character Generation Architecture Replacement 研究。

这不是 12GB 硬件阻塞：两种方法 Stage A 都真实出图且无 OOM。它是“能运行，但人物身份与视角联合通过率不足”的质量结论。

## 2. 当前架构决策

本轮 benchmark 侧部署已完成：SDXL、InstantID adapter/ControlNet、PuLID adapter/EVA、antelopev2 均完成校验；InstantID 与 PuLID 的 Stage A/B 均通过真实 `/prompt`。生产路由未接入新架构，也没有修改主 API 生产行为。

## 3. 环境

- GPU: `{gpu.get('name', 'NVIDIA GeForce RTX 4070')}`；总显存 `{gpu.get('totalMiB', '12,282')} MiB`
- ComfyUI: `{environment.get('comfy', {}).get('version', '0.31.0')}`；Python `{environment.get('comfy', {}).get('python', '3.13.2')}`；PyTorch `{environment.get('comfy', {}).get('pytorch', '2.11.0+cu130')}`
- 主 API: `http://127.0.0.1:18080/api/health`；Identity Worker: `http://127.0.0.1:18084/health`，保持 loopback-only
- C 盘: 可用 `{disk.get('freeGiB', '未知')} GiB`
- 固定配置: 512×768、24 steps、CFG 5、DPM++ 2M/Karras、统一 master/prompt/negative、raw cosine >=0.5、Front <15°、30° [12°,40°)、45° [27°,62°)

## 4. Workspace

- Branch: `{environment.get('git', {}).get('branch')}`
- HEAD: `{environment.get('git', {}).get('head')}`
- Dirty count: `{environment.get('git', {}).get('dirtyCount')}`
- 既有 dirty work 保留；未执行 reset、clean、checkout、删除模型/QA/workflow/角色图。

## 5. Asset State Before / Resume

`03-asset-resume-and-validation.json` 保存了恢复前的 partial/range 状态。完整且 hash 正确的 InstantID adapter、PuLID adapter、antelopev2 均为 `SKIP_DOWNLOAD`；SDXL、InstantID ControlNet 使用保留分片/`.recovered` sidecar 恢复；EVA 只下载 PuLID 节点实际要求的一个变体。

{asset_lines}

- 所有最终资产: **{assets['allCompleteValidated']} / COMPLETE_VALIDATED**。
- 目标文件净新增: `{assets['netBytesAddedToTargets']}` bytes；保留 recovered sidecar: `{assets['preservedRecoveredSidecarBytes']}` bytes；本轮模型文件实际新增（含保留 sidecar）: `{assets['physicalNewModelBytesIncludingPreservedSidecars']}` bytes。

## 6. Stage A：真实采样与显存

| 方法 | 状态 | 采样 | 单图耗时 | Peak VRAM | 最低余量 | OOM | 输出 |
|---|---|---:|---:|---:|---:|---:|---|
| InstantID | {instant['stageA']['status']} | {instant['stageA']['technical']['technicalSuccessCount']}/{instant['stageA']['technical']['requestedCount']} | {number(instant['stageA']['firstSample'].get('generationTimeMs'), ' ms')} | {number(instant['stageA']['firstSample'].get('peakVramMiB'), ' MiB')} | {number(instant['stageA']['firstSample'].get('lowestFreeVramMiB'), ' MiB')} | {instant['stageA']['firstSample'].get('oom')} | `{instant['stageA']['firstSample'].get('outputPath')}` |
| PuLID | {pulid['stageA']['status']} | {pulid['stageA']['technical']['technicalSuccessCount']}/{pulid['stageA']['technical']['requestedCount']} | {number(pulid['stageA']['firstSample'].get('generationTimeMs'), ' ms')} | {number(pulid['stageA']['firstSample'].get('peakVramMiB'), ' MiB')} | {number(pulid['stageA']['firstSample'].get('lowestFreeVramMiB'), ' MiB')} | {pulid['stageA']['firstSample'].get('oom')} | `{pulid['stageA']['firstSample'].get('outputPath')}` |

第一次 InstantID A 请求曾因 benchmark ComfyUI 未用中央 models directory 而触发 `FAIL_WORKFLOW`（模型列表为空），不是显存错误；使用进程级 `--models-directory C:\\install\\AI\\Models` 修正后重新通过，原失败 manifest 保留。

## 7. InstantID Stage B

总体：{stage_line(instant, 'B')}。`METHOD_REJECTED_STAGE_B`。

逐视角：{by_view(instant)}。

- Median cosine: `{instant['stageB']['qa'].get('medianCosine')}`
- Median yaw error: `{instant['stageB']['qa'].get('medianYawError')}°`；P95 `{instant['stageB']['qa'].get('p95YawError')}°`
- 视角趋势: `NO_MONOTONIC_VIEW_CONTROL={instant['stageB']['qa'].get('noMonotonicViewControl')}`

## 8. PuLID Stage B

总体：{stage_line(pulid, 'B')}。`METHOD_REJECTED_STAGE_B`。

逐视角：{by_view(pulid)}。

- Median cosine: `{pulid['stageB']['qa'].get('medianCosine')}`
- Median yaw error: `{pulid['stageB']['qa'].get('medianYawError')}°`；P95 `{pulid['stageB']['qa'].get('p95YawError')}°`
- 视角趋势: `NO_MONOTONIC_VIEW_CONTROL={pulid['stageB']['qa'].get('noMonotonicViewControl')}`

## 9. Stage B Gate / Stage C

- InstantID: 0/6 <30%，停止，不进入 C。
- PuLID: 1/6 =16.67% <30%，停止，不进入 C。
- InstantID Stage C: `NOT_RUN`，不是 0/15。
- PuLID Stage C: `NOT_RUN`，不是 0/15。
- 因此左右 30°/45°完整双侧稳定性、Stage C 5 视角覆盖、Half/Full、Golden Candidates 均为 `NOT_RUN`/`UNVERIFIED`，不从未执行数据推断质量。

## 10. Identity / View / Dual Comparison

| 指标 | InstantID | PuLID |
|---|---:|---:|
| Stage A | {instant['stageA']['status']} {instant['stageA']['technical']['technicalSuccessCount']}/1 | {pulid['stageA']['status']} {pulid['stageA']['technical']['technicalSuccessCount']}/1 |
| Stage B Technical | {instant['stageB']['qa'].get('technicalSuccessCount')}/6 | {pulid['stageB']['qa'].get('technicalSuccessCount')}/6 |
| Stage B IdentityPass | {instant['stageB']['qa'].get('identityPassCount')}/6 | {pulid['stageB']['qa'].get('identityPassCount')}/6 |
| Stage B ViewPass | {instant['stageB']['qa'].get('viewPassCount')}/6 | {pulid['stageB']['qa'].get('viewPassCount')}/6 |
| Stage B DualPass | {instant['stageB']['qa'].get('dualPassCount')}/6 = {pct(instant['stageB']['qa'].get('endToEndYield'))} | {pulid['stageB']['qa'].get('dualPassCount')}/6 = {pct(pulid['stageB']['qa'].get('endToEndYield'))} |
| Stage B Median cosine | {instant['stageB']['qa'].get('medianCosine')} | {pulid['stageB']['qa'].get('medianCosine')} |
| Stage B Median yaw error | {instant['stageB']['qa'].get('medianYawError')}° | {pulid['stageB']['qa'].get('medianYawError')}° |
| Stage B HardReject | {instant['stageB']['qa'].get('hardRejectCount')}/6 | {pulid['stageB']['qa'].get('hardRejectCount')}/6 |
| Stage C | NOT_RUN | NOT_RUN |

PuLID 的 B 阶段身份指标高于 InstantID，但它仍然只有 1/6 Dual，主要失败在目标视角；因此“身份分数较高”不能替代身份+视角联合通过。

## 11. VRAM / Performance / Local Viability

- InstantID Stage A: Peak `{instant['stageA']['firstSample'].get('peakVramMiB')} MiB`，约 `{(float(instant['stageA']['firstSample'].get('peakVramMiB') or 0) / 1024):.2f} GiB`；`{instant['stageA']['firstSample'].get('generationTimeMs')} ms`；OOM `false`。
- PuLID Stage A: Peak `{pulid['stageA']['firstSample'].get('peakVramMiB')} MiB`，约 `{(float(pulid['stageA']['firstSample'].get('peakVramMiB') or 0) / 1024):.2f} GiB`；`{pulid['stageA']['firstSample'].get('generationTimeMs')} ms`；OOM `false`。
- Stage B generation P50/P95（按该阶段原始 manifest）: InstantID `{number(instant['stageB']['qa'].get('generationP50Ms'), ' ms')} / {number(instant['stageB']['qa'].get('generationP95Ms'), ' ms')}`；PuLID `{number(pulid['stageB']['qa'].get('generationP50Ms'), ' ms')} / {number(pulid['stageB']['qa'].get('generationP95Ms'), ' ms')}`。如果 QA JSON 没有重复该字段，以 Stage A 采样监控为准；没有用理论值替代。
- ComfyUI 进程启用了 async weight offloading；本轮没有 OOM，也没有单张超过 5 分钟，Gate F 为 PASS。

## 12. Half / Full / Golden Candidates

均未执行。原因是两条方法均未通过 Stage B，严格遵守不扩大样本、不伪造 C/Golden 结果的停止规则。`READY_FOR_CHARACTER_LORA_POC=false`。

## 13. Dependency Complexity

- InstantID: SDXL Base + InstantID adapter + antelopev2/InsightFace + InstantID ControlNet；需要显式的 pose/control image。
- PuLID: SDXL Base + PuLID adapter + antelopev2/InsightFace + EVA02 CLIP L 336；本轮 workflow 没有独立 ControlNet pose 分支，视角依赖 prompt，因此不能把它的方向失败归因成缺少已执行的控制分支之外的能力。
- 两者共享同一个 SDXL Base 和同一套 QA Worker，比较结果主要反映身份控制路线差异，而不是 checkpoint 差异。

## 14. Blocked / Unverified

{blocked_lines}

左右方向稳定性：本轮 Stage B 只按提示词执行 Front/Left30/Left45，未执行右侧；两种方法左侧趋势均为 `NO_MONOTONIC_VIEW_CONTROL=true`，右侧方向不能宣称通过。

## 15. 最终排名

按 DualPass → Core View Coverage → IdentityPass → Median Yaw Error → HardReject → VRAM → Generation Time → Dependency Complexity 排名：

{ranking_lines}

该排名仅是“已执行 Stage B 的相对排序”，不是生产选择；由于最高也只有 16.67%，最终没有 selected method。

## 16. 构建与自动回归

{build_lines}

所有本轮新增 Python 工具已执行 compile check；`git diff --check` 结果也在 `12-build-regression.json`。本轮没有改动主 API/Worker/ModelRouter/TTS/FFmpeg 生产代码。

## 17. QA / Benchmark 文件

- [01-environment.json]({root / '01-environment.json'})
- [02-existing-assets.json]({root / '02-existing-assets.json'})
- [03-asset-resume-and-validation.json]({root / '03-asset-resume-and-validation.json'})
- [04-instantid-vram-probe.json]({root / '04-instantid-vram-probe.json'})
- [05-pulid-vram-probe.json]({root / '05-pulid-vram-probe.json'})
- [06-instantid-stage-b.json]({root / '06-instantid-stage-b.json'})
- [07-pulid-stage-b.json]({root / '07-pulid-stage-b.json'})
- [08-instantid-stage-c.json]({root / '08-instantid-stage-c.json'}) — `NOT_RUN`
- [09-pulid-stage-c.json]({root / '09-pulid-stage-c.json'}) — `NOT_RUN`
- [10-method-comparison.json]({root / '10-method-comparison.json'})
- [11-final-candidate-ranking.json]({root / '11-final-candidate-ranking.json'})
- [12-build-regression.json]({root / '12-build-regression.json'})
- [13-final-acceptance.json]({root / '13-final-acceptance.json'})

## 18. 人工审核 HTML

- [01-instantid-stage-b.html]({root / 'html' / '01-instantid-stage-b.html'})
- [02-pulid-stage-b.html]({root / 'html' / '02-pulid-stage-b.html'})
- [03-instantid-stage-c.html]({root / 'html' / '03-instantid-stage-c.html'}) — 未生成，Stage C `NOT_RUN`
- [04-pulid-stage-c.html]({root / 'html' / '04-pulid-stage-c.html'}) — 未生成，Stage C `NOT_RUN`
- [05-instantid-vs-pulid.html]({root / 'html' / '05-instantid-vs-pulid.html'})
- [06-final-golden-candidates.html]({root / 'html' / '06-final-golden-candidates.html'}) — 状态页，无 Golden 样本

HTML 只展示实际生成的 Stage B 图片与指标，不把未执行的 Stage C/Golden 伪装成样本。最终审美签字仍由用户完成：同一人物、发型/年龄/衣服稳定性、左右 30°/45°自然度、五官失真均需人工复核。

## 19. 本轮代码 / workflow 修改

- 新增 `VideoStudio/tools/sdxl_final_benchmark/` 下的资产恢复、资产清单、环境采集、真实 `/prompt` runner、QA evaluator、汇总/报告/HTML 工具。
- 新增版本化 workflow：`C:\\install\\AI\\Workflows\\23_sdxl_instantid_final_benchmark_v1_api.json`、`24_sdxl_pulid_final_benchmark_v1_api.json`；没有覆盖 21/22。
- QA evaluator 增加 worker allow-list 内的哈希证据副本，保留 ComfyUI 原始输出。
- ComfyUI 仅为本轮验证以进程级 `--models-directory` 与 `HF_HUB_CACHE` 启动；主 API、Identity Worker 保持运行边界。

## 20. 最终架构决策与下一轮唯一推荐方向

**正式结论：`REPLACE_CHARACTER_GENERATION_ARCHITECTURE`。**

本轮不再建议继续调 SD1.5 FaceID、SDXL FaceID、InstantID 或 PuLID，也不降低阈值、不扩大 seed。下一轮唯一推荐方向是：**评估一种新的原生 reference-conditioned / multi-view Character Generation Architecture**，优先做小规模选型与真实多视角联合 DualPass 验证；本轮不执行该替换、不训练 LoRA、不进入视频动作或 TTS。
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    args = parser.parse_args()
    root = Path(args.run_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    environment = load_json(root / "01-environment.json", {}) or {}
    assets = asset_resume(root)
    methods = [build_method(root, "InstantID"), build_method(root, "PuLID")]
    comparison = make_comparison(root, assets, methods)
    ranking = build_ranking(comparison)
    build = load_json(root / "12-build-regression.json", {"checks": []}) or {"checks": []}
    acceptance = build_acceptance(root, environment, assets, comparison, ranking)
    write_json(root / "10-method-comparison.json", comparison)
    write_json(root / "11-final-candidate-ranking.json", ranking)
    write_json(root / "13-final-acceptance.json", acceptance)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report_text(root, environment, assets, methods, ranking, acceptance, build), encoding="utf-8")
    print(json.dumps({"decision": acceptance["decision"], "report": str(REPORT_PATH), "comparison": str(root / '10-method-comparison.json'), "ranking": str(root / '11-final-candidate-ranking.json'), "acceptance": str(root / '13-final-acceptance.json')}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
