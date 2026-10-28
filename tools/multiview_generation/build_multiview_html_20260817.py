"""Build lightweight, local HTML evidence views without changing QA decisions."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


RUN_ROOT = Path(r"C:\install\AI\Data\QA\multiview_identity_generation_20260817\run_01")


def read(name: str, fallback: Any) -> Any:
    path = RUN_ROOT / name
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8-sig"))


def image_src(value: str | None) -> str:
    if not value:
        return ""
    path = Path(value)
    try:
        relative = path.resolve().relative_to(RUN_ROOT.resolve())
        return relative.as_posix()
    except ValueError:
        return path.resolve().as_uri() if path.exists() else ""


def cell(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, (dict, list)):
        return html.escape(json.dumps(value, ensure_ascii=False))
    return html.escape("" if value is None else str(value))


def render(name: str, title: str, subtitle: str, rows: list[dict[str, Any]], summary: dict[str, Any], fields: list[str]) -> None:
    cards: list[str] = []
    for row in rows:
        source = image_src(row.get("path") or row.get("analysisPath"))
        image = f'<img src="{html.escape(source)}" loading="lazy" alt="candidate" />' if source else '<div class="missing">no image</div>'
        metadata = "".join(f"<tr><th>{html.escape(field)}</th><td>{cell(row.get(field))}</td></tr>" for field in fields)
        cards.append(f'<article class="card">{image}<table>{metadata}</table></article>')
    if not cards:
        cards.append('<div class="blocked">No generated rows. This method is blocked before generation; see the JSON evidence for the exact dependency or hardware preflight reason.</div>')
    summary_rows = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{cell(v)}</td></tr>" for k, v in summary.items())
    content = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#10141b;color:#e9eef5;margin:24px}}h1{{margin-bottom:4px}}.sub{{color:#9da9b8;margin-bottom:18px}}.summary{{background:#1a222d;border:1px solid #344252;padding:12px;display:inline-block;vertical-align:top;margin-right:18px}}table{{border-collapse:collapse;font-size:12px;width:100%}}th,td{{border-bottom:1px solid #33404f;padding:4px;text-align:left;vertical-align:top}}th{{color:#aab8c8;width:42%}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px;margin-top:20px}}.card{{background:#1a222d;border:1px solid #344252;padding:10px;border-radius:8px}}.card img{{display:block;width:100%;max-height:520px;object-fit:contain;background:#090b0f;margin-bottom:8px}}.missing,.blocked{{padding:22px;background:#3a2525;border:1px solid #9d5a5a;color:#ffd5d5}}.pass{{color:#7ce2a1}}.fail{{color:#ff9d9d}}</style></head>
<body><h1>{html.escape(title)}</h1><div class="sub">{html.escape(subtitle)}</div>
<section class="summary"><table>{summary_rows}</table></section>
<section class="grid">{''.join(cards)}</section></body></html>'''
    (RUN_ROOT / name).write_text(content, encoding="utf-8")


def main() -> None:
    head = read("04-faceid-headpose-benchmark.json", {})
    img = read("09-img2img-benchmark.json", {})
    instant = read("06-instantid-benchmark.json", {})
    pulid = read("08-pulid-benchmark.json", {})
    golden = read("13-golden-reference-pack-v3.json", {})
    render("02-headpose-comparison.html", "FaceID + HeadPose comparison", "15-image controlled probe; frozen identity and yaw gates", head.get("rows", []), head.get("summary", {}), ["method", "requestedView", "targetYaw", "yaw", "yawError", "rawCosineSimilarity", "identityPass", "viewPass", "dualPass", "hardRejectFlags"])
    render("03-instantid-comparison.html", "InstantID comparison", instant.get("blocker", "blocked"), instant.get("rows", []), instant.get("summary", {}), ["requestedView", "rawCosineSimilarity", "identityPass", "viewPass", "dualPass", "hardRejectFlags"])
    render("04-pulid-comparison.html", "PuLID comparison", pulid.get("blocker", "blocked"), pulid.get("rows", []), pulid.get("summary", {}), ["requestedView", "rawCosineSimilarity", "identityPass", "viewPass", "dualPass", "hardRejectFlags"])
    render("05-img2img-comparison.html", "Img2Img A/B/C/D comparison", "24-image SD1.5 controlled matrix; 30/45-degree views and three denoise levels", img.get("rows", []), img.get("summary", {}), ["method", "requestedView", "denoise", "targetYaw", "yaw", "yawError", "rawCosineSimilarity", "identityPass", "viewPass", "dualPass", "hardRejectFlags"])
    all_rows = head.get("rows", []) + img.get("rows", [])
    render("06-all-methods-comparison.html", "All available methods comparison", "Only completed image-producing rows are shown; blocked InstantID/PuLID remain explicitly blocked", all_rows, {"headPose": head.get("summary", {}), "img2img": img.get("summary", {}), "instantId": instant.get("status"), "puLid": pulid.get("status")}, ["method", "requestedView", "denoise", "targetYaw", "yaw", "rawCosineSimilarity", "identityPass", "viewPass", "dualPass"])
    golden_rows = golden.get("goldenPack", []) + golden.get("newReviewCandidates", [])
    render("07-golden-reference-v3.html", "Golden reference pack v3", "No new Golden is promoted unless the frozen gates and manual review support it", golden_rows, {"status": golden.get("status"), "count": golden.get("count"), "goldenByView": golden.get("goldenByView")}, ["goldenId", "requestedView", "method", "seed", "path", "autoRecommended", "manualReviewRequired", "qualification"])


if __name__ == "__main__":
    main()
