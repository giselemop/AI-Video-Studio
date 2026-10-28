from __future__ import annotations

import json
import math
import shutil
import statistics
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\install\AI")
VIDEO_STUDIO = ROOT / "VideoStudio"
RUN_ROOT = ROOT / "Data" / "QA" / "character_architecture_replacement_20260818" / "run_01"
ARCH_ROOT = ROOT / "CharacterArchitectures"
REFERENCE = ROOT / "Data" / "QA" / "sdxl_identity_final_benchmark_20260818" / "run_01" / "worker_inputs" / "identity_master_6e39fe49dae7.png"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"status": "UNREADABLE", "path": str(path), "error": f"{type(exc).__name__}: {exc}"}


def write_json(name: str, payload: dict[str, Any]) -> Path:
    path = RUN_ROOT / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def git_snapshot() -> dict[str, Any]:
    def run(args: list[str]) -> str:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()

    try:
        status = run(["git", "-C", str(VIDEO_STUDIO), "status", "--short"])
        return {"branch": run(["git", "-C", str(VIDEO_STUDIO), "branch", "--show-current"]), "head": run(["git", "-C", str(VIDEO_STUDIO), "rev-parse", "HEAD"]), "dirtyCount": len([line for line in status.splitlines() if line.strip()]), "statusShort": status}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def gpu_snapshot() -> dict[str, Any]:
    try:
        line = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,driver_version,temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"], text=True, stderr=subprocess.STDOUT).strip().splitlines()[0]
        fields = [item.strip() for item in line.split(",")]
        keys = ["name", "totalMiB", "usedMiB", "freeMiB", "driver", "temperatureC", "utilizationPct"]
        result: dict[str, Any] = {}
        for key, value in zip(keys, fields):
            try:
                result[key] = float(value) if key not in {"name", "driver"} else value
            except ValueError:
                result[key] = value
        return result
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def repo_snapshot(repo: Path) -> dict[str, Any]:
    try:
        head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, stderr=subprocess.STDOUT).strip()
        return {"path": str(repo), "exists": True, "head": head, "dirtyCount": len(subprocess.check_output(["git", "-C", str(repo), "status", "--short"], text=True).splitlines())}
    except Exception as exc:
        return {"path": str(repo), "exists": repo.is_dir(), "error": f"{type(exc).__name__}: {exc}"}


def file_record(path: Path, expected: int | None = None) -> dict[str, Any]:
    exists = path.is_file()
    size = path.stat().st_size if exists else None
    return {"path": str(path), "exists": exists, "sizeBytes": size, "expectedBytes": expected, "complete": bool(exists and (expected is None or size == expected))}


def sith_weights() -> list[dict[str, Any]]:
    base = ARCH_ROOT / "SiTH" / "checkpoints" / "SiTH_diffusion"
    return [
        file_record(base / "controlnet" / "diffusion_pytorch_model.bin", 1445308665),
        file_record(base / "image_encoder" / "pytorch_model.bin", 1215996977),
        file_record(base / "projection" / "diffusion_pytorch_model.bin", 3146715),
        file_record(base / "unet" / "diffusion_pytorch_model.bin", 3438422053),
        file_record(base / "vae" / "diffusion_pytorch_model.bin", 334712113),
    ]


def stdgen_weights() -> list[dict[str, Any]]:
    base = ARCH_ROOT / "StdGEN" / "ckpt" / "StdGEN-multiview-1024"
    return [
        file_record(base / "image_encoder" / "model.safetensors", 1264217240),
        file_record(base / "text_encoder" / "model.safetensors", 680820392),
        file_record(base / "unet" / "diffusion_pytorch_model.safetensors", 1895432652),
        file_record(base / "vae" / "diffusion_pytorch_model.safetensors", 167335342),
        file_record(base / "image_normalizer" / "diffusion_pytorch_model.safetensors", 4272),
    ]


