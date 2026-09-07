#!/usr/bin/env python3
"""Validate schema 4.0 evidence-locked video-recreation deliverables."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
import re
import sys
from pathlib import Path


PLACEHOLDER = re.compile(r"\bTODO\b|\bNEEDS_INPUT\b|\[待填写\]|\[TODO\]", re.I)
BANNED = re.compile(
    r"@(?:视频|影片|图片|圖像)(?:\s*\d+)?|参考映射|参考(?:视频|影片|原片|素材)|源视频|"
    r"(?:依照|按照|根据)原片|(?:^|[\s；。])(?:入口|出口)(?:状态)?[：:]|片段(?:入口|出口)|"
    r"(?:入口|出口)状态|承接(?:上一段|前一段)|延续(?:上一段|前一段)|"
    r"(?:上一段|下一段|前一段|后一段)(?:生成|视频|画面|内容|出口|入口)|"
    r"忠实复刻上一段|再次上传|reference\s+video|previous\s+segment|next\s+segment",
    re.I,
)
CAMERA_REQUIRED = ("equipment_name", "lens_name", "focal_length", "aperture", "camera_height_angle", "composition", "movement", "focus_depth")
VISUAL_MASTER_REQUIRED = ("core_style", "visual_tone", "color_system", "tonal_structure")
BEAT_REQUIRED = ("beat_id", "subject_asset_id", "subject", "actor_type", "object_asset_ids", "start", "end", "action", "object_or_target", "spatial_relation", "motion_rhythm", "physical_feedback", "timeline_fact", "timeline_required", "evidence_status")
PERFORMANCE_REQUIRED = ("emotion_intent", "visible_expression", "gaze_target", "preparation", "execution", "follow_through", "settle")
APPEARANCE_REQUIRED = (
    "event_id", "asset_id", "appearance_type", "start", "end", "prior_visibility", "source_space",
    "reveal_trigger", "entry_direction", "frame_region", "first_visible_part", "initial_pose_state",
    "emergence_motion", "first_visible_action", "completion_state", "observer_reaction", "evidence_frame_refs",
    "timeline_fact", "timeline_required", "evidence_status",
)
PROMPT_HEADINGS = ("【生成任务】", "【基础设定】", "【氛围质感】", "【时间轴】")
INTERNAL_FIELD_LABELS = re.compile(r"(?:^|[；。\s])(?:主体|位置关系|动作|对象或目标|节奏|表演状态|物理反馈)[：:]", re.I)
PRODUCTION_META = re.compile(r"换底片|底片替换|Alpha\s*通道|合成节点|渲染通道|后期软件", re.I)
INTERACTION_KINDS = {"ownership_transfer", "trajectory", "handoff"}
INTERACTION_PHASES = {
    "trigger", "launch", "transit", "contact", "capture", "ownership_transfer",
    "carry", "return", "result", "observer_response", "settle",
}
OWNERSHIP_PHASE_GROUPS = (
    {"trigger", "launch"},
    {"contact", "capture", "ownership_transfer"},
    {"carry", "return"},
    {"result", "observer_response", "settle"},
)
OWNERSHIP_PHASE_STAGE = {
    "trigger": 0,
    "launch": 1,
    "transit": 1,
    "contact": 2,
    "capture": 2,
    "ownership_transfer": 2,
    "carry": 3,
    "return": 3,
    "result": 4,
    "observer_response": 4,
    "settle": 4,
}


def normalized_clauses(text: str) -> list[tuple[str, str]]:
    clauses = []
    for raw in re.split(r"[。！？；\n]+", text):
        display = raw.strip(" ：:\t")
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", display, flags=re.UNICODE).casefold()
        camera_prefixes = ("摄影：", "RECREATION_SPEC", "设备：", "镜头：", "焦段：", "光圈：", "机位与角度：", "构图：", "运镜：", "对焦与景深：")
        if len(normalized) >= 18 and not display.startswith("【") and not display.startswith(camera_prefixes):
            clauses.append((display, normalized))
    return clauses


def repeated_prompt_clause(text: str) -> tuple[str, str] | None:
    clauses = normalized_clauses(text)
    for index, (left_display, left) in enumerate(clauses):
        for right_display, right in clauses[index + 1 :]:
            length_ratio = min(len(left), len(right)) / max(len(left), len(right))
            if left == right or (length_ratio >= 0.88 and SequenceMatcher(None, left, right).ratio() >= 0.96):
                return left_display, right_display
    return None


def atmosphere_has_camera(text: str) -> bool:
    return bool(re.search(r"摄影方案|摄影实现方案|摄影：?RECREATION_SPEC|RECREATION_SPEC\s*[｜|]\s*设备", text, re.I))


def canonical_state(value: object) -> str:
    return re.sub(r"[\s。；;]+", "", str(value or "")).casefold()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--prompt-data", type=Path, help="Internal prompt-data.json used to build the storyboard")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    root = args.output_dir
    errors: list[str] = []
    screenplay = root / "01-完整故事剧本.md"
    storyboard = root / "02-图文分镜故事板"
    for path in (screenplay, storyboard):
        if not path.exists():
            errors.append(f"Missing: {path.name}")
    if screenplay.is_file():
        text = screenplay.read_text(encoding="utf-8")
        if len(text.strip()) < 100:
            errors.append(f"Too little content: {screenplay.name}")
        if PLACEHOLDER.search(text):
            errors.append(f"Placeholder remains: {screenplay.name}")
    allowed_top_level = {screenplay.name, storyboard.name}
    if root.is_dir():
        for path in root.iterdir():
            if path.name not in allowed_top_level:
                errors.append(f"Unexpected duplicate delivery: {path.name}")

    prompt_data_path = args.prompt_data
    segment_ids: set[str] = set()
    referenced_shots: set[str] = set()
    expected_refs: set[str] = set()
    asset_ids: set[str] = set()
    asset_frame_refs: set[str] = set()
    source_duration = 0.0
    data: dict = {}
    visual_master: dict = {}
    if prompt_data_path is None or not prompt_data_path.is_file():
        errors.append("Missing internal --prompt-data prompt-data.json")
    else:
        data = json.loads(prompt_data_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != "4.0":
            errors.append("prompt-data.json must use schema_version 4.0")
        source_duration = float(data.get("source_duration") or 0)
        if source_duration <= 0:
            errors.append("Invalid source_duration")
        global_consistency = str(data.get("global_consistency") or "")
        if not global_consistency:
            errors.append("Missing global_consistency")
        elif BANNED.search(global_consistency):
            errors.append("global_consistency depends on reference media/context")
        visual_master = data.get("visual_master")
        if not isinstance(visual_master, dict):
            errors.append("Missing visual_master")
            visual_master = {}
        for key in VISUAL_MASTER_REQUIRED:
            value = str(visual_master.get(key) or "").strip()
            if not value:
                errors.append(f"Missing visual_master.{key}")
            elif BANNED.search(value):
                errors.append(f"Reference-dependent visual master: {key}")

        library = data.get("asset_library")
        if not isinstance(library, dict):
            errors.append("Missing asset_library")
            library = {}
        prefixes = {"characters": "CHAR", "props": "PROP", "locations": "LOC"}
        for group, prefix in prefixes.items():
            items = library.get(group)
            if not isinstance(items, list):
                errors.append(f"Missing asset category: {group}")
                continue
            for asset in items:
                asset_id = str(asset.get("asset_id", ""))
                if not re.fullmatch(prefix + r"\d{3,}", asset_id) or asset_id in asset_ids:
                    errors.append(f"Invalid or duplicate asset_id: {asset_id}")
                asset_ids.add(asset_id)
                for key in ("name", "description_prompt", "narrative_function", "continuity_lock", "evidence_status"):
                    if not str(asset.get(key, "")).strip():
                        errors.append(f"Missing {key}: {asset_id}")
                for key in ("description_prompt", "continuity_lock"):
                    if BANNED.search(str(asset.get(key, ""))):
                        errors.append(f"Reference-dependent asset text: {asset_id}.{key}")
                refs = [str(value) for value in asset.get("frame_refs", [])]
                if not refs:
                    errors.append(f"Missing asset frame_refs: {asset_id}")
                asset_frame_refs.update(refs)
        if not asset_ids:
            errors.append("Asset library has no assets")

        segments = data.get("segments", [])
        if not segments:
            errors.append("prompt-data.json has no segments")
        previous_end = None
        seen_visible_characters: set[str] = set()
        for index, segment in enumerate(segments):
            segment_id = str(segment.get("segment_id", ""))
            if not re.fullmatch(r"P\d{3,}", segment_id) or segment_id in segment_ids:
                errors.append(f"Invalid or duplicate segment_id: {segment_id}")
            segment_ids.add(segment_id)
            start = float(segment.get("start", -1))
            end = float(segment.get("end", -1))
            duration = float(segment.get("duration", -1))
            if end <= start or abs(duration - (end - start)) > 0.02:
                errors.append(f"Invalid segment duration: {segment_id}")
            if index == 0 and abs(start) > 0.05:
                errors.append(f"First segment does not start at zero: {segment_id}")
            if previous_end is not None and abs(start - previous_end) > 0.05:
                errors.append(f"Segment gap/overlap before {segment_id}")
            previous_end = end
            shot_ids = [str(value) for value in segment.get("shot_ids", [])]
            referenced_shots.update(shot_ids)
            times = [float(value) for value in segment.get("keyframe_times", [])]
            if len(times) < max(2, len(shot_ids)) or times != sorted(times):
                errors.append(f"Invalid keyframe_times: {segment_id}")
            refs_for_segment = {f"{segment_id}-node-{node:02d}" for node in range(1, len(times) + 1)}
            expected_refs.update(refs_for_segment)
            assets_used = [str(value) for value in segment.get("assets_used", [])]
            if not assets_used or any(value not in asset_ids for value in assets_used):
                errors.append(f"Invalid assets_used: {segment_id}")
            for key in ("summary", "segment_consistency", "avoid", "full_prompt"):
                value = str(segment.get(key, ""))
                if not value.strip():
                    errors.append(f"Missing {key}: {segment_id}")
                if key != "summary" and BANNED.search(value):
                    errors.append(f"Reference-dependent wording: {segment_id}.{key}")
            full_prompt = str(segment.get("full_prompt", ""))
            heading_positions = [full_prompt.find(heading) for heading in PROMPT_HEADINGS]
            if any(position < 0 for position in heading_positions) or heading_positions != sorted(heading_positions):
                errors.append(f"Invalid full_prompt section order: {segment_id}")
            atmosphere_start = full_prompt.find("【氛围质感】")
            timeline_start = full_prompt.find("【时间轴】")
            atmosphere_text = full_prompt[atmosphere_start:timeline_start] if atmosphere_start >= 0 and timeline_start > atmosphere_start else ""
            if atmosphere_has_camera(atmosphere_text):
                errors.append(f"Camera plan must not appear in atmosphere: {segment_id}")
            atmosphere_labels = ("全片视觉母版：", "核心风格：", "视觉基调：", "色彩体系：", "影调结构：", "本段光影与色彩", "声音设计")
            atmosphere_positions = [atmosphere_text.find(label) for label in atmosphere_labels]
            if any(position < 0 for position in atmosphere_positions) or atmosphere_positions != sorted(atmosphere_positions):
                errors.append(f"Invalid atmosphere structure: {segment_id}")
            for key in VISUAL_MASTER_REQUIRED:
                value = str(visual_master.get(key) or "")
                if value and atmosphere_text.count(value) != 1:
                    errors.append(f"Visual master missing or repeated in full_prompt: {segment_id}.{key}")
            repeated = repeated_prompt_clause(full_prompt)
            if repeated:
                errors.append(f"Repeated or near-duplicate full_prompt wording: {segment_id} -> {repeated[0]!r} / {repeated[1]!r}")
            timeline_text = full_prompt[heading_positions[-1] :] if heading_positions and heading_positions[-1] >= 0 else full_prompt
            if INTERNAL_FIELD_LABELS.search(timeline_text):
                errors.append(f"Timeline exposes internal field labels: {segment_id}")
            if PRODUCTION_META.search(timeline_text):
                errors.append(f"Timeline contains non-visual production wording: {segment_id}")
            timeline_events = segment.get("timeline_events", [])
            timeline_source_refs: list[str] = []
            if not isinstance(timeline_events, list) or not timeline_events:
                errors.append(f"Missing timeline_events: {segment_id}")
            else:
                previous_event_start = -1.0
                max_event_end = 0.0
                for event_index, event in enumerate(timeline_events):
                    try:
                        event_start = float(event.get("start", -1))
                        event_end = float(event.get("end", -1))
                    except (AttributeError, TypeError, ValueError):
                        errors.append(f"Invalid timeline event: {segment_id}[{event_index}]")
                        continue
                    event_text = str(event.get("text", "")).strip()
                    if not event_text or event_start < 0 or event_end <= event_start or event_end > duration + 0.05:
                        errors.append(f"Invalid timeline event: {segment_id}[{event_index}]")
                    if event_start < previous_event_start:
                        errors.append(f"Timeline events out of order: {segment_id}[{event_index}]")
                    if INTERNAL_FIELD_LABELS.search(event_text) or PRODUCTION_META.search(event_text):
                        errors.append(f"Invalid timeline event wording: {segment_id}[{event_index}]")
                    refs = [str(value) for value in event.get("source_refs", [])]
                    if not refs or len(refs) != len(set(refs)):
                        errors.append(f"Invalid timeline source_refs: {segment_id}[{event_index}]")
                    timeline_source_refs.extend(refs)
                    previous_event_start = event_start
                    max_event_end = max(max_event_end, event_end)
                try:
                    first_event_start = float(timeline_events[0].get("start", -1))
                except (AttributeError, TypeError, ValueError):
                    first_event_start = -1.0
                if first_event_start < 0 or first_event_start > 0.05 or abs(max_event_end - duration) > 0.05:
                    errors.append(f"Timeline events do not cover segment bounds: {segment_id}")
            timeline_continuity = str(segment.get("timeline_continuity", "")).strip()
            if not timeline_continuity:
                errors.append(f"Missing timeline_continuity: {segment_id}")
            elif INTERNAL_FIELD_LABELS.search(timeline_continuity) or PRODUCTION_META.search(timeline_continuity):
                errors.append(f"Invalid timeline_continuity wording: {segment_id}")
            used_frame_refs: set[str] = set()
            shot_prompts = segment.get("shot_prompts", [])
            if len(shot_prompts) != len(shot_ids):
                errors.append(f"shot_prompts count mismatch: {segment_id}")
            prompt_ids = [str(shot.get("shot_id", "")) for shot in shot_prompts]
            if prompt_ids != shot_ids:
                errors.append(f"shot_prompts id/order mismatch: {segment_id}")
            prior_shot_end = start
            source_facts: dict[str, dict] = {}
            source_owners: dict[str, str] = {}
            shot_map: dict[str, dict] = {}
            interaction_chains: dict[str, list[dict]] = {}
            first_appearance_assets: list[str] = []
            for shot in shot_prompts:
                shot_id = str(shot.get("shot_id", ""))
                shot_map[shot_id] = shot
                shot_start = float(shot.get("start", -1))
                shot_end = float(shot.get("end", -1))
                shot_duration = float(shot.get("duration", -1))
                if shot_end <= shot_start or abs(shot_duration - (shot_end - shot_start)) > 0.02:
                    errors.append(f"Invalid shot duration: {shot_id}")
                if abs(shot_start - prior_shot_end) > 0.05:
                    errors.append(f"Shot timeline gap before: {shot_id}")
                prior_shot_end = shot_end
                shot_rel_start = shot_start - start
                shot_rel_end = shot_end - start
                refs = [str(value) for value in shot.get("frame_refs", [])]
                if not refs or any(value not in refs_for_segment for value in refs):
                    errors.append(f"Invalid frame_refs: {shot_id}")
                used_frame_refs.update(refs)
                present_entities = [str(value) for value in shot.get("present_entities", [])]
                if not present_entities or any(value not in asset_ids for value in present_entities):
                    errors.append(f"Invalid present_entities: {shot_id}")
                beats = shot.get("action_beats", [])
                if not beats:
                    errors.append(f"Missing action beats: {shot_id}")
                for beat in beats:
                    for key in BEAT_REQUIRED:
                        if not str(beat.get(key, "")).strip():
                            errors.append(f"Missing action relation {key}: {shot_id}")
                    beat_id = str(beat.get("beat_id", ""))
                    if beat_id in source_facts:
                        errors.append(f"Duplicate source id: {segment_id}.{beat_id}")
                    source_facts[beat_id] = beat
                    source_owners[beat_id] = shot_id
                    try:
                        source_start, source_end = float(beat.get("start", -1)), float(beat.get("end", -1))
                        if source_start < shot_rel_start - 0.02 or source_end > shot_rel_end + 0.02:
                            errors.append(f"Cross-shot source range: {shot_id}.{beat_id}")
                    except (TypeError, ValueError):
                        errors.append(f"Invalid source range: {shot_id}.{beat_id}")
                    subject_id = str(beat.get("subject_asset_id", ""))
                    if subject_id not in {"CAMERA", "GRAPHICS", "ENVIRONMENT"} and subject_id not in present_entities:
                        errors.append(f"Cross-shot subject pollution: {shot_id}.{beat_id}")
                    if any(str(value) not in present_entities for value in beat.get("object_asset_ids", [])):
                        errors.append(f"Cross-shot object pollution: {shot_id}.{beat_id}")
                    performance = beat.get("performance_chain")
                    if beat.get("actor_type") in {"character", "creature"}:
                        if not isinstance(performance, dict) or any(not str(performance.get(key, "")).strip() for key in PERFORMANCE_REQUIRED):
                            errors.append(f"Missing visible performance chain: {shot_id}.{beat_id}")
                    elif performance is not None:
                        errors.append(f"Performance chain assigned to non-character: {shot_id}.{beat_id}")
                    chain_id = beat.get("interaction_chain_id")
                    chain_values = (
                        beat.get("interaction_kind"), beat.get("interaction_object_ids"),
                        beat.get("interaction_phase"), beat.get("state_in"), beat.get("state_out"),
                    )
                    if chain_id is not None or any(value is not None for value in chain_values):
                        interaction_kind = str(beat.get("interaction_kind") or "")
                        interaction_objects = [str(value) for value in (beat.get("interaction_object_ids") or [])]
                        interaction_phase = str(beat.get("interaction_phase") or "")
                        bound_assets = {subject_id, *[str(value) for value in beat.get("object_asset_ids", [])]}
                        if (
                            not re.fullmatch(r"X\d{3,}", str(chain_id or ""))
                            or interaction_kind not in INTERACTION_KINDS
                            or not interaction_objects
                            or len(interaction_objects) != len(set(interaction_objects))
                            or interaction_phase not in INTERACTION_PHASES
                            or not str(beat.get("state_in") or "").strip()
                            or not str(beat.get("state_out") or "").strip()
                            or any(value not in bound_assets for value in interaction_objects)
                        ):
                            errors.append(f"Incomplete interaction chain fields: {shot_id}.{beat_id}")
                        else:
                            if beat.get("timeline_required") is not True:
                                errors.append(f"Interaction chain phase omitted from timeline: {shot_id}.{beat_id}")
                            interaction_chains.setdefault(str(chain_id), []).append({
                                "start": float(beat.get("start", -1)),
                                "end": float(beat.get("end", -1)),
                                "shot_id": shot_id,
                                "phase": interaction_phase,
                                "kind": interaction_kind,
                                "objects": tuple(interaction_objects),
                                "state_in": str(beat.get("state_in")),
                                "state_out": str(beat.get("state_out")),
                            })
                for event in shot.get("first_appearance_events", []):
                    event_id = str(event.get("event_id", ""))
                    if event_id in source_facts:
                        errors.append(f"Duplicate source id: {segment_id}.{event_id}")
                    source_facts[event_id] = event
                    source_owners[event_id] = shot_id
                    first_appearance_assets.append(str(event.get("asset_id", "")))
                    for key in APPEARANCE_REQUIRED:
                        value = event.get(key)
                        if key == "evidence_frame_refs":
                            appearance_refs = [str(item) for item in (value or [])]
                            if len(appearance_refs) < 2 or len(appearance_refs) != len(set(appearance_refs)) or any(item not in refs for item in appearance_refs):
                                errors.append(f"Invalid first appearance evidence frames: {shot_id}.{event_id}")
                        elif not str(value or "").strip():
                            errors.append(f"Missing first appearance {key}: {shot_id}.{event_id}")
                    try:
                        source_start, source_end = float(event.get("start", -1)), float(event.get("end", -1))
                        if source_start < shot_rel_start - 0.02 or source_end > shot_rel_end + 0.02:
                            errors.append(f"Cross-shot first appearance range: {shot_id}.{event_id}")
                    except (TypeError, ValueError):
                        errors.append(f"Invalid first appearance range: {shot_id}.{event_id}")
                layer_types = set()
                for event in shot.get("layer_events", []):
                    event_id = str(event.get("event_id", ""))
                    if event_id in source_facts:
                        errors.append(f"Duplicate source id: {segment_id}.{event_id}")
                    source_facts[event_id] = event
                    source_owners[event_id] = shot_id
                    layer_types.add(str(event.get("layer_type", "")))
                if "text_graphics" in shot:
                    errors.append(f"Legacy mixed text_graphics field remains: {shot_id}")
                for event in shot.get("impact_events", []):
                    event_id = str(event.get("event_id", ""))
                    if event_id in source_facts:
                        errors.append(f"Duplicate source id: {segment_id}.{event_id}")
                    source_facts[event_id] = event
                    source_owners[event_id] = shot_id
                    center = float(event.get("source_time", -1))
                    dense = sorted(float(value) for value in event.get("dense_keyframe_times", []))
                    if len(dense) < 3 or not any(value < center for value in dense) or not any(value > center for value in dense):
                        errors.append(f"Impact event lacks pre/impact/post frames: {shot_id}.{event_id}")
                    if any(min(abs(value - keyframe) for keyframe in times) > 0.015 for value in dense):
                        errors.append(f"Impact dense frame absent from keyframe_times: {shot_id}.{event_id}")
                camera = shot.get("camera", {})
                for key in CAMERA_REQUIRED:
                    if not str(camera.get(key, "")).strip():
                        errors.append(f"Missing camera {key}: {shot_id}")
                shot_prompt = str(shot.get("shot_prompt", ""))
                if not shot_prompt or BANNED.search(shot_prompt):
                    errors.append(f"Invalid self-contained shot_prompt: {shot_id}")
                for value in (camera.get("equipment_name"), camera.get("focal_length"), camera.get("aperture")):
                    if value and str(value) not in shot_prompt:
                        errors.append(f"Camera detail absent from shot_prompt: {shot_id} -> {value}")
                    if value and str(value) not in full_prompt:
                        errors.append(f"Camera detail absent from full_prompt: {shot_id} -> {value}")
            if abs(prior_shot_end - end) > 0.05:
                errors.append(f"Shot prompts do not cover segment: {segment_id}")
            if used_frame_refs != refs_for_segment:
                errors.append(f"Not every keyframe maps to a shot: {segment_id}")
            for chain_id, phases in interaction_chains.items():
                if len(phases) < 2:
                    errors.append(f"Interaction chain has fewer than two phases: {segment_id}.{chain_id}")
                if any(phases[index]["start"] > phases[index + 1]["start"] for index in range(len(phases) - 1)):
                    errors.append(f"Interaction chain phases out of time order: {segment_id}.{chain_id}")
                if len({phase["kind"] for phase in phases}) != 1 or len({phase["objects"] for phase in phases}) != 1:
                    errors.append(f"Interaction chain changes kind or tracked objects: {segment_id}.{chain_id}")
                for previous, current in zip(phases, phases[1:]):
                    if canonical_state(previous["state_out"]) != canonical_state(current["state_in"]):
                        errors.append(f"Interaction chain state discontinuity: {segment_id}.{chain_id}")
                if phases and phases[0]["kind"] == "ownership_transfer":
                    phase_names = {phase["phase"] for phase in phases}
                    if len(phases) < 4 or any(not (phase_names & group) for group in OWNERSHIP_PHASE_GROUPS):
                        errors.append(f"Incomplete ownership-transfer chain: {segment_id}.{chain_id}")
                    causal_stages = [OWNERSHIP_PHASE_STAGE[phase["phase"]] for phase in phases]
                    if causal_stages != sorted(causal_stages) or causal_stages[0] > 1 or causal_stages[-1] != 4:
                        errors.append(f"Ownership-transfer phases out of causal order: {segment_id}.{chain_id}")
            first_visible_now = {
                entity
                for shot in shot_prompts
                for entity in shot.get("present_entities", [])
                if str(entity).startswith("CHAR") and entity not in seen_visible_characters
            }
            if first_visible_now != set(first_appearance_assets) or len(first_appearance_assets) != len(set(first_appearance_assets)):
                errors.append(f"First appearance events mismatch: {segment_id}")
            seen_visible_characters.update(first_visible_now)
            required_refs = {source_id for source_id, item in source_facts.items() if item.get("timeline_required") is True}
            if set(timeline_source_refs) != required_refs or len(timeline_source_refs) != len(set(timeline_source_refs)):
                errors.append(f"Timeline source coverage mismatch: {segment_id}")
            for event in timeline_events:
                refs = [str(ref) for ref in event.get("source_refs", [])]
                owners = {source_owners.get(ref) for ref in refs if ref in source_owners}
                if len(owners) != 1 or None in owners:
                    errors.append(f"Timeline event mixes or lacks source-shot ownership: {segment_id}")
                    continue
                owner_shot_id = next(iter(owners))
                owner_shot = shot_map.get(owner_shot_id, {})
                try:
                    event_start, event_end = float(event.get("start", -1)), float(event.get("end", -1))
                    owner_start = float(owner_shot.get("start", -1)) - start
                    owner_end = float(owner_shot.get("end", -1)) - start
                    if event_start < owner_start - 0.02 or event_end > owner_end + 0.02:
                        errors.append(f"Timeline event/source shot mismatch: {segment_id}.{owner_shot_id}")
                    for ref in refs:
                        source = source_facts.get(ref, {})
                        overlap = min(event_end, float(source.get("end", -1))) - max(event_start, float(source.get("start", -1)))
                        if overlap <= 0.001:
                            errors.append(f"Timeline event does not overlap source fact: {segment_id}.{ref}")
                except (TypeError, ValueError):
                    errors.append(f"Invalid timeline/source range: {segment_id}.{owner_shot_id}")
                if str(event.get("shot_id", "")) != owner_shot_id:
                    errors.append(f"Timeline event shot_id mismatch: {segment_id}.{owner_shot_id}")
                facts = "；".join(
                    str(source_facts.get(ref, {}).get("timeline_fact", "")).strip().rstrip("。；")
                    for ref in refs
                )
                camera = owner_shot.get("camera", {})
                camera_text = (
                    f"RECREATION_SPEC｜设备：{camera.get('equipment_name', '')}；镜头：{camera.get('lens_name', '')}；"
                    f"焦段：{camera.get('focal_length', '')}；光圈：{camera.get('aperture', '')}；"
                    f"机位与角度：{camera.get('camera_height_angle', '')}；构图：{camera.get('composition', '')}；"
                    f"运镜：{camera.get('movement', '')}；对焦与景深：{camera.get('focus_depth', '')}"
                )
                expected_text = f"{facts}；摄影：{camera_text}"
                if str(event.get("text", "")) != expected_text:
                    errors.append(f"Timeline fact changed after shot analysis: {segment_id}")
                    break
        if previous_end is not None and abs(previous_end - source_duration) > 0.05:
            errors.append("Story segments do not cover source end")
        if any(ref not in expected_refs for ref in asset_frame_refs):
            errors.append("Asset library references unknown storyboard frames")

    html_path = storyboard / "图文分镜故事板-完整制作版.html"
    overview_path = storyboard / "图文分镜故事板-总览图.png"
    frame_root = storyboard / "storyboard-images"
    html_text = html_path.read_text(encoding="utf-8") if html_path.is_file() else ""
    if not html_path.is_file():
        errors.append("Missing storyboard HTML")
    if not overview_path.is_file():
        errors.append("Missing storyboard overview PNG")
    for label in ("人物资产表", "主要道具资产表", "主要场景资产表", "逐镜分镜故事板", "常见失败修复提示词"):
        if html_text and label not in html_text:
            errors.append(f"Storyboard missing section: {label}")
    if html_text and "Seedance 2.5 整段完整提示词（可直接复制）" not in html_text:
        errors.append("Storyboard missing user-facing full segment prompt")
    if html_text and "Seedance 2.5 自包含镜头提示词" in html_text:
        errors.append("Storyboard still exposes redundant shot prompts")
    for value in asset_ids | referenced_shots:
        if html_text and value not in html_text:
            errors.append(f"Storyboard missing mapped item: {value}")
    repairs = data.get("repair_prompts", {}) if isinstance(data, dict) else {}
    if html_text:
        if repairs:
            for name, prompt in repairs.items():
                if str(name) not in html_text or str(prompt) not in html_text:
                    errors.append(f"Storyboard missing repair prompt: {name}")
        elif "本片无需额外专项修复提示词" not in html_text:
            errors.append("Storyboard missing empty repair-prompt statement")
    if not (frame_root / "clean").is_dir() or not (frame_root / "annotated").is_dir():
        errors.append("Missing clean/annotated storyboard image directories")
    else:
        for ref in expected_refs:
            for folder in ("clean", "annotated"):
                if not (frame_root / folder / f"{ref}.png").is_file():
                    errors.append(f"Missing storyboard frame: {folder}/{ref}.png")

    if args.manifest and args.manifest.is_file():
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        manifest_ids = {str(value.get("segment_id")) for value in manifest.get("segments", [])}
        if manifest_ids != segment_ids:
            errors.append("Manifest/prompt segment mismatch")

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Validation passed: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
