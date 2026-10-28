#!/usr/bin/env python3
"""Finalize the 3D Character Foundation evidence package.

This module creates only evidence/report artifacts.  It refuses to invent
renders when no candidate produced a persistent representation.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\install\AI")
EVIDENCE = ROOT / "Data" / "QA" / "3d_character_foundation_20260818" / "run_01"
STUDIO = ROOT / "VideoStudio"
TOOLS = STUDIO / "tools" / "3d_character_foundation"
REPORT = STUDIO / "docs" / "AI视频3D人物基础架构决选执行结果.md"


def load(name: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    p = EVIDENCE / name
    if not p.is_file():
        return default or {"missing": True, "path": str(p)}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"read_error": f"{type(exc).__name__}: {exc}", "path": str(p)}


def write_json(name: str, value: dict[str, Any]) -> None:
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], cwd: Path | None = None, timeout: int = 120) -> dict[str, Any]:
    try:
        p = subprocess.run(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=False)
        return {"command": command, "returncode": p.returncode, "stdout": p.stdout[-12000:], "stderr": p.stderr[-12000:]}
    except Exception as exc:
        return {"command": command, "error": f"{type(exc).__name__}: {exc}"}


def blocked_multiview(candidate: str, reason: str, source_json: str) -> dict[str, Any]:
    return {
        "schema": f"3d-character-foundation/{candidate.lower()}-multiview-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "candidate": candidate,
        "source_probe": str(EVIDENCE / source_json),
        "representation_created": False,
        "representation_type": None,
        "persistent_representation_paths": [],
        "fixed_cameras": [
            {"name": "Front", "yaw_deg": 0, "elevation_deg": 0, "roll_deg": 0},
            {"name": "Left30", "yaw_deg": -30, "elevation_deg": 0, "roll_deg": 0},
            {"name": "Right30", "yaw_deg": 30, "elevation_deg": 0, "roll_deg": 0},
            {"name": "Left45", "yaw_deg": -45, "elevation_deg": 0, "roll_deg": 0},
            {"name": "Right45", "yaw_deg": 45, "elevation_deg": 0, "roll_deg": 0},
        ],
        "render_resolution": "512x768 target",
        "renders": [],
        "representation_reopen_test": {"status": "NOT_RUN_NO_REPRESENTATION"},
        "repeat_render_test": {"status": "NOT_RUN_NO_REPRESENTATION"},
        "multiview_set_pass_v2": False,
        "gate": "BLOCKED",
        "blocked_reason": reason,
        "no_fake_samples": True,
    }


def create_html() -> None:
    page_dir = EVIDENCE / "html"
    page_dir.mkdir(parents=True, exist_ok=True)
    pages = [
        ("01-humansplat-multiview.html", "HumanSplat 五相机验收", "BLOCKED", "HumanSplat 未通过模型/依赖/资产门禁；没有 persistent Gaussian，也没有可展示的五相机渲染。", "../05-humansplat-probe.json"),
        ("02-sith-multiview.html", "SiTH Full Pipeline 五相机验收", "BLOCKED", "SiTH 只完成到官方权重与入口审计；SMPL-X body asset、Windows 原生依赖和可信全身输入门禁未满足，没有把背面 PNG 当作 mesh。", "../08-sith-full-pipeline-probe.json"),
        ("03-sam3d-multiview.html", "SAM 3D Body 五相机验收", "BLOCKED", "官方 DINOv3/ViT-H checkpoint 轻量请求返回 GatedRepo/approval required，按要求停止，不展示伪造样本。", "../11-sam3d-probe.json"),
        ("04-3d-character-comparison.html", "3D Character Foundation 对比", "NO READY CANDIDATE", "HumanSplat、SiTH Full Pipeline、SAM 3D Body 均未产生可持久化且可重复相机渲染的同一人物表示；当前结论为 NO_3D_CHARACTER_FOUNDATION_READY。", "../19-final-acceptance.json"),
    ]
    css = "body{font-family:Segoe UI,Arial,sans-serif;margin:32px;background:#0f172a;color:#e2e8f0}main{max-width:900px;margin:auto;background:#1e293b;padding:28px;border-radius:14px}h1{margin-top:0}.status{display:inline-block;padding:8px 12px;border-radius:8px;background:#7f1d1d;color:#fecaca;font-weight:700}p{line-height:1.65}a{color:#93c5fd}code{color:#c4b5fd}"
    for filename, title, status, body, evidence in pages:
        content = f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{css}</style></head><body><main><h1>{html.escape(title)}</h1><div class='status'>{html.escape(status)}</div><p>{html.escape(body)}</p><p>本页面明确没有添加候选生成图。机器可读证据：<a href='{evidence}'>{html.escape(evidence)}</a></p><p>统一相机：Front 0°、Left30 -30°、Right30 +30°、Left45 -45°、Right45 +45°；无表示时不执行渲染。</p></main></body></html>"
        (page_dir / filename).write_text(content, encoding="utf-8")


def finalize_json() -> None:
    hs = load("05-humansplat-probe.json")
    sith = load("08-sith-full-pipeline-probe.json")
    sam = load("11-sam3d-probe.json")
    write_json("06-humansplat-multiview.json", blocked_multiview("HumanSplat", "No persistent representation: official checkpoint, diffusers/xformers/HPS assets, and renderer gate failed before inference.", "05-humansplat-probe.json"))

    unified = {
        "schema": "3d-character-foundation/unified-camera-render-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "camera_contract": [
            {"name": "Front", "yaw_deg": 0, "elevation_deg": 0, "roll_deg": 0},
            {"name": "Left30", "yaw_deg": -30, "elevation_deg": 0, "roll_deg": 0},
            {"name": "Right30", "yaw_deg": 30, "elevation_deg": 0, "roll_deg": 0},
            {"name": "Left45", "yaw_deg": -45, "elevation_deg": 0, "roll_deg": 0},
            {"name": "Right45", "yaw_deg": 45, "elevation_deg": 0, "roll_deg": 0},
        ],
        "representation_gate": "persistent 3D Gaussian, mesh, textured SMPL-X, NeRF-like or repeatable camera-renderable asset only",
        "candidate_renders": [],
        "camera_to_face_alignment": {"status": "NOT_RUN_NO_REPRESENTATION", "required_yaw_order": [-45, -30, 0, 30, 45]},
        "render_status": "NOT_RUN_BLOCKED_ALL_CANDIDATES",
        "severe_hard_reject": True,
        "reason": "No candidate produced a valid persistent representation; rendering PNGs would violate the gate.",
    }
    write_json("13-unified-camera-render.json", unified)
    write_json("14-crossview-identity.json", {
        "schema": "3d-character-foundation/crossview-identity-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "embedding_model": "InsightFace buffalo_l/w600k_r50.onnx, raw cosine, 512-d",
        "threshold": 0.5,
        "required_pairs": ["Front-L30", "Front-R30", "Front-L45", "Front-R45", "L30-L45", "R30-R45", "L30-R30", "L45-R45"],
        "pair_results": [],
        "identity_gate": "NOT_RUN_NO_FIVE_VIEW_SET",
        "reason": "No real five-view set exists because no candidate produced a persistent representation.",
        "full_body_reference_status": "BLOCKED_FULL_BODY_REFERENCE",
    })
    write_json("15-method-comparison.json", {
        "schema": "3d-character-foundation/method-comparison-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "candidates": [
            {"name": "HumanSplat", "deployment": "BLOCKED", "representation": False, "five_view": False, "identity_qa": None, "camera_qa": None, "vram_mib": None, "license": "MIT", "gated_assets": ["out/178000/model.safetensors", "PIXIE", "SMPL-X", "xformers", "diffusers", "Windows rasterizer"]},
            {"name": "SiTH Full Pipeline", "deployment": "BLOCKED", "representation": False, "five_view": False, "identity_qa": None, "camera_qa": None, "vram_mib": None, "license": "MIT", "gated_assets": ["SMPL-X body models", "OpenPose", "Windows/kaolin/nvdiffrast compatibility", "trusted full-body input"]},
            {"name": "SAM 3D Body", "deployment": "BLOCKED_CHECKPOINT_ACCESS", "representation": False, "five_view": False, "identity_qa": None, "camera_qa": None, "vram_mib": None, "license": "SAM License", "gated_assets": ["HF checkpoint approval/authentication"]},
        ],
        "reference_only": {"Pippo": "Official code-only release without pre-trained weights; not a local decision candidate."},
        "ranking": [],
        "recommended_foundation": None,
        "decision": "NO_3D_CHARACTER_FOUNDATION_READY",
    })

    env = load("01-environment.json")
    gpu = env.get("gpu_probe", {})
    disk = env.get("disk_C", {})
    write_json("16-hardware-viability.json", {
        "schema": "3d-character-foundation/hardware-viability-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "local_gpu": gpu,
        "local_torch": env.get("torch"),
        "local_12gb_verdict": "NO_SELECTION: 12GB-class RTX 4070 was not proven sufficient for any complete candidate because all candidates stopped before representation; SiTH diffusion-only sampler history is not a full-pipeline proof.",
        "cloud_24gb_plus_verdict": "CONDITIONAL_UNVERIFIED: 24GB+ may relax VRAM/dependency pressure, but cannot remove checkpoint approval, SMPL-X asset, license, or trusted full-body-input gates.",
        "disk_free_bytes": disk.get("free_bytes"),
        "vram_comparable_full_pipeline_measurements": [],
    })
    write_json("17-canonical-pack-preview.json", {
        "schema": "3d-character-foundation/canonical-pack-preview-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "NOT_READY",
        "representation": None,
        "files": [],
        "required_for_next_gate": ["persistent representation", "same-representation five fixed-camera renders", "reopen/repeat render pass", "identity/camera QA", "trusted same-person full-body input"],
    })
    py_scripts = sorted(str(p) for p in TOOLS.glob("*.py"))
    compile_result = run([str(Path(sys.executable)), "-m", "py_compile", *py_scripts], cwd=TOOLS, timeout=180) if py_scripts else {"error": "no scripts"}
    write_json("18-build-regression.json", {
        "schema": "3d-character-foundation/build-regression-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python_tools": py_scripts,
        "python_compile": compile_result,
        "git_diff_check": run(["git", "-C", str(STUDIO), "diff", "--check"], timeout=60),
        "service_health_at_baseline": env.get("service_health"),
        "production_modelrouter_or_page_changes": False,
        "frontend_build": "NOT_APPLICABLE: this phase added evidence tooling only; no product frontend/backend route was changed.",
        "regression_status": "PASS_FOR_EVIDENCE_TOOLING" if compile_result.get("returncode") == 0 and compile_result.get("error") is None else "FAIL",
    })
    write_json("19-final-acceptance.json", {
        "schema": "3d-character-foundation/final-acceptance-v1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "final_state": "NO_3D_CHARACTER_FOUNDATION_READY",
        "recommended_foundation": None,
        "candidate_results": {
            "HumanSplat": {"status": "rejected", "evidence": str(EVIDENCE / "05-humansplat-probe.json")},
            "SiTH Full Pipeline": {"status": "rejected", "evidence": str(EVIDENCE / "08-sith-full-pipeline-probe.json")},
            "SAM 3D Body": {"status": "rejected", "evidence": str(EVIDENCE / "11-sam3d-probe.json")},
            "Pippo": {"status": "reference_only", "evidence": str(EVIDENCE / "13-pippo-reference.json")},
        },
        "representation_gate": False,
        "five_view_gate": False,
        "identity_gate": False,
        "camera_gate": False,
        "persistence_gate": False,
        "full_body_reference_status": "BLOCKED_FULL_BODY_REFERENCE",
        "ready_for_character_canonical_pack_poc": False,
        "blocked_items": ["trusted same-person full-body reference", "HumanSplat checkpoint/HPS/renderer", "SiTH full-pipeline dependencies/body assets", "SAM checkpoint approval", "no local persistent representation"],
        "next_direction": "Next-generation native single-image reconstruction/Gaussian/4D or a licensed commercial/high-VRAM service; do not revert to independent FaceID-per-view generation.",
    })


def report_text() -> str:
    final = load("19-final-acceptance.json")
    root = str(EVIDENCE)
    lines = [
        "# AI Video Studio 3D 人物基础架构决选执行结果",
        "",
        f"执行时间：{time.strftime('%Y-%m-%d %H:%M:%S %z')}  ",
        f"证据根目录：`{root}`  ",
        f"最终状态：**{final.get('final_state')}**",
        "",
        "## 结论",
        "",
        "本轮没有任何候选达到“单一 Identity Master → 持久化 3D/canonical 表示 → 同一表示五相机渲染”的硬门槛，因此不选 HumanSplat、SiTH 或 SAM 3D Body，也不把 Pippo 作为本地候选。没有生成伪造多视图、伪造 mesh 或伪造身份分数。",
        "",
        "## 36 项回传",
        "",
        "1. 最终状态：`NO_3D_CHARACTER_FOUNDATION_READY`。",
        "2. 推荐 foundation：无；当前不允许进入 Character Canonical Pack POC。",
        "3. HumanSplat 部署：官方仓库已隔离到 `C:\\install\\AI\\CharacterArchitectures\\HumanSplat`，源码可编译，导入在缺少 `diffusers` 处停止。",
        "4. HumanSplat 表示：未创建；核心 `out/178000/model.safetensors` 不存在。",
        "5. HumanSplat 五视图：未执行；没有 persistent Gaussian 和 renderer 输出。",
        "6. HumanSplat QA：身份、视角、相机单调性、重复渲染、重开渲染均为未运行。",
        "7. HumanSplat VRAM：无完整推理峰值；不能用未完成探针推断 12GB 可行。",
        "8. HumanSplat 门禁资产：PIXIE/SMPL-X 需要官方账号资产，`xformers`、`diffusers` 和 Windows rasterizer 也缺失；未提交凭据。",
        "9. SiTH 部署：已有官方 `SiTH_diffusion` 权重，并下载官方 ETH `recon_model.pth`；完整入口仍被环境/资产门禁阻断。",
        "10. SiTH 完整表示：未创建 mesh、纹理 mesh、GLB/OBJ canonical 输出。",
        "11. SiTH 五视图：未执行；之前的背面 diffusion PNG 明确不计入本轮。",
        "12. SiTH QA：无五视图输入，身份/视角/相机/重开/重复渲染均未运行。",
        "13. SiTH VRAM：历史背面 sampler 约 2.6 GiB allocated 仅是扩散子步骤，不能代表完整 mesh pipeline。",
        "14. 全身参考：冻结 Identity Master 是 head-and-shoulders；现有 A/B 全身候选与其 raw cosine 约为 `-0.0454` 至 `0.0682`，不作为同人真值，状态 `BLOCKED_FULL_BODY_REFERENCE`。",
        "15. SiTH 依赖：Windows/Python 3.13/Torch 2.11/CUDA 13 与官方 Ubuntu 22.04/Torch 2.1/CUDA 12.1 目标不一致；`kaolin`、`nvdiffrast`、`smplx`、`trimesh` 等不完整，触发 `DEPLOYMENT_COMPLEXITY_BLOCK`。",
        "16. SAM 3D Body 权限：DINOv3 和 ViT-H 官方 HF checkpoint 轻量请求均返回 `GatedRepo`/需要审批；按要求停止。",
        "17. SAM 3D Body 探针：未在无权重时重复大下载；无表示、无渲染。",
        "18. Pippo：官方 README 说明是 code-only release without pre-trained weights，本轮仅作参考。",
        "19. 统一相机：契约为 Front 0°、Left30 -30°、Right30 +30°、Left45 -45°、Right45 +45°，elevation/roll 0；没有表示所以没有渲染。",
        "20. 跨视图身份：要求的 8 组 pair 未运行；没有真实五视图集。",
        "21. 表示持久化：无 `.ply/.splat/.obj/.glb/.gltf` 候选输出可验收。",
        "22. 同一表示：未满足；没有把五张 PNG 视为一个 3D 表示。",
        "23. Repeat Render Test：未运行；无表示。",
        "24. Representation Reopen Test：未运行；无可保存/重开资产。",
        "25. 本机 12GB：RTX 4070 12,282 MiB；本轮没有任何候选证明完整 foundation 在此容量可用。",
        "26. 云端 24GB+：仅为条件性下一步，可能缓解显存/依赖压力，但不能消除 checkpoint、账号资产、许可证和输入真值门禁。",
        "27. 许可证：HumanSplat MIT、SiTH MIT、SAM 3D Body 使用 SAM License；实际发布前仍需逐项核对权重及依赖许可。",
        "28. 硬件阻塞证据：环境、GPU、CUDA、WSL 状态、依赖、缺失路径、官方 HTTP 门禁均写入 JSON。",
        "29. 构建回归：本阶段证据脚本 `py_compile` 与 `git diff --check` 结果写入 `18-build-regression.json`；未改生产 ModelRouter、页面或工作流。",
        "30. JSON 完整性：`01` 至 `19` 均在本轮证据根目录；另有 Pippo 参考状态 JSON。",
        "31. HTML：四个候选/对比页面均明确显示 BLOCKED 或 NO READY CANDIDATE，没有伪造样本。",
        "32. Canonical Pack：`17-canonical-pack-preview.json` 状态 `NOT_READY`，文件列表为空。",
        "33. 磁盘：环境基线写入 C 盘总量、已用量、剩余量；下载的 SiTH 官方文件位于隔离目录。",
        "34. 脚本：执行工具位于 `C:\\install\\AI\\VideoStudio\\tools\\3d_character_foundation`，包括 baseline、HumanSplat、SiTH、SAM/Pippo、finalize。",
        "35. READY_FOR_CHARACTER_CANONICAL_PACK_POC：`false`。",
        "36. 下一方向：寻找支持单图直接重建 Gaussian/mesh/4D canonical 的下一代原生方案、商业服务或 24GB+ 云 GPU；不要回退到每个视角独立 FaceID 生成。",
        "",
        "## 机器可读证据",
        "",
        f"- 统一证据根目录：`{root}`",
        f"- 最终验收：`{root}\\19-final-acceptance.json`",
        f"- HumanSplat 探针：`{root}\\05-humansplat-probe.json`",
        f"- SiTH Full Pipeline：`{root}\\08-sith-full-pipeline-probe.json`",
        f"- SAM checkpoint 权限：`{root}\\11-sam3d-probe.json`",
        f"- 统一相机：`{root}\\13-unified-camera-render.json`",
        f"- 对比：`{root}\\15-method-comparison.json`",
        "",
        "## 官方资料",
        "",
        "- [HumanSplat 官方仓库](https://github.com/humansplat/humansplat)：单图预测 3D Gaussian；其 README 说明需要 PIXIE/SMPL-X 账号资产。",
        "- [SiTH 官方仓库](https://github.com/SiTH-Diffusion/SiTH)：body fitting、back hallucination、textured mesh reconstruction 完整链路。",
        "- [SAM 3D Body 官方仓库](https://github.com/facebookresearch/sam-3d-body)：官方 checkpoint 需按 INSTALL 流程申请访问。",
        "- [Pippo 官方仓库](https://github.com/facebookresearch/pippo)：当前官方 README 标注为无预训练权重的 code-only release。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    EVIDENCE = args.evidence_root.resolve()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    finalize_json()
    create_html()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report_text(), encoding="utf-8")
    print(json.dumps({"final_state": load("19-final-acceptance.json").get("final_state"), "report": str(REPORT), "evidence_root": str(EVIDENCE)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