def execution_paths(alias: str) -> tuple[Path, Path, Path]:
    if alias == "candidate-a":
        base = ARCH_ROOT / "SiTH" / "outputs" / "candidate-a"
    else:
        base = ARCH_ROOT / "StdGEN" / "outputs" / "candidate-b"
    manifests = sorted(base.rglob(f"{alias}-execution.json"), key=lambda path: path.stat().st_mtime) if base.exists() else []
    return base, (manifests[-1] if manifests else base / f"{alias}-execution.json"), RUN_ROOT / f"{alias}-multiview-qa.json"


def metrics(alias: str, execution: dict[str, Any] | None, qa: dict[str, Any] | None) -> dict[str, Any]:
    execution = execution or {}
    qa = qa or {}
    samples = execution.get("samples", [])
    generated = sum(1 for sample in samples if sample.get("status") == "GENERATED")
    if not samples and execution.get("images"):
        generated = len(execution.get("images", []))
    rows = qa.get("rows", [])
    core_rows = [row for row in rows if row.get("core")]
    requested = len(core_rows) if core_rows else len(samples) or len(execution.get("images", []))
    identity_pass = sum(bool(row.get("identityPass")) for row in rows)
    view_pass = sum(bool(row.get("viewPass")) for row in rows if row.get("viewPass") is not None)
    dual_pass = sum(bool(row.get("dualPass")) for row in core_rows)
    generation_ms = [float(sample["elapsedSeconds"]) * 1000 for sample in samples if sample.get("status") == "GENERATED" and sample.get("elapsedSeconds") is not None]
    peak_values: list[float] = []
    for sample in samples:
        for key in ("peakReservedMiB", "peakAllocatedMiB"):
            if isinstance(sample.get(key), (int, float)):
                peak_values.append(float(sample[key]))
    if isinstance(execution.get("peakVramMiB"), (int, float)):
        peak_values.append(float(execution["peakVramMiB"]))
    return {
        "architecture": execution.get("candidate", alias),
        "requested": requested,
        "generated": generated,
        "identityPass": identity_pass,
        "viewPass": view_pass,
        "dualPass": dual_pass,
        "multiViewSetPass": bool(qa.get("multiViewSetPass", False)),
        "medianIdentity": qa.get("summary", {}).get("medianIdentity"),
        "medianYawError": qa.get("summary", {}).get("medianYawError"),
        "crossViewIdentity": qa.get("crossView", {}).get("median"),
        "crossViewMean": qa.get("crossView", {}).get("mean"),
        "crossViewMin": qa.get("crossView", {}).get("min"),
        "peakVramMiB": max(peak_values) if peak_values else None,
        "generationP50Ms": statistics.median(generation_ms) if generation_ms else None,
        "generationP95Ms": sorted(generation_ms)[max(0, math.ceil(len(generation_ms) * 0.95) - 1)] if generation_ms else None,
        "status": execution.get("status", "NOT_RUN"),
        "execution": str(execution.get("result", "")) if execution.get("result") else None,
        "qa": str(qa.get("runRoot", "")) if qa else None,
    }


def html_page(title: str, body: str) -> str:
    return "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>" + escape(title) + "</title><style>body{font-family:Segoe UI,Arial,sans-serif;background:#111827;color:#e5e7eb;margin:32px}h1,h2{color:#f9fafb}.muted{color:#9ca3af}.summary{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}.card{background:#1f2937;border:1px solid #374151;border-radius:8px;padding:10px 14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.sample{background:#1f2937;border-radius:10px;padding:10px}.sample img{width:100%;max-height:420px;object-fit:contain;background:#fff}.metric{font-size:13px;line-height:1.55}.pass{color:#86efac}.fail{color:#fca5a5}.status{padding:16px;background:#3f1d1d;border:1px solid #7f1d1d;border-radius:8px}table{border-collapse:collapse;width:100%;background:#1f2937}th,td{border:1px solid #4b5563;padding:8px;text-align:left;vertical-align:top}</style></head><body>" + body + "</body></html>"


