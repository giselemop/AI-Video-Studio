"""Build versioned local three-shot InfiniteTalk graphs; never submit inference.

Input is the list written by audio.py at audio/shot-definitions.json. Each item
needs index, startSeconds, endSeconds, durationSeconds, femaleAudio and maleAudio.
The caller pads each selected audio track to native_frames(shot) / 25 seconds and
binds it through the declared input slots. References are prepared separately.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[2]
AI = ROOT.parent
DATA = AI / "Data" / "DialogueThreeShot20261023"
DEFAULT_SHOTS = DATA / "audio" / "shot-definitions.json"
CONTRACT_PATH = ROOT / "config" / "workflow-contracts.json"
SOURCE_CONTRACT = "infinitetalk-dialogue-241-v2"

PROMPTS = {
    1: (
        "A photorealistic live-action medium close-up of the exact same adult East Asian woman from the reference image, "
        "sitting on the cream sofa, beige knitted cardigan and cream blouse, long wavy dark hair. "
        "She looks to screen right toward the man sitting beside her, keeps her gaze engaged in their conversation, "
        "slightly raises one eyebrow while teasing him warmly in Mandarin according to her audio, then lets the expression "
        "settle into an amused, restrained smile. Subtle natural lip articulation, small cheek and eyebrow reactions, "
        "gentle breathing and a tiny shoulder movement. Her mouth rests after the utterance. "
        "Stable identity, hair, clothes and background, realistic skin, warm afternoon window light from the same room. "
        "One visible person, fixed camera, small natural movements, continuous single shot."
    ),
    2: (
        "A photorealistic live-action reverse medium close-up of the exact same adult East Asian man from the reference image, "
        "sitting on the cream sofa, olive green cardigan over a dark T-shirt, short black hair and light stubble. "
        "He lifts his eyes slightly from the phone toward the woman at screen left and answers in Mandarin according to his "
        "audio with playful mock indignation, a restrained half-smile and a minimal shoulder shrug. He remains engaged "
        "with her, then listens with a relaxed attentive expression. Subtle natural lip articulation and eyebrows, "
        "gentle breathing. His mouth rests when the audio stops. Stable identity, hair, clothes and room, realistic skin, "
        "warm afternoon window light matching the reference. One visible person, fixed camera, small natural movements, "
        "continuous single shot."
    ),
    3: (
        "A photorealistic live-action two-person medium shot of the exact same East Asian adults sitting beside each other "
        "on a cream sofa. The woman on the LEFT has long wavy dark hair and wears a beige knitted cardigan and cream blouse. "
        "The man on the RIGHT has short black hair and light stubble and wears an olive cardigan over a dark T-shirt. "
        "They alternate speaking Mandarin according to their own audio tracks. The woman softens her teasing smile, "
        "relaxes her shoulders and gently reassures him. The man looks toward her and listens quietly; when his own reply "
        "starts he answers with a small satisfied smile, then gives one tiny nod and meets her gaze. "
        "The listener stays silent with a subtle responsive expression. Natural synchronized lips, small restrained eyebrow "
        "and cheek reactions, gentle breathing, no broad head turns. Stable identities, clothes, hands, phone and room, "
        "realistic skin, warm afternoon window light. Fixed camera and a continuous single shot."
    ),
}
NEGATIVE = (
    "cartoon, doll, plastic skin, beauty filter, overexposure, blurry face, duplicated person, merged bodies, "
    "deformed mouth, huge open mouth, extra teeth, talking in unison, extra people, face morphing, identity change, "
    "looking away from the conversation, exaggerated head turn, exaggerated laughter, large gestures, standing, "
    "touching another person, camera movement, cuts, text, watermark"
)


def native_frames(shot):
    return math.ceil(float(shot["durationSeconds"]) * 25) + 1


def load_shots(path):
    shots = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(shots, list) or [x.get("index") for x in shots] != [1, 2, 3]:
        raise ValueError("Expected exactly three ordered shot definitions, indexed 1, 2, 3")
    previous = 0.0
    for shot in shots:
        start, end, duration = (float(shot[k]) for k in ("startSeconds", "endSeconds", "durationSeconds"))
        if not all(math.isfinite(x) for x in (start, end, duration)) or duration <= 0:
            raise ValueError("Invalid shot timing")
        if abs(start - previous) > 1e-7 or abs(end - start - duration) > 1e-7:
            raise ValueError("Shot definitions must be contiguous and have matching durations")
        for role in ("femaleAudio", "maleAudio"):
            value = shot.get(role)
            if not isinstance(value, str) or not value:
                raise ValueError("Each shot needs both separated audio paths")
            path_under_data = (AI / "Data" / value).resolve()
            if not path_under_data.is_relative_to((AI / "Data").resolve()):
                raise ValueError("Audio paths must stay inside controlled Data")
        if native_frames(shot) > 251:
            raise ValueError("Unexpected shot longer than the ten-second local sample")
        previous = end
    if abs(previous - 10.0) > 1e-7:
        raise ValueError("The final cut must total exactly ten seconds")
    return shots


def pinned_models(doc):
    source = next((c for c in doc["contracts"] if c.get("id") == SOURCE_CONTRACT), None)
    if source is None:
        raise ValueError("Previously verified pilot model contract is missing")
    names, hashes = source.get("modelFiles"), source.get("modelSha256")
    if not isinstance(names, list) or len(names) != 6 or not isinstance(hashes, dict):
        raise ValueError("Previously verified six-model manifest is incomplete")
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(hashes.get(name, ""))) for name in names):
        raise ValueError("Previously verified model SHA manifest is incomplete")
    return copy.deepcopy(names), copy.deepcopy(hashes)


def make_graph(shot, split_ratio=.38):
    index = shot["index"]
    frames = native_frames(shot)

    def node(cls, **inputs):
        return dict(class_type=cls, inputs=inputs)

    speaker_role = "femaleAudio" if index == 1 else "maleAudio"
    graph = {
        "1": node("LoadImage", image=f"reference-{index}.png"),
        "2": node("LoadAudio", audio=Path(shot[speaker_role if index < 3 else "femaleAudio"]).name),
        "5": node("VideoStudioNativeWanTextCached", model_name="umt5_xxl_fp8_e4m3fn_scaled.safetensors", positive=PROMPTS[index], negative=NEGATIVE),
        "6": node("Wav2VecModelLoader", model="wav2vec2-chinese-base_fp16.safetensors", base_precision="fp16", load_device="offload_device"),
        "7": node("MultiTalkWav2VecEmbeds", wav2vec_model=["6", 0], audio_1=["2", 0], normalize_loudness=False,
                  num_frames=frames, fps=25.0, audio_scale=1.0, audio_cfg_scale=1.0, multi_audio_type="para", add_noise_floor=False, smooth_transients=False),
        "8": node("MultiTalkModelLoader", model="Wan2_1-InfiniteTalk_Multi_Q8.gguf"),
        "9": node("VideoStudioAudioModelAfterText", model=["8", 0], text=["5", 0]),
        "10": node("WanVideoBlockSwap", blocks_to_swap=30, offload_img_emb=True, offload_txt_emb=True, use_non_blocking=False,
                   vace_blocks_to_swap=0, prefetch_blocks=0, block_swap_debug=False),
        "11": node("WanVideoLoraSelect", lora="lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors", strength=1.0, low_mem_load=True, merge_loras=False),
        "12": node("WanVideoModelLoader", model="wan2.1-i2v-14b-480p-Q4_K_M.gguf", base_precision="bf16", quantization="disabled",
                   load_device="offload_device", attention_mode="sdpa", block_swap_args=["10", 0], lora=["11", 0], multitalk_model=["9", 0]),
        "13": node("WanVideoVAELoader", model_name="Wan2_1_VAE_bf16.safetensors", precision="bf16", use_cpu_cache=False, verbose=False),
        "14": node("WanVideoImageToVideoMultiTalk", vae=["13", 0], width=832, height=480, frame_window_size=81, motion_frame=9,
                   force_offload=True, colormatch="disabled", start_image=["1", 0], tiled_vae=True, mode="infinitetalk", output_path=""),
        "15": node("WanVideoSampler", model=["12", 0], image_embeds=["14", 0], text_embeds=["5", 0], multitalk_embeds=["7", 0],
                   steps=6, cfg=1.0, shift=11.0, seed=2026102350 + index, force_offload=True, scheduler="dpm++_sde",
                   riflex_freq_index=0, denoise_strength=1.0, batched_cfg=False, rope_function="comfy"),
        "16": node("WanVideoPassImagesFromSamples", samples=["15", 0]),
        "19": node("ImageFromBatch", image=["16", 0], batch_index=0, length=frames),
        "17": node("CreateVideo", images=["19", 0], audio=["7", 1], fps=25.0),
        "18": node("SaveVideo", video=["17", 0], filename_prefix=f"dialogue_three_shot_{index}", format="mp4", codec="h264"),
    }
    if index == 3:
        graph["3"] = node("LoadAudio", audio=Path(shot["maleAudio"]).name)
        graph["4"] = node("VideoStudioDialogueSpeakerMasks", image=["1", 0], split_ratio=split_ratio)
        graph["7"]["inputs"].update(audio_2=["3", 0], ref_target_masks=["4", 0])
    return graph


def make_contract(shot, graph, models, hashes):
    index, frames = shot["index"], native_frames(shot)
    encoded = json.dumps(graph, ensure_ascii=False, indent=2).encode("utf-8")
    version = f"dialogue-three-shot-{index}-v1"
    roles = [("firstFrame", "1", "LoadImage", "image")]
    roles += [("speakerAudio", "2", "LoadAudio", "audio")] if index < 3 else [
        ("femaleAudio", "2", "LoadAudio", "audio"), ("maleAudio", "3", "LoadAudio", "audio")]
    return dict(
        id=version, version=version, fileName=f"dialogue_three_shot_{index}_v1_api.json", workflowType="ImageToVideo",
        productionEligible=False, experimental=True, licenseStatus="LOCAL_ONLY_PENDING_REVIEW", taskTypes=["ImageToVideo"],
        modelFiles=models, modelSha256=hashes,
        nodes=[dict(role=role, nodeId=node_id, classType=cls, inputName=field) for role, node_id, cls, field in [
            ("output", "18", "SaveVideo", "filename_prefix"), ("sampler", "15", "WanVideoSampler", "seed"),
            ("positivePrompt", "5", "VideoStudioNativeWanTextCached", "positive"),
            ("negativePrompt", "5", "VideoStudioNativeWanTextCached", "negative"),
            ("exactFrameTrim", "19", "ImageFromBatch", "length")]],
        slots=[dict(role=role, nodeId=node_id, classType=cls, inputName=field, required=True) for role, node_id, cls, field in roles],
        media=dict(defaultWidth=832, defaultHeight=480, allowedDimensions=[dict(width=832, height=480)], outputFrames=[frames],
                   nativeFps=25, allowedFps=[25], exactFrameCount=True, preserveAudio=True),
        notes=f"sha256={hashlib.sha256(encoded).hexdigest()} | local three-shot {index}; exact decoded frame trim; caller pads audio to {frames}/25 seconds; visual and voice review required")


def prepare(shots_path=DEFAULT_SHOTS, split_ratio=.38):
    if not .1 <= split_ratio <= .9:
        raise ValueError("Two-person mask split must lie between .1 and .9")
    shots = load_shots(shots_path)
    original_bytes = CONTRACT_PATH.read_bytes()
    doc = json.loads(original_bytes)
    models, hashes = pinned_models(doc)
    prepared = []
    for shot in shots:
        graph = make_graph(shot, split_ratio)
        contract = make_contract(shot, graph, models, hashes)
        path = AI / "Workflows" / contract["fileName"]
        encoded = json.dumps(graph, ensure_ascii=False, indent=2).encode("utf-8")
        if path.exists() and path.read_bytes() != encoded:
            raise RuntimeError(f"Existing graph differs; create a new version: {path.name}")
        matches = [c for c in doc["contracts"] if c.get("id") == contract["id"] or c.get("version") == contract["version"]
                   or c.get("fileName") == contract["fileName"]]
        if len(matches) > 1 or (matches and matches[0] != contract):
            raise RuntimeError(f"Existing contract differs; create a new version: {contract['id']}")
        if not matches:
            doc["contracts"].append(contract)
        prepared.append((shot, path, encoded, contract))
    DATA.mkdir(parents=True, exist_ok=True)
    backup = DATA / "workflow-contracts-before-three-shot.json"
    if not backup.exists():
        shutil.copy2(CONTRACT_PATH, backup)
    for _, path, encoded, _ in prepared:
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(encoded)
    updated_bytes = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if CONTRACT_PATH.read_bytes() != original_bytes:
        raise RuntimeError("Contract configuration changed concurrently; preserved it, rerun after inspection")
    if updated_bytes != original_bytes:
        CONTRACT_PATH.write_bytes(updated_bytes)
    return [dict(index=shot["index"], workflowVersion=contract["version"], workflowName=path.stem, fileName=path.name,
                 nativeFrames=native_frames(shot), nativeFps=25, nativeDurationSeconds=native_frames(shot) / 25,
                 cutDurationSeconds=shot["durationSeconds"], referenceName=f"reference-{shot['index']}.png",
                 slots=[s["role"] for s in contract["slots"]]) for shot, path, _, contract in prepared]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shots", type=Path, default=DEFAULT_SHOTS)
    parser.add_argument("--split-ratio", type=float, default=.38)
    args = parser.parse_args()
    print(json.dumps(prepare(args.shots, args.split_ratio), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
