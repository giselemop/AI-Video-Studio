from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_head(path: str) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True, timeout=30).strip()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    args = parser.parse_args()
    root = Path(args.run_root)
    root.mkdir(parents=True, exist_ok=True)
    now = utc_now()

    sources = [
        {"name": "StdGEN official repository", "url": "https://github.com/hyz317/StdGEN", "checked": "2026-08-18", "evidence": "code, inference commands, public checkpoints, low_vram flag, anime/full-body caveats, Apache-2.0 code and research-only checkpoint disclaimer"},
        {"name": "SiTH official repository", "url": "https://github.com/SiTH-Diffusion/SiTH", "checked": "2026-08-18", "evidence": "single-image textured human reconstruction, diffusion back hallucination, SMPL-X fitting, public checkpoints, Ubuntu 22.04/PyTorch 2.1/CUDA 12.1/RTX 3090 test, MIT license"},
        {"name": "SAM 3D Body official repository", "url": "https://github.com/facebookresearch/sam-3d-body", "checked": "2026-08-18", "evidence": "single-image full-body MHR mesh recovery, checkpoint identifiers, Python 3.11 install, gated Hugging Face access, SAM License"},
        {"name": "GAS official repository", "url": "https://github.com/humansensinglab/GAS", "checked": "2026-08-18", "evidence": "single-image novel-view and novel-pose avatar synthesis, Linux requirement, minimum 20GB inference memory, public code and HF checkpoints, research disclaimer"},
        {"name": "Pippo official repository", "url": "https://github.com/facebookresearch/pippo", "checked": "2026-08-18", "evidence": "1K multi-view turnaround from one image, code-only release without pretrained weights, A100 80GB full model training, tiny T4 training config"},
        {"name": "CharacterGen official project page", "url": "https://charactergen.github.io/", "checked": "2026-08-18", "evidence": "image-conditioned multi-view diffusion plus sparse-view reconstruction and texture back-projection; page still says code/dataset/weights will be available soon"},
        {"name": "MVD-HuGaS paper page", "url": "https://huggingface.co/papers/2503.08218", "checked": "2026-08-18", "evidence": "paper describes single-image human multi-view diffusion prior and 3D Gaussian free-view rendering; page has no linked model or repository"},
        {"name": "HumanGaussian official repository", "url": "https://github.com/alvinliu0/HumanGaussian", "checked": "2026-08-18", "evidence": "text-driven, not reference-conditioned; code and pretrained guidance/avatars, animation-ready 3DGS, A100 40GB one-hour optimization note"},
    ]

    candidates = [
        {
            "id": "CAND-01",
            "name": "SiTH",
            "paper": "SiTH: Single-view Textured Human Reconstruction with Image-Conditioned Diffusion, CVPR 2024",
            "paperUrl": "https://arxiv.org/abs/2311.15861",
            "repository": "https://github.com/SiTH-Diffusion/SiTH",
            "localClone": r"C:\install\AI\CharacterArchitectures\SiTH",
            "localHead": repo_head(r"C:\install\AI\CharacterArchitectures\SiTH"),
            "weights": ["hohs/SiTH_diffusion", "hohs/SiTH-diffusion-2000", "hohs/SiTH-diffusion-1K", "official recon_model.pth", "official save_smplerx.pth"],
            "releaseDate": "2024-04-15 demo/models; 2024-06-14 training code",
            "license": "MIT code; referenced SMPL-X/OpenPose/assets have their own terms",
            "baseArchitecture": "image-conditioned diffusion back-view hallucination + SMPL-X fitting + implicit textured human reconstruction",
            "referenceMode": "single reference image",
            "capabilities": {"human": True, "fullBody": True, "camera": "mesh/render camera after reconstruction", "pose": "SMPL-X reposing downstream", "multiView": "front plus generated back views; free-view mesh after reconstruction"},
            "platform": {"windows": "UNVERIFIED", "linux": "OFFICIAL_TESTED_UBUNTU_22_04", "comfyui": "NOT_AVAILABLE"},
            "runtime": {"python": "official install not pinned; official test uses PyTorch 2.1.0/CUDA 12.1", "torch": "2.1.0", "cuda": "12.1", "vram": "RTX 3090 tested; 12GB unverified"},
            "modelSize": "several GB; official recon_model.pth 0.78GB and save_smplerx.pth 2.65GB; diffusion checkpoints are additional",
            "activity": "public CVPR 2024 release; 64 repository commits observed locally from shallow clone",
            "labels": ["CODE_AVAILABLE", "WEIGHTS_AVAILABLE", "RUNNABLE_PROJECT", "COMFYUI_UNAVAILABLE", "PRODUCTION_CANDIDATE_CONDITIONAL"],
            "fitRisk": "Input contract is full-body/RGBA plus OpenPose and SMPL-X; the fixed identity master is a head-and-shoulders portrait, so full-body identity acceptance is unverified and likely structurally blocked.",
        },
        {
            "id": "CAND-02",
            "name": "StdGEN",
            "paper": "StdGEN: Semantic-Decomposed 3D Character Generation from Single Images, CVPR 2025",
            "paperUrl": "https://arxiv.org/abs/2411.05738",
            "repository": "https://github.com/hyz317/StdGEN",
            "localClone": r"C:\install\AI\CharacterArchitectures\StdGEN",
            "localHead": repo_head(r"C:\install\AI\CharacterArchitectures\StdGEN"),
            "weights": ["hyz317/StdGEN/StdGEN-canonicalize-1024", "hyz317/StdGEN/StdGEN-multiview-1024", "hyz317/StdGEN/StdGEN-mesh-slrm.pth", "ViT-H SAM model"],
            "releaseDate": "2025-03-04 inference code/dataset/checkpoints; 2025-03-17 online demo",
            "license": "Apache-2.0 repository; released checkpoints explicitly research-only",
            "baseArchitecture": "reference canonicalization to A-pose + semantic-decomposed multi-view RGB/normal diffusion + S-LRM + multi-layer refinement",
            "referenceMode": "single reference image; expected full-body image",
            "capabilities": {"human": True, "fullBody": True, "camera": "canonical multi-view camera set; reconstructed mesh render camera", "pose": "canonical A-pose; downstream mesh pose possible", "multiView": "six-view RGB and normal set"},
            "platform": {"windows": "UNVERIFIED", "linux": "README_CONDA_ORIENTED", "comfyui": "NOT_AVAILABLE"},
            "runtime": {"python": "3.9", "torch": "2.1.0", "cuda": "11.8", "vram": "low_vram flag; exact requirement not published"},
            "modelSize": "multi-view UNet 1.90GB plus image/text/normalizer/VAE files; full canonicalize and S-LRM add several GB",
            "activity": "public CVPR 2025 release; 100 git objects in shallow clone",
            "labels": ["CODE_AVAILABLE", "WEIGHTS_AVAILABLE", "RUNNABLE_PROJECT", "COMFYUI_UNAVAILABLE", "PRODUCTION_CANDIDATE_CONDITIONAL"],
            "fitRisk": "Training data is Anime3D++; README warns half-body/real-world background inputs are suboptimal. This is a technical route probe, not a production identity approval.",
        },
        {
            "id": "CAND-03",
            "name": "SAM 3D Body",
            "paper": "SAM 3D Body: Robust Full-Body Human Mesh Recovery, CVPR 2026/arXiv 2602.15989",
            "paperUrl": "https://arxiv.org/abs/2602.15989",
            "repository": "https://github.com/facebookresearch/sam-3d-body",
            "localClone": r"C:\install\AI\CharacterArchitectures\SAM3DBody",
            "localHead": repo_head(r"C:\install\AI\CharacterArchitectures\SAM3DBody"),
            "weights": ["facebook/sam-3d-body-dinov3 (gated/manual access)", "facebook/sam-3d-body-vith (gated/manual access)"],
            "releaseDate": "2025-11-19 checkpoints/dataset/web demo/paper announced",
            "license": "Meta SAM License; checkpoint access requires Hugging Face approval/authentication",
            "baseArchitecture": "single-image promptable full-body mesh recovery using MHR with optional keypoint/mask prompts",
            "referenceMode": "single reference image; optional keypoint/mask prompt",
            "capabilities": {"human": True, "fullBody": True, "camera": "estimated camera/mesh; native 3D body", "pose": "body/feet/hands pose recovered", "multiView": "native 3D mesh can be rendered from multiple cameras; texture/avatar identity is not generated by this model"},
            "platform": {"windows": "UNVERIFIED", "linux": "INSTALL_GUIDE_CONDA", "comfyui": "NOT_AVAILABLE"},
            "runtime": {"python": "3.11 in INSTALL.md", "torch": "follow official PyTorch instructions", "cuda": "not pinned", "vram": "not published; 12GB unverified"},
            "modelSize": "DINOv3-H+ backbone listed as 840M parameters; full checkpoint size and peak VRAM unverified due gated download",
            "activity": "public Meta repository; active current main branch, official 2025 checkpoint release",
            "labels": ["CODE_AVAILABLE", "WEIGHTS_AVAILABLE_GATED", "RUNNABLE_PROJECT_CONDITIONAL", "COMFYUI_UNAVAILABLE", "PRODUCTION_CANDIDATE_CONDITIONAL"],
            "fitRisk": "Body mesh recovery is not a photoreal identity/texture generator; gated weights and Windows/12GB viability are unresolved.",
        },
        {
            "id": "CAND-04",
            "name": "GAS",
            "paper": "GAS: Generative Avatar Synthesis from a Single Image, ICCV 2025",
            "paperUrl": "https://arxiv.org/abs/2502.06957",
            "repository": "https://github.com/humansensinglab/GAS",
            "weights": ["yixinglu/GAS (public HF files)"],
            "releaseDate": "2025-08-13 HF checkpoint repository; ICCV 2025",
            "license": "Repository license plus research-only disclaimer; demo media rights remain with their owners",
            "baseArchitecture": "single-image generative avatar model with separate novel-view and novel-pose inference paths",
            "referenceMode": "single image; optional driving video for novel pose",
            "capabilities": {"human": True, "fullBody": True, "camera": "novel-view synthesis", "pose": "novel-pose synthesis", "multiView": "novel view set"},
            "platform": {"windows": "BLOCKED_BY_OFFICIAL_OS_REQUIREMENT", "linux": "OFFICIAL", "comfyui": "NOT_AVAILABLE"},
            "runtime": {"python": "INSTALL.md; not captured in survey", "torch": "repository requirements", "cuda": "NVIDIA CUDA", "vram": "official minimum 20GB"},
            "modelSize": "public weights; exact aggregate size not yet downloaded",
            "activity": "public ICCV 2025 release, 17 repository commits",
            "labels": ["CODE_AVAILABLE", "WEIGHTS_AVAILABLE", "RUNNABLE_PROJECT_LINUX_ONLY", "COMFYUI_UNAVAILABLE", "CLOUD_GPU_CANDIDATE"],
            "fitRisk": "Official minimum 20GB exceeds the local RTX 4070 12GB; do not spend local disk on a doomed download.",
        },
        {
            "id": "CAND-05",
            "name": "Pippo",
            "paper": "Pippo: High-Resolution Multi-View Humans from a Single Image, CVPR 2025",
            "paperUrl": "https://arxiv.org/abs/2412.14414",
            "repository": "https://github.com/facebookresearch/pippo",
            "weights": [],
            "releaseDate": "CVPR 2025",
            "license": "Repository LICENSE; no pretrained inference weights",
            "baseArchitecture": "1K multi-view diffusion transformer from one casual image",
            "referenceMode": "single image",
            "capabilities": {"human": True, "fullBody": True, "camera": "multi-view turnaround cameras", "pose": "viewpoint turnaround, not a pose-driver contract", "multiView": "dense 1K turnaround video"},
            "platform": {"windows": "UNVERIFIED", "linux": "README_CONDA_ORIENTED", "comfyui": "NOT_AVAILABLE"},
            "runtime": {"python": "3.10.1", "torch": "2.4.0", "cuda": "12.0", "vram": "full model training tested A100 80GB; tiny training T4 16GB; inference weights absent"},
            "modelSize": "not applicable for inference because pretrained weights are not released",
            "activity": "public Meta repository, 21 commits, high technical relevance but code-only",
            "labels": ["CODE_AVAILABLE", "PAPER_ONLY_FOR_INFERENCE", "NO_PRETRAINED_WEIGHTS", "NOT_RUN", "FUTURE_CLOUD_POC"],
            "fitRisk": "Cannot perform a valid inference Mini Probe without pretrained weights; training is outside this task.",
        },
        {
            "id": "CAND-06",
            "name": "CharacterGen",
            "paper": "CharacterGen: Efficient 3D Character Generation from Single Images with Multi-View Pose Calibration, SIGGRAPH TOG 2024",
            "paperUrl": "https://arxiv.org/abs/2402.17214",
            "repository": "https://charactergen.github.io/",
            "weights": [],
            "releaseDate": "SIGGRAPH/TOG 2024",
            "license": "Project page Creative Commons Attribution-ShareAlike for website; model/code license not published on the page",
            "baseArchitecture": "image-conditioned multi-view diffusion + sparse-view reconstruction + texture back-projection",
            "referenceMode": "single image",
            "capabilities": {"human": True, "fullBody": True, "camera": "pose-calibrated multi-view", "pose": "canonical pose calibration", "multiView": "four consistent views"},
            "platform": {"windows": "UNVERIFIED", "linux": "UNVERIFIED", "comfyui": "NOT_AVAILABLE"},
            "runtime": {"python": "UNPUBLISHED", "torch": "UNPUBLISHED", "cuda": "UNPUBLISHED", "vram": "UNPUBLISHED"},
            "modelSize": "UNPUBLISHED",
            "activity": "project page still says code/dataset/pretrained weights will be available soon",
            "labels": ["PAPER_ONLY", "NOT_RUN", "NO_LOCAL_ARTIFACT_READY"],
            "fitRisk": "No verified local code/weights package available from the official page at survey time.",
        },
        {
            "id": "CAND-07",
            "name": "MVD-HuGaS",
            "paper": "MVD-HuGaS: Human Gaussians from a Single Image via 3D Human Multi-view Diffusion Prior, 2025",
            "paperUrl": "https://arxiv.org/abs/2503.08218",
            "repository": None,
            "weights": [],
            "releaseDate": "2025-03-11 paper publication",
            "license": "Not established for a runnable model package",
            "baseArchitecture": "multi-view human diffusion prior + camera alignment + optimized 3D Gaussian representation",
            "referenceMode": "single image",
            "capabilities": {"human": True, "fullBody": True, "camera": "free-view 3D Gaussian rendering", "pose": "not an explicit pose-driver contract", "multiView": "generated multi-view images and free-view rendering"},
            "platform": {"windows": "UNVERIFIED", "linux": "UNVERIFIED", "comfyui": "NOT_AVAILABLE"},
            "runtime": {"python": "UNPUBLISHED", "torch": "UNPUBLISHED", "cuda": "UNPUBLISHED", "vram": "UNPUBLISHED"},
            "modelSize": "UNPUBLISHED",
            "activity": "paper page reports no linked model or repository",
            "labels": ["PAPER_ONLY", "NOT_RUN", "NO_LOCAL_ARTIFACT_READY"],
            "fitRisk": "Promising technical family but no official runnable artifact was found during this survey.",
        },
        {
            "id": "CAND-08",
            "name": "HumanGaussian",
            "paper": "HumanGaussian: Text-Driven 3D Human Generation with Gaussian Splatting, 2023",
            "paperUrl": "https://arxiv.org/abs/2311.17061",
            "repository": "https://github.com/alvinliu0/HumanGaussian",
            "weights": ["texture-structure joint model", "SMPL-X", "pretrained avatar PLY gallery"],
            "releaseDate": "2023-11-28 code/pretrained models",
            "license": "MIT repository; third-party model/data terms apply",
            "baseArchitecture": "text-driven SDS 3D Gaussian Splatting with optional SMPL-X animation",
            "referenceMode": "text prompt, not a reference image",
            "capabilities": {"human": True, "fullBody": True, "camera": "3DGS rendering", "pose": "SMPL-X zero-shot animation", "multiView": "renderable 3DGS avatar"},
            "platform": {"windows": "UNVERIFIED", "linux": "README_ORIENTED", "comfyui": "NOT_AVAILABLE"},
            "runtime": {"python": "UNPUBLISHED", "torch": "2.0.1", "cuda": "11.8", "vram": "one-hour optimization on A100 40GB"},
            "modelSize": "guidance plus 3DGS assets; exact aggregate size not collected",
            "activity": "public but not reference-conditioned; low relevance",
            "labels": ["CODE_AVAILABLE", "WEIGHTS_AVAILABLE", "NOT_REFERENCE_CONDITIONED", "NOT_RUN", "LOW_RELEVANCE"],
            "fitRisk": "Does not satisfy the single reference image character identity contract; retained only as a family boundary.",
        },
    ]

    survey = {
        "schema": "character-architecture-replacement.survey.v1",
        "capturedAtUtc": now,
        "minimumCandidateCount": 6,
        "candidateCount": len(candidates),
        "sourcePolicy": "Official project/repository/model pages and primary papers; no paper-only item is marked runnable.",
        "sources": sources,
        "candidates": candidates,
    }

    matrix_rows = [
        {"candidateId": "CAND-01", "technicalFamily": "image-conditioned diffusion + SMPL-X textured mesh", "technicalFit": 5, "artifactAvailability": 5, "local12GBFit": "CONDITIONAL", "windowsFit": "UNVERIFIED", "inputFit": "HEAD_ONLY_RISK", "deploymentAudit": "SELECTED_TOP3_A", "reason": "Strongest complete reference-to-textured-human code path, but it demands full-body/OpenPose/SMPL-X and is Linux/3090 tested."},
        {"candidateId": "CAND-02", "technicalFamily": "semantic decomposed multi-view diffusion + S-LRM", "technicalFit": 5, "artifactAvailability": 5, "local12GBFit": "CONDITIONAL_LOW_VRAM", "windowsFit": "UNVERIFIED", "inputFit": "FULL_BODY_REQUIRED", "deploymentAudit": "SELECTED_TOP3_B", "reason": "Most direct native multi-view generation path with public weights and low_vram option; anime-domain and research-only checkpoint constraints."},
        {"candidateId": "CAND-03", "technicalFamily": "promptable parametric full-body mesh recovery", "technicalFit": 4, "artifactAvailability": 3, "local12GBFit": "UNVERIFIED", "windowsFit": "UNVERIFIED", "inputFit": "FULL_BODY_REQUIRED", "deploymentAudit": "SELECTED_TOP3_C", "reason": "Native 3D camera/pose family and current official release, but texture/identity generation is outside the model and weights are gated."},
        {"candidateId": "CAND-04", "technicalFamily": "generative avatar novel-view/pose video", "technicalFit": 5, "artifactAvailability": 5, "local12GBFit": "BLOCKED_20GB_MIN", "windowsFit": "BLOCKED_LINUX_ONLY", "inputFit": "SINGLE_IMAGE", "deploymentAudit": "NOT_SELECTED_CLOUD_BLOCK", "reason": "Technically closest to target identity/view/pose contract, but official hardware/OS gate exceeds this host."},
        {"candidateId": "CAND-05", "technicalFamily": "multi-view diffusion transformer", "technicalFit": 5, "artifactAvailability": 2, "local12GBFit": "NOT_ASSESSABLE", "windowsFit": "UNVERIFIED", "inputFit": "SINGLE_IMAGE", "deploymentAudit": "NOT_RUN_CODE_ONLY", "reason": "High relevance but official repository explicitly says code-only release without pretrained weights."},
        {"candidateId": "CAND-06", "technicalFamily": "multi-view pose-calibrated diffusion + sparse-view reconstruction", "technicalFit": 5, "artifactAvailability": 1, "local12GBFit": "NOT_ASSESSABLE", "windowsFit": "UNVERIFIED", "inputFit": "SINGLE_IMAGE", "deploymentAudit": "NOT_RUN_PAPER_ONLY", "reason": "Excellent architectural fit on paper, but official page still says code/dataset/weights will be available soon."},
        {"candidateId": "CAND-07", "technicalFamily": "multi-view diffusion prior + 3D Gaussian optimization", "technicalFit": 5, "artifactAvailability": 1, "local12GBFit": "NOT_ASSESSABLE", "windowsFit": "UNVERIFIED", "inputFit": "SINGLE_IMAGE", "deploymentAudit": "NOT_RUN_PAPER_ONLY", "reason": "Relevant 3D-aware family, but no linked official runnable artifact was found."},
        {"candidateId": "CAND-08", "technicalFamily": "text-driven 3D Gaussian Splatting", "technicalFit": 1, "artifactAvailability": 4, "local12GBFit": "BLOCKED_OR_SLOW_40GB_REFERENCE", "windowsFit": "UNVERIFIED", "inputFit": "NO_REFERENCE_CONTRACT", "deploymentAudit": "NOT_SELECTED_LOW_RELEVANCE", "reason": "Useful boundary for 3DGS but fails the single reference identity requirement."},
    ]
    matrix = {
        "schema": "character-architecture-replacement.feasibility.v1",
        "capturedAtUtc": now,
        "scoring": {"technicalFit": "1 low to 5 high", "artifactAvailability": "1 paper-only to 5 runnable public weights", "selectionRule": "technical family diversity plus real deployment probability; not paper quality alone"},
        "rows": matrix_rows,
    }

    top3 = {
        "schema": "character-architecture-replacement.top3.v1",
        "capturedAtUtc": now,
        "selectionStatus": "TOP3_SELECTED_FOR_DEPLOYMENT_AUDIT",
        "top3": [
            {"rank": 1, "candidateId": "CAND-01", "alias": "candidate-a", "architecture": "SiTH", "family": "image-conditioned diffusion + SMPL-X textured mesh", "why": "Complete public single-reference reconstruction path; directly supports textured 3D human and downstream camera/pose."},
            {"rank": 2, "candidateId": "CAND-02", "alias": "candidate-b", "architecture": "StdGEN", "family": "semantic decomposed multi-view diffusion + S-LRM", "why": "Direct six-view image/normal set generation; public weights and low_vram switch allow a 12GB probe despite domain risk."},
            {"rank": 3, "candidateId": "CAND-03", "alias": "candidate-c", "architecture": "SAM 3D Body", "family": "promptable parametric full-body mesh recovery", "why": "Distinct native 3D pose/camera family; audit gated weights and local VRAM before any production interpretation."},
        ],
        "deprioritizedButRecorded": [
            {"candidateId": "CAND-04", "reason": "GAS official minimum 20GB and Linux-only; preserve as cloud GPU reference."},
            {"candidateId": "CAND-05", "reason": "Pippo code-only with no pretrained inference weights."},
            {"candidateId": "CAND-06", "reason": "CharacterGen official page does not publish runnable code/weights."},
            {"candidateId": "CAND-07", "reason": "MVD-HuGaS paper page has no linked runnable artifact."},
            {"candidateId": "CAND-08", "reason": "HumanGaussian is text-driven rather than reference-conditioned."},
        ],
        "gate": {"atLeastTwoTop3MustEnterMiniProbe": True, "ifNot": "ARCHITECTURE_SELECTION_INSUFFICIENT", "mustNotClaimProduction": True},
    }

    (root / "03-candidate-architecture-survey.json").write_text(json.dumps(survey, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "04-candidate-feasibility-matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "05-top-candidate-selection.json").write_text(json.dumps(top3, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"survey": str(root / "03-candidate-architecture-survey.json"), "matrix": str(root / "04-candidate-feasibility-matrix.json"), "top3": str(root / "05-top-candidate-selection.json")}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