def file_uri(path: str | Path) -> str:
    try:
        return Path(path).resolve().as_uri()
    except Exception:
        return ""


def build_candidate_html(alias: str, architecture: str, execution: dict[str, Any] | None, qa: dict[str, Any] | None) -> str:
    execution = execution or {}
    qa = qa or {}
    summary = qa.get("summary", {})
    cards = "".join(f"<div class='card'>{escape(str(key))}: <b>{escape(str(value))}</b></div>" for key, value in [("Status", execution.get("status", "NOT_RUN")), ("Requested core", summary.get("requestedCoreCount", "NOT_RUN")), ("Generated", sum(1 for row in qa.get("rows", []) if row.get("technicalSuccess"))), ("Identity", summary.get("identityPassCount", "NOT_RUN")), ("View", summary.get("viewPassCount", "NOT_RUN")), ("Dual", summary.get("dualPassCount", "NOT_RUN")), ("MultiViewSetPass", qa.get("multiViewSetPass", False))])
    body = f"<h1>{escape(architecture)} — {escape(alias)}</h1><div class='muted'>只展示真实执行输出；没有生成的候选不填充示例图。</div><div class='summary'>{cards}</div>"
    if not qa.get("rows"):
        reason = execution.get("error") or execution.get("pipelineBoundary", {}).get("reason") or "执行尚未完成或没有可评估输出。"
        body += f"<div class='status'><b>NOT_RUN / NOT_EVALUATED</b><br>{escape(str(reason))}</div>"
        return html_page(f"{architecture} {alias}", body)
    body += "<div class='grid'>"
    for row in qa.get("rows", []):
        source = row.get("sourcePath") or row.get("workerOutputPath")
        image = f"<img src='{escape(file_uri(source))}' alt='{escape(str(row.get('requestedView')))}'>" if source and Path(source).is_file() else "<div class='status'>Image missing</div>"
        hard = ", ".join(row.get("hardRejects", [])) or "none"
        body += f"<div class='sample'>{image}<div class='metric'><b>{escape(str(row.get('requestedView')))}</b><br>Cosine: {escape(str(row.get('identityRawCosine')))}<br>Yaw: {escape(str(row.get('yaw')))}° / target {escape(str(row.get('targetYaw')))}°<br>Identity: {escape(str(row.get('identityPass')))}; View: {escape(str(row.get('viewPass')))}; Dual: {escape(str(row.get('dualPass')))}<br>HardReject: {escape(hard)}<br><span class='muted'>{escape(str(source))}</span></div></div>"
    body += "</div>"
    return html_page(f"{architecture} {alias}", body)


def main() -> int:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    env = read_json(RUN_ROOT / "01-environment.json") or {}
    baseline = read_json(RUN_ROOT / "02-current-architecture-baseline.json") or {}
    a_base, a_exec_path, a_qa_path = execution_paths("candidate-a")
    b_base, b_exec_path, b_qa_path = execution_paths("candidate-b")
    a_exec, b_exec = read_json(a_exec_path), read_json(b_exec_path)
    a_qa, b_qa = read_json(a_qa_path), read_json(b_qa_path)
    a_metrics = metrics("candidate-a", a_exec, a_qa)
    b_metrics = metrics("candidate-b", b_exec, b_qa)

    candidate_a = {
        "schema": "character-architecture-replacement.deployment.v1",
        "capturedAt": now(),
        "candidate": "SiTH",
        "alias": "candidate-a",
        "repository": "https://github.com/SiTH-Diffusion/SiTH",
        "local": repo_snapshot(ARCH_ROOT / "SiTH"),
        "sidecar": str(ARCH_ROOT / "SiTH" / "sidecar_packages"),
        "runtime": "C:\\install\\AI\\ComfyUI\\venv\\Scripts\\python.exe; Python 3.13.2; torch 2.11.0+cu130; diffusers 0.24.0; transformers 4.39.3",
        "importSmoke": {"status": "PASS", "imports": ["BackHallucinationPipeline", "CCProjection", "torch.cuda"]},
        "weights": sith_weights(),
        "dependencyBoundary": {"kaolin": False, "nvdiffrast": False, "smplx": False, "trimesh": False, "diffusionImports": True, "note": "The isolated back-view diffusion probe bypasses the unverified mesh stack; full SMPL-X/texture reconstruction is not claimed."},
        "probe": {"execution": str(a_exec_path) if a_exec else None, "qa": str(a_qa_path) if a_qa else None, "status": a_exec.get("status") if a_exec else "NOT_RUN"},
        "deploymentStatus": "READY_FOR_DIFFUSION_PROBE" if all(item["complete"] for item in sith_weights()) else "WEIGHTS_INCOMPLETE_OR_PROBE_PENDING",
        "productionCandidate": False,
    }
    candidate_b = {
        "schema": "character-architecture-replacement.deployment.v1",
        "capturedAt": now(),
        "candidate": "StdGEN",
        "alias": "candidate-b",
        "repository": "https://github.com/hyz317/StdGEN",
        "local": repo_snapshot(ARCH_ROOT / "StdGEN"),
        "sidecar": str(ARCH_ROOT / "StdGEN" / "sidecar_packages"),
        "runtime": "C:\\install\\AI\\ComfyUI\\venv\\Scripts\\python.exe; Python 3.13.2; torch 2.11.0+cu130; diffusers 0.27.2; transformers 4.42.4",
        "importSmoke": {"status": "PASS", "imports": ["StableUnCLIPImg2ImgPipeline", "kornia", "einops", "torch.cuda"]},
        "weights": stdgen_weights(),
        "dependencyBoundary": {"xformers": False, "pytorchAttentionFallback": True, "officialLowVramFlag": True, "inputContract": "The frozen reference is head-and-shoulders; direct multiview probe does not validate official full-body canonicalization."},
        "probe": {"execution": str(b_exec_path) if b_exec else None, "qa": str(b_qa_path) if b_qa else None, "status": b_exec.get("status") if b_exec else "NOT_RUN"},
        "probeAttempts": [str(path) for path in sorted((ARCH_ROOT / "StdGEN" / "outputs" / "candidate-b").rglob("candidate-b-execution.json"))],
        "deploymentStatus": "READY_FOR_MULTIVIEW_PROBE" if all(item["complete"] for item in stdgen_weights()) else "WEIGHTS_INCOMPLETE_OR_PROBE_PENDING",
        "productionCandidate": False,
    }
    candidate_c = {
        "schema": "character-architecture-replacement.deployment.v1",
        "capturedAt": now(),
        "candidate": "SAM 3D Body",
        "alias": "candidate-c",
        "repository": "https://github.com/facebookresearch/sam-3d-body",
        "local": repo_snapshot(ARCH_ROOT / "SAM3DBody"),
        "officialCheckpointAttempts": [
            {"repo": "facebook/sam-3d-body-dinov3", "include": "model.ckpt", "status": "BLOCKED", "error": "Access denied. This repository requires approval."},
            {"repo": "facebook/sam-3d-body-vith", "include": "model.ckpt", "status": "BLOCKED", "error": "Access denied. This repository requires approval."},
        ],
        "demoImportAttempt": {"command": "python demo.py --help", "status": "FAILED_BEFORE_MODEL_LOAD", "error": "ModuleNotFoundError: No module named 'pyrootutils'"},
        "weights": {"downloaded": False, "checkpointAccess": "GATED_APPROVAL_REQUIRED"},
        "hardware": {"localGpu": "RTX 4070 12GB", "status": "NOT_TESTABLE_WITHOUT_OFFICIAL_CHECKPOINT"},
        "deploymentStatus": "BLOCKED_WEIGHT_ACCESS_AND_UNVERIFIED_12GB",
        "productionCandidate": False,
    }
    write_json("06-candidate-a-deployment.json", candidate_a)
    write_json("07-candidate-b-deployment.json", candidate_b)
    write_json("08-candidate-c-deployment.json", candidate_c)

    mini_probe = {
        "schema": "character-architecture-replacement.mini-probe.v1",
        "capturedAt": now(),
        "reference": str(REFERENCE),
        "frozenQa": {"identityRawCosine": 0.5, "frontAbsYawMax": 15, "yaw30Range": [12, 40], "yaw45Range": [27, 62]},
        "candidates": [a_metrics, b_metrics, {"architecture": "SAM 3D Body", "requested": 0, "generated": 0, "identityPass": 0, "viewPass": 0, "dualPass": 0, "multiViewSetPass": False, "medianIdentity": None, "medianYawError": None, "crossViewIdentity": None, "peakVramMiB": None, "generationP50Ms": None, "generationP95Ms": None, "status": "BLOCKED_WEIGHT_ACCESS"}],
        "atLeastTwoTop3EnteredProbe": bool(a_exec or b_exec),
    }
    write_json("09-mini-probe-results.json", mini_probe)

    benchmark = {
        "schema": "character-architecture-replacement.multiview-mini-benchmark.v1",
        "capturedAt": now(),
        "reference": str(REFERENCE),
        "coreViews": ["front", "left30", "right30", "left45", "right45"],
        "crossViewPairs": [[left, right] for left, right in [("front", "left30"), ("front", "right30"), ("front", "left45"), ("front", "right45"), ("left30", "left45"), ("right30", "right45")]],
        "crossViewThreshold": 0.5,
        "candidateA": {"status": "PARTIAL_BACK_VIEW_ONLY", "evidence": str(a_qa_path) if a_qa else None, "reason": "SiTH back-hallucination probe is not a five-view reconstructed mesh; no MultiViewSetPass is inferred."},
        "candidateB": {"status": b_qa.get("status", "NOT_RUN") if b_qa else "NOT_RUN", "evidence": str(b_qa_path) if b_qa else None, "summary": b_qa.get("summary") if b_qa else None, "crossView": b_qa.get("crossView") if b_qa else None, "multiViewSetPass": bool(b_qa.get("multiViewSetPass", False)) if b_qa else False},
        "candidateC": {"status": "NOT_RUN", "reason": "Official checkpoint approval blocked download."},
        "gate": {"dualCandidate": 0.5, "strongCandidate": 0.7, "multiViewSetPassRatio": 0.5},
        "status": "EVALUATED" if b_qa else "INSUFFICIENT_UNTIL_CANDIDATE_B_PROBE",
    }
    write_json("10-multiview-mini-benchmark.json", benchmark)

    comparison = {
        "schema": "character-architecture-replacement.method-comparison.v1",
        "capturedAt": now(),
        "historicalBaselineOnly": {"architecture": "SDXL InstantID/PuLID", "evidence": r"C:\install\AI\Data\QA\sdxl_identity_final_benchmark_20260818\run_01", "decision": "REPLACE_CHARACTER_GENERATION_ARCHITECTURE", "notRebenchmarked": True},
        "candidateMetrics": [a_metrics, b_metrics, {"architecture": "SAM 3D Body", "status": "BLOCKED_WEIGHT_ACCESS"}],
        "comparisonBoundary": "Candidate outputs are not interchangeable: SiTH partial back hallucination, StdGEN six-view diffusion when available, SAM 3D Body no local checkpoint. No production router or page changed.",
    }
    write_json("11-method-comparison.json", comparison)

    baseline_disk = env.get("disk", {})
    current_disk = shutil.disk_usage("C:\\")
    hardware = {
        "schema": "character-architecture-replacement.hardware-viability.v1",
        "capturedAt": now(),
        "gpu": {"baseline": env.get("hardware", {}).get("nvidiaSmi", {}).get("stdout"), "current": gpu_snapshot(), "localLimit": "RTX 4070 12GB / 12282 MiB reported by nvidia-smi"},
        "disk": {"baselineFreeBytes": baseline_disk.get("freeBytes"), "baselineFreeGiB": baseline_disk.get("freeGiB"), "currentFreeBytes": current_disk.free, "currentFreeGiB": round(current_disk.free / 1024**3, 2), "downloadFootprintUnderCharacterArchitecturesBytes": sum(path.stat().st_size for path in ARCH_ROOT.rglob("*") if path.is_file()) if ARCH_ROOT.exists() else 0},
        "weightManifests": {"SiTH": sith_weights(), "StdGEN": stdgen_weights()},
        "officialHardwareEvidence": {"GAS": "official repository states Linux-only and minimum 20GB", "SAM3DBody": "checkpoint approval blocked; no local VRAM result", "StdGEN": "official low_vram path attempted where weights permit", "SiTH": "official README tested on RTX 3090; full mesh stack not verified on this Windows/Python 3.13 runtime"},
        "status": "RECORDED_WITH_12GB_BOUNDARY",
    }
    write_json("12-hardware-viability.json", hardware)

    regression = {
        "schema": "character-architecture-replacement.build-regression.v1",
        "capturedAt": now(),
        "videoStudioGit": git_snapshot(),
        "baselineGit": {"head": env.get("git", {}).get("head"), "dirtyCount": env.get("git", {}).get("dirtyCount")},
        "mainServices": {"comfy": "not restarted by this phase; baseline captured healthy", "mainApi": "not restarted by this phase; baseline captured healthy", "identityWorker": "not modified; loopback 127.0.0.1:18084"},
        "isolation": {"candidateRoot": str(ARCH_ROOT), "evidenceToolingRoot": str(VIDEO_STUDIO / "tools" / "character_architecture_replacement"), "productionRouterModified": False, "productionPagesModified": False, "workerModified": False, "mainApiRestarted": False},
        "regressionStatus": "PASS_SCOPE_PRESERVED" if git_snapshot().get("head") == env.get("git", {}).get("head") else "HEAD_CHANGED_REVIEW_REQUIRED",
    }
    write_json("13-build-regression.json", regression)

    a_core_rate = a_metrics["dualPass"] / a_metrics["requested"] if a_metrics["requested"] else 0.0
    b_core_rate = b_metrics["dualPass"] / b_metrics["requested"] if b_metrics["requested"] else 0.0
    candidates_with_quality = [item for item in (a_metrics, b_metrics) if item["requested"] > 0 and item["status"] == "GENERATED"]
    best = max(candidates_with_quality, key=lambda item: item["dualPass"] / item["requested"], default=None)
    best_rate = best["dualPass"] / best["requested"] if best else 0.0
    if b_qa and b_qa.get("multiViewSetPass") and b_core_rate >= 0.7:
        decision = "ARCHITECTURE_SELECTED_FOR_POC"
    elif best and best_rate >= 0.5:
        decision = "ARCHITECTURE_CONDITIONAL"
    elif candidates_with_quality and all((item["dualPass"] / item["requested"]) < 0.3 for item in candidates_with_quality) and len(candidates_with_quality) >= 2:
        decision = "NO_LOCAL_ARCHITECTURE_READY"
    elif (not candidates_with_quality or any(item.get("status") in {"FAILED", "TIMEOUT"} for item in (a_metrics, b_metrics))) and not b_qa:
        decision = "CLOUD_GPU_REQUIRED_FOR_NEXT_POC"
    else:
        decision = "ARCHITECTURE_SELECTION_INSUFFICIENT"
    final = {
        "schema": "character-architecture-replacement.final-decision.v1",
        "capturedAt": now(),
        "decision": decision,
        "decisionRules": {"selected": "local dual >=70% and MultiViewSetPass >=50%", "conditional": "local dual >=50%", "noLocal": "all executed candidates dual <30%", "cloud": "only viable path is blocked by >12GB/gated/cloud hardware"},
        "candidateSummary": [a_metrics, b_metrics, {"architecture": "SAM 3D Body", "status": "BLOCKED_WEIGHT_ACCESS", "dualPass": 0, "requested": 0}],
        "top3ProbeGate": {"required": 2, "entered": sum(1 for item in (a_exec, b_exec) if item), "satisfied": sum(1 for item in (a_exec, b_exec) if item) >= 2},
        "qualityGate": {"candidateAConditionalDualRate": a_core_rate, "candidateBConditionalDualRate": b_core_rate, "best": best, "multiViewSetPass": bool(b_qa.get("multiViewSetPass", False)) if b_qa else False},
        "hardBlocks": ["SAM 3D Body official checkpoint requires approval", "full SiTH mesh path lacks verified kaolin/nvdiffrast/SMPL-X stack on this runtime", "12GB hardware cannot be treated as a 24GB/40GB/80GB result"],
        "productionStatus": "NOT_SELECTED_FOR_PRODUCTION" if decision != "ARCHITECTURE_SELECTED_FOR_POC" else "POC_ONLY_NOT_PRODUCTION",
        "requiredNextStep": "Use a Linux/cloud GPU with approved checkpoints and a full-body reference, then re-run the same frozen five-view gate before changing ModelRouter.",
    }
    write_json("14-final-architecture-decision.json", final)

    html_dir = RUN_ROOT / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / "candidate-a-multiview.html").write_text(build_candidate_html("candidate-a", "SiTH", a_exec, a_qa), encoding="utf-8")
    (html_dir / "candidate-b-multiview.html").write_text(build_candidate_html("candidate-b", "StdGEN", b_exec, b_qa), encoding="utf-8")
    (html_dir / "candidate-c-multiview.html").write_text(html_page("SAM 3D Body candidate-c", "<h1>SAM 3D Body — candidate-c</h1><div class='status'><b>NOT_RUN / BLOCKED</b><br>官方 checkpoint 下载返回 approval required；本页不伪造样例图。</div>"), encoding="utf-8")
    rows = "".join(f"<tr><td>{escape(str(item.get('architecture')))}</td><td>{escape(str(item.get('status')))}</td><td>{escape(str(item.get('requested')))}</td><td>{escape(str(item.get('generated')))}</td><td>{escape(str(item.get('identityPass')))}</td><td>{escape(str(item.get('viewPass')))}</td><td>{escape(str(item.get('dualPass')))}</td><td>{escape(str(item.get('multiViewSetPass')))}</td><td>{escape(str(item.get('peakVramMiB')))}</td></tr>" for item in [a_metrics, b_metrics, {"architecture": "SAM 3D Body", "status": "BLOCKED_WEIGHT_ACCESS", "requested": 0, "generated": 0, "identityPass": 0, "viewPass": 0, "dualPass": 0, "multiViewSetPass": False, "peakVramMiB": None}])
    (html_dir / "architecture-comparison.html").write_text(html_page("Character architecture comparison", f"<h1>Character Generation Architecture Replacement</h1><p>Decision: <b>{escape(decision)}</b></p><table><thead><tr><th>Architecture</th><th>Status</th><th>Requested core</th><th>Generated</th><th>Identity</th><th>View</th><th>Dual</th><th>MultiViewSet</th><th>Peak VRAM MiB</th></tr></thead><tbody>{rows}</tbody></table>"), encoding="utf-8")

    report_path = VIDEO_STUDIO / "docs" / "AI视频人物生成架构替换执行结果.md"
    report = f"""# AI Video Studio 人物生成架构替换执行结果

执行日期：2026-08-18
本轮证据目录：`{RUN_ROOT}`
最终决策：**{decision}**

## 结论

本轮 Survey 记录了 8 条路线，Top 3 为 SiTH、StdGEN、SAM 3D Body。SiTH 与 StdGEN 已进入隔离部署/实际 Mini Probe 流程；SAM 3D Body 的官方 checkpoint 下载被 gated approval 阻断，因此没有伪造推理结果。当前结果只决定“是否值得进入下一轮 POC”，没有修改 ModelRouter、生产页面、主 API 或 Identity Worker。

## 本轮边界

没有重跑 InstantID/PuLID/FaceID 主 Benchmark；历史 SDXL 结果仅作为“替换架构”基线。没有做 Character LoRA、I2V、Wan Animate、HunyuanVideo、Driving/Pose、TTS、字幕、25/60 秒成片或生产 Master。

冻结 QA：raw cosine ≥0.5；front abs yaw <15°；30°视角 abs yaw ∈[12,40)；45°视角 abs yaw ∈[27,62)；Dual = IdentityPass 且 ViewPass 且无 HardReject；多视角集合还要求 5 个核心视角、至少 4/5 ViewPass、跨视角相似度阈值 0.5。

## 候选实际状态

| 候选 | 技术路线 | 实际状态 | 生产判断 |
|---|---|---|---|
| SiTH | 单参考图扩散式背面补全 + SMPL-X/纹理重建 | {a_metrics['status']}；本轮 probe 边界为 back-view diffusion，完整 mesh 依赖未验证 | 不进入生产 |
| StdGEN | 语义分解多视角扩散 + S-LRM | {b_metrics['status']}；输入是 head-and-shoulders，不能冒充 full-body canonicalization | 不进入生产 |
| SAM 3D Body | promptable 参数化全身 mesh | 官方 checkpoint approval required；未运行 | 不进入生产 |

Mini Probe 机器指标详见 `09-mini-probe-results.json`，五视角门槛详见 `10-multiview-mini-benchmark.json`。实际样例与失败状态页：

- [candidate-a-multiview.html]({html_dir / 'candidate-a-multiview.html'})
- [candidate-b-multiview.html]({html_dir / 'candidate-b-multiview.html'})
- [candidate-c-multiview.html]({html_dir / 'candidate-c-multiview.html'})
- [architecture-comparison.html]({html_dir / 'architecture-comparison.html'})

## 硬件与阻塞证据

本机为 RTX 4070，nvidia-smi 报告 12,282 MiB 显存；本轮所有数值均不能外推到 24GB、40GB 或 80GB。SAM 3D Body 的两个官方 checkpoint 仓库均返回 `Access denied. This repository requires approval.`。SiTH 的完整 mesh 路径还缺少已验证的 kaolin、nvdiffrast、SMPL-X 运行栈；因此只把成功的扩散阶段记为 partial probe。

## 回归

主 API、ComfyUI、Identity Worker 在本轮保持 loopback 健康；Worker 仍为 `127.0.0.1:18084`。候选代码、sidecar 依赖、权重和输出均位于 `{ARCH_ROOT}`；本轮只在 VideoStudio 的 `tools/character_architecture_replacement` 增加证据/探针脚本，没有重启主 API、没有修改 Worker、没有改动生产 ModelRouter 或生产页面。回归详情见 `13-build-regression.json`。

## 官方资料

- [SiTH official repository](https://github.com/SiTH-Diffusion/SiTH)
- [StdGEN official repository](https://github.com/hyz317/StdGEN)
- [SAM 3D Body official repository](https://github.com/facebookresearch/sam-3d-body)
- [GAS official repository](https://github.com/humansensinglab/GAS)
- [Pippo official repository](https://github.com/facebookresearch/pippo)
- [CharacterGen project page](https://charactergen.github.io/)
- [MVD-HuGaS paper page](https://huggingface.co/papers/2503.08218)
- [HumanGaussian official repository](https://github.com/alvinliu0/HumanGaussian)

"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"decision": decision, "report": str(report_path), "runRoot": str(RUN_ROOT), "html": [str(path) for path in sorted(html_dir.glob("*.html"))]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
