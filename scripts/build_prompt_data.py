#!/usr/bin/env python3
"""Build self-contained Seedance prompt data with evidence-locked timelines."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
import re
import sys
from pathlib import Path


BANNED = re.compile(
    r"@(?:视频|影片|图片|圖像)(?:\s*\d+)?|参考映射|参考(?:视频|影片|原片|素材)|源视频|"
    r"(?:依照|按照|根据)原片|(?:^|[\s；。])(?:入口|出口)(?:状态)?[：:]|片段(?:入口|出口)|"
    r"(?:入口|出口)状态|承接(?:上一段|前一段)|延续(?:上一段|前一段)|"
    r"(?:上一段|下一段|前一段|后一段)(?:生成|视频|画面|内容|出口|入口)|"
    r"忠实复刻上一段|再次上传|reference\s+video|previous\s+segment|next\s+segment",
    re.I,
)
MISSING_MARKER = re.compile(r"\bNEEDS_INPUT\b", re.I)
EVIDENCE = {"OBSERVED", "MEASURED", "INFERRED", "UNKNOWN", "USER_PROVIDED"}
ASSET_GROUPS = (("characters", "人物", "CHAR"), ("props", "主要道具", "PROP"), ("locations", "主要场景", "LOC"))
ASSET_REQUIRED = ("asset_id", "name", "frame_refs", "description_prompt", "narrative_function", "continuity_lock", "evidence_status")
SEGMENT_REQUIRED = ("segment_id", "title", "start", "end", "duration", "shot_ids", "keyframe_times", "assets_used", "summary", "segment_consistency", "avoid", "shot_prompts", "timeline_events", "timeline_continuity")
SHOT_REQUIRED = ("shot_id", "start", "end", "duration", "frame_refs", "present_entities", "scene", "action_beats", "first_appearance_events", "layer_events", "impact_events", "camera", "lighting_color", "sound", "edit_instruction")
BEAT_REQUIRED = ("beat_id", "subject_asset_id", "subject", "actor_type", "object_asset_ids", "start", "end", "action", "object_or_target", "spatial_relation", "motion_rhythm", "physical_feedback", "timeline_fact", "timeline_required", "evidence_status")
PERFORMANCE_REQUIRED = ("emotion_intent", "visible_expression", "gaze_target", "preparation", "execution", "follow_through", "settle")
LAYER_REQUIRED = ("event_id", "layer_type", "start", "end", "content", "appearance", "placement_depth", "timeline_fact", "timeline_required", "evidence_status")
APPEARANCE_REQUIRED = (
    "event_id", "asset_id", "appearance_type", "start", "end", "prior_visibility", "source_space",
    "reveal_trigger", "entry_direction", "frame_region", "first_visible_part", "initial_pose_state",
    "emergence_motion", "first_visible_action", "completion_state", "observer_reaction", "evidence_frame_refs",
    "timeline_fact", "timeline_required", "evidence_status",
)
IMPACT_REQUIRED = ("event_id", "event_type", "start", "end", "source_time", "source_asset_id", "target_asset_id", "audio_cue", "visible_cause", "visible_effect", "causal_verdict", "dense_keyframe_times", "timeline_fact", "timeline_required", "evidence_status")
CAMERA_REQUIRED = ("equipment_name", "lens_name", "focal_length", "aperture", "camera_height_angle", "composition", "movement", "focus_depth")
VISUAL_MASTER_REQUIRED = ("core_style", "visual_tone", "color_system", "tonal_structure")
TIMELINE_EVENT_REQUIRED = ("start", "end", "source_refs")
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


def require_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SystemExit(f"Empty {label}")
    return text


def validate_generation_text(value: object, label: str) -> str:
    text = require_text(value, label)
    if MISSING_MARKER.search(text):
        raise SystemExit(f"Unresolved missing-field marker in {label}")
    match = BANNED.search(text)
    if match:
        raise SystemExit(f"Reference-dependent wording in {label}: {match.group(0)}")
    return text


def validate_timeline_text(value: object, label: str) -> str:
    text = validate_generation_text(value, label)
    match = INTERNAL_FIELD_LABELS.search(text)
    if match:
        raise SystemExit(f"Internal field label exposed in {label}: {match.group(0).strip()}")
    match = PRODUCTION_META.search(text)
    if match:
        raise SystemExit(f"Non-visual production wording in {label}: {match.group(0)}")
    return text


def frame_names(segment_id: str, count: int) -> set[str]:
    return {f"{segment_id}-node-{index:02d}" for index in range(1, count + 1)}


def action_sentence(beat: dict) -> str:
    performance = beat.get("performance_chain")
    visible_chain = ""
    if performance:
        visible_chain = (
            f"可见表演链：情绪意图{performance['emotion_intent']}，表情{performance['visible_expression']}，"
            f"视线指向{performance['gaze_target']}；预备{performance['preparation']}，执行{performance['execution']}，"
            f"延续{performance['follow_through']}，收势{performance['settle']}；"
        )
    return (
        f"{beat['subject']}在{beat['spatial_relation']}，以{beat['motion_rhythm']}的节奏{beat['action']}，"
        f"作用于{beat['object_or_target']}；{visible_chain}可见物理反馈为{beat['physical_feedback']}。"
    )


def layer_sentence(event: dict) -> str:
    labels = {
        "diegetic_display": "画内面屏",
        "editorial_title": "后期标题",
        "environment_vfx": "环境VFX",
        "ui_overlay": "UI叠层",
        "transition_vfx": "转场VFX",
    }
    return f"{labels[event['layer_type']]}：{event['content']}；外观与变化：{event['appearance']}；位置与深度：{event['placement_depth']}。"


def appearance_sentence(event: dict) -> str:
    return (
        f"首次登场：{event['asset_id']}；此前可见状态：{event['prior_visibility']}；出现触发：{event['reveal_trigger']}；"
        f"来源空间：{event['source_space']}；从{event['entry_direction']}进入{event['frame_region']}，"
        f"最先露出{event['first_visible_part']}，初始姿态为{event['initial_pose_state']}；"
        f"揭示动作：{event['emergence_motion']}；第一可见动作：{event['first_visible_action']}；"
        f"完成状态：{event['completion_state']}；其他角色反应：{event['observer_reaction']}。"
    )


def impact_sentence(event: dict) -> str:
    return (
        f"短促冲击事件：{event['event_type']}；声音线索：{event['audio_cue']}；"
        f"可见原因：{event['visible_cause']}；可见结果：{event['visible_effect']}；因果结论：{event['causal_verdict']}。"
    )


def camera_sentence(camera: dict) -> str:
    return (
        f"RECREATION_SPEC｜设备：{camera['equipment_name']}；镜头：{camera['lens_name']}；"
        f"焦段：{camera['focal_length']}；光圈：{camera['aperture']}；"
        f"机位与角度：{camera['camera_height_angle']}；构图：{camera['composition']}；"
        f"运镜：{camera['movement']}；对焦与景深：{camera['focus_depth']}。"
    )


def relative_window(segment: dict, shot: dict) -> str:
    segment_start = float(segment["start"])
    return f"{float(shot['start']) - segment_start:.2f}–{float(shot['end']) - segment_start:.2f}秒"


def timeline_event_sentence(event: dict) -> str:
    text = str(event["text"]).strip()
    if text[-1] not in "。！？":
        text += "。"
    return f"{float(event['start']):.2f}–{float(event['end']):.2f}秒：{text}"


def join_timeline_facts(facts: list[str]) -> str:
    """Join locked facts without producing awkward terminal-punctuation pairs."""
    return "；".join(str(fact).strip().rstrip("。；") for fact in facts)


def canonical_state(value: object) -> str:
    return re.sub(r"[\s。；;]+", "", str(value or "")).casefold()


def scoped_lines(segment: dict, label: str, values: list[tuple[dict, str]]) -> list[str]:
    unique = []
    seen = set()
    for shot, value in values:
        normalized = re.sub(r"\s+", "", value)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append((shot, value))
    if len(unique) == 1:
        return [f"{label}：{unique[0][1]}"]
    return [f"{label}（{relative_window(segment, shot)}）：{value}" for shot, value in unique]


def normalized_clauses(text: str) -> list[tuple[str, str]]:
    clauses = []
    for raw in re.split(r"[。！？；\n]+", text):
        display = raw.strip(" ：:\t")
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", display, flags=re.UNICODE).casefold()
        camera_prefixes = ("摄影：", "RECREATION_SPEC", "设备：", "镜头：", "焦段：", "光圈：", "机位与角度：", "构图：", "运镜：", "对焦与景深：")
        if len(normalized) >= 18 and not display.startswith("【") and not display.startswith(camera_prefixes):
            clauses.append((display, normalized))
    return clauses


def validate_prompt_structure(text: str, label: str) -> str:
    positions = [text.find(heading) for heading in PROMPT_HEADINGS]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise SystemExit(f"Invalid prompt section order in {label}")
    return text


def validate_prompt_redundancy(text: str, label: str) -> str:
    clauses = normalized_clauses(text)
    for index, (left_display, left) in enumerate(clauses):
        for right_display, right in clauses[index + 1 :]:
            length_ratio = min(len(left), len(right)) / max(len(left), len(right))
            if left == right or (length_ratio >= 0.88 and SequenceMatcher(None, left, right).ratio() >= 0.96):
                raise SystemExit(
                    f"Repeated or near-duplicate wording in {label}: {left_display!r} / {right_display!r}"
                )
    return text


def build_shot_prompt(shot: dict) -> str:
    camera = shot["camera"]
    actions = " ".join(action_sentence(beat) for beat in shot["action_beats"])
    appearances = " ".join(appearance_sentence(event) for event in shot["first_appearance_events"])
    layers = " ".join(layer_sentence(event) for event in shot["layer_events"])
    impacts = " ".join(impact_sentence(event) for event in shot["impact_events"])
    return (
        f"生成 {float(shot['duration']):.2f} 秒镜头。场景：{shot['scene']} "
        f"动作关系：{actions} "
        f"{appearances} "
        f"摄影实现方案：{camera_sentence(camera)}"
        f"光影与色彩：{shot['lighting_color']} 分层文字与视效：{layers} {impacts} "
        f"声音：{shot['sound']} 剪辑指令：{shot['edit_instruction']}"
    )


def build_full_prompt(segment: dict, asset_map: dict[str, dict], visual_master: dict) -> str:
    asset_groups: dict[str, list[str]] = {"CHAR": [], "PROP": [], "LOC": []}
    for asset_id in segment["assets_used"]:
        asset = asset_map[asset_id]
        prefix = next(value for value in asset_groups if asset_id.startswith(value))
        asset_groups[prefix].append(f"{asset['name']}：{asset['description_prompt']}")

    basic_parts = []
    for prefix, label in (("CHAR", "人物角色"), ("PROP", "道具与车辆"), ("LOC", "场景环境")):
        if asset_groups[prefix]:
            basic_parts.append(f"{label}：\n" + "\n".join(asset_groups[prefix]))
    basic_parts.append(f"连续性要求：\n{segment['segment_consistency']}")
    basic_parts.append(f"禁止项：\n{segment['avoid']}")

    lighting_values = [(shot, shot["lighting_color"]) for shot in segment["shot_prompts"]]
    sound_values = [(shot, shot["sound"]) for shot in segment["shot_prompts"]]
    atmosphere_parts = [
        "全片视觉母版：",
        f"核心风格：{visual_master['core_style']}",
        f"视觉基调：{visual_master['visual_tone']}",
        f"色彩体系：{visual_master['color_system']}",
        f"影调结构：{visual_master['tonal_structure']}",
    ]
    atmosphere_parts.extend(scoped_lines(segment, "本段光影与色彩", lighting_values))
    atmosphere_parts.extend(scoped_lines(segment, "声音设计", sound_values))

    timeline_parts = [timeline_event_sentence(event) for event in segment["timeline_events"]]
    timeline_parts.append(f"镜头连续性：{segment['timeline_continuity']}")
    aspect = require_text(segment.get("aspect_ratio") or "保持分析所得画幅", f"{segment['segment_id']}.aspect_ratio")
    return "\n\n".join(
        (
            "【生成任务】\n"
            f"生成一个{float(segment['duration']):.2f}秒、{aspect}的完整剧情片段。\n"
            f"剧情目标：{segment['summary']}",
            "【基础设定】\n" + "\n\n".join(basic_parts),
            "【氛围质感】\n" + "\n".join(atmosphere_parts),
            "【时间轴】\n" + "\n\n".join(timeline_parts),
        )
    )


def write_markdown(data: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    visual_master = data["visual_master"]
    global_parts = [
        "# 全局一致性提示词\n",
        data["global_consistency"],
        "\n## 全片视觉母版\n",
        f"- 核心风格：{visual_master['core_style']}",
        f"- 视觉基调：{visual_master['visual_tone']}",
        f"- 色彩体系：{visual_master['color_system']}",
        f"- 影调结构：{visual_master['tonal_structure']}",
        "\n## 视频资产提示词库\n",
    ]
    for group, label, _ in ASSET_GROUPS:
        global_parts.append(f"### {label}\n")
        items = data["asset_library"][group]
        if not items:
            global_parts.append("未识别到可确认资产。\n")
            continue
        for asset in items:
            global_parts.extend([
                f"#### {asset['asset_id']}｜{asset['name']}\n",
                f"- 详细生成提示词：{asset['description_prompt']}",
                f"- 叙事功能：{asset['narrative_function']}",
                f"- 连续性锁定：{asset['continuity_lock']}",
                f"- 证据等级：{asset['evidence_status']}\n",
            ])
    (output_dir / "全局一致性提示词.md").write_text("\n".join(global_parts), encoding="utf-8")

    parts = ["# 逐段剧情提示词\n", "> 下列提示词均可独立复制到新的生成任务，无需再次提交参考视频。\n"]
    for segment in data["segments"]:
        parts.extend([
            f"## {segment['segment_id']}｜{segment['title']}｜分析时间码 {float(segment['start']):.2f}s–{float(segment['end']):.2f}s｜生成时长 {float(segment['duration']):.2f}s\n",
            str(segment["full_prompt"]).strip() + "\n",
        ])
    (output_dir / "逐段剧情提示词.md").write_text("\n".join(parts), encoding="utf-8")

    repair_parts = ["# 修复提示词\n", "> 每条修复提示词也必须自包含，不依赖参考视频或前次对话。\n"]
    for name, prompt in data.get("repair_prompts", {}).items():
        repair_parts.extend([f"## {name}\n", str(prompt).strip() + "\n"])
    (output_dir / "修复提示词.md").write_text("\n".join(repair_parts), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Draft prompt JSON")
    parser.add_argument("output", type=Path, help="Normalized prompt-data.json")
    parser.add_argument("--emit-markdown", action="store_true", help="Also emit legacy prompt Markdown files for internal compatibility")
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    data["schema_version"] = "4.0"
    data.setdefault("project_title", "视频复刻项目")
    data.setdefault("repair_prompts", {})
    data["global_consistency"] = validate_generation_text(data.get("global_consistency"), "global_consistency")
    visual_master = data.get("visual_master")
    if not isinstance(visual_master, dict):
        raise SystemExit("visual_master must be an object")
    missing = [key for key in VISUAL_MASTER_REQUIRED if key not in visual_master]
    if missing:
        raise SystemExit(f"visual_master missing: {', '.join(missing)}")
    for key in VISUAL_MASTER_REQUIRED:
        visual_master[key] = validate_generation_text(visual_master[key], f"visual_master.{key}")
    source_duration = float(data.get("source_duration") or 0)
    if source_duration <= 0:
        raise SystemExit("source_duration must be greater than zero")

    library = data.get("asset_library")
    if not isinstance(library, dict):
        raise SystemExit("asset_library must be an object")
    asset_map: dict[str, dict] = {}
    pending_asset_refs: list[tuple[str, str]] = []
    for group, _, prefix in ASSET_GROUPS:
        items = library.get(group)
        if not isinstance(items, list):
            raise SystemExit(f"asset_library.{group} must be an array")
        for asset in items:
            missing = [key for key in ASSET_REQUIRED if key not in asset]
            if missing:
                raise SystemExit(f"Asset missing fields: {', '.join(missing)}")
            asset_id = str(asset["asset_id"])
            if not re.fullmatch(prefix + r"\d{3,}", asset_id) or asset_id in asset_map:
                raise SystemExit(f"Invalid or duplicate asset_id: {asset_id}")
            asset["name"] = require_text(asset["name"], f"{asset_id}.name")
            asset["description_prompt"] = validate_generation_text(asset["description_prompt"], f"{asset_id}.description_prompt")
            asset["narrative_function"] = require_text(asset["narrative_function"], f"{asset_id}.narrative_function")
            asset["continuity_lock"] = validate_generation_text(asset["continuity_lock"], f"{asset_id}.continuity_lock")
            if asset["evidence_status"] not in EVIDENCE:
                raise SystemExit(f"Invalid evidence_status: {asset_id}")
            refs = asset["frame_refs"]
            if not isinstance(refs, list) or not refs:
                raise SystemExit(f"Missing asset frame_refs: {asset_id}")
            pending_asset_refs.extend((asset_id, str(ref)) for ref in refs)
            asset_map[asset_id] = asset
    if not asset_map:
        raise SystemExit("asset_library must contain at least one observed asset")

    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        raise SystemExit("segments must be a non-empty array")
    segments = sorted(segments, key=lambda item: float(item.get("start", -1)))
    previous_end = None
    seen_segments: set[str] = set()
    all_frame_refs: set[str] = set()
    seen_visible_characters: set[str] = set()
    for index, segment in enumerate(segments):
        missing = [key for key in SEGMENT_REQUIRED if key not in segment]
        if missing:
            raise SystemExit(f"{segment.get('segment_id', '<unknown>')} missing: {', '.join(missing)}")
        segment_id = str(segment["segment_id"])
        if not re.fullmatch(r"P\d{3,}", segment_id) or segment_id in seen_segments:
            raise SystemExit(f"Invalid or duplicate segment_id: {segment_id}")
        seen_segments.add(segment_id)
        start, end, duration = map(float, (segment["start"], segment["end"], segment["duration"]))
        if end <= start or abs(duration - (end - start)) > 0.02:
            raise SystemExit(f"Duration does not match time range: {segment_id}")
        if index == 0 and abs(start) > 0.05:
            raise SystemExit(f"First segment must start at 0: {segment_id}")
        if previous_end is not None and abs(start - previous_end) > 0.05:
            raise SystemExit(f"Timeline gap/overlap before {segment_id}: {start - previous_end:.3f}s")

        shot_ids = [str(x) for x in segment["shot_ids"]]
        if not shot_ids or len(shot_ids) != len(set(shot_ids)) or any(not re.fullmatch(r"SH\d{3,}", value) for value in shot_ids):
            raise SystemExit(f"Invalid shot_ids: {segment_id}")
        times = [float(value) for value in segment["keyframe_times"]]
        if len(times) < max(2, len(shot_ids)) or times != sorted(times) or any(value < start - 0.01 or value > end + 0.01 for value in times):
            raise SystemExit(f"Invalid keyframe_times: {segment_id}")
        allowed_refs = frame_names(segment_id, len(times))
        all_frame_refs.update(allowed_refs)

        assets_used = [str(value) for value in segment["assets_used"]]
        if not assets_used or len(assets_used) != len(set(assets_used)) or any(value not in asset_map for value in assets_used):
            raise SystemExit(f"Invalid assets_used: {segment_id}")
        segment["summary"] = require_text(segment["summary"], f"{segment_id}.summary")
        segment["segment_consistency"] = validate_generation_text(segment["segment_consistency"], f"{segment_id}.segment_consistency")
        segment["avoid"] = validate_generation_text(segment["avoid"], f"{segment_id}.avoid")

        timeline_events = segment["timeline_events"]
        if not isinstance(timeline_events, list) or not timeline_events:
            raise SystemExit(f"Missing timeline_events: {segment_id}")
        segment["timeline_continuity"] = validate_timeline_text(segment["timeline_continuity"], f"{segment_id}.timeline_continuity")

        shot_prompts = segment["shot_prompts"]
        if not isinstance(shot_prompts, list) or len(shot_prompts) != len(shot_ids):
            raise SystemExit(f"shot_prompts must match shot_ids: {segment_id}")
        seen_shots: list[str] = []
        used_refs: set[str] = set()
        prior_shot_end = start
        source_facts: dict[str, dict] = {}
        source_owners: dict[str, str] = {}
        shot_map: dict[str, dict] = {}
        interaction_chains: dict[str, list[dict]] = {}
        first_appearances_in_segment: set[str] = set()

        def register_source(item: dict, id_key: str, label: str, owner_shot_id: str, owner_start: float, owner_end: float) -> None:
            source_id = str(item.get(id_key, ""))
            if not re.fullmatch(r"[BLAI]\d{3,}", source_id) or source_id in source_facts:
                raise SystemExit(f"Invalid or duplicate source id: {segment_id}.{label}.{source_id}")
            item["timeline_fact"] = validate_timeline_text(item.get("timeline_fact"), f"{segment_id}.{source_id}.timeline_fact")
            if not isinstance(item.get("timeline_required"), bool):
                raise SystemExit(f"timeline_required must be boolean: {segment_id}.{source_id}")
            if item.get("evidence_status") not in EVIDENCE:
                raise SystemExit(f"Invalid evidence_status: {segment_id}.{source_id}")
            item_start, item_end = map(float, (item.get("start", -1), item.get("end", -1)))
            if item_start < 0 or item_end <= item_start or item_end > duration + 0.05:
                raise SystemExit(f"Invalid source event range: {segment_id}.{source_id}")
            if item_start < owner_start - 0.02 or item_end > owner_end + 0.02:
                raise SystemExit(
                    f"Cross-shot source range: {segment_id}.{source_id} belongs to {owner_shot_id} "
                    f"({owner_start:.2f}-{owner_end:.2f}) but uses {item_start:.2f}-{item_end:.2f}"
                )
            source_facts[source_id] = item
            source_owners[source_id] = owner_shot_id

        for shot in shot_prompts:
            missing = [key for key in SHOT_REQUIRED if key not in shot]
            if missing:
                raise SystemExit(f"{segment_id} shot missing: {', '.join(missing)}")
            shot_id = str(shot["shot_id"])
            shot_map[shot_id] = shot
            seen_shots.append(shot_id)
            shot_start, shot_end, shot_duration = map(float, (shot["start"], shot["end"], shot["duration"]))
            if shot_end <= shot_start or abs(shot_duration - (shot_end - shot_start)) > 0.02:
                raise SystemExit(f"Invalid shot duration: {shot_id}")
            if abs(shot_start - prior_shot_end) > 0.05 or shot_end > end + 0.05:
                raise SystemExit(f"Shot timeline mismatch: {shot_id}")
            prior_shot_end = shot_end
            shot_rel_start = shot_start - start
            shot_rel_end = shot_end - start
            refs = [str(value) for value in shot["frame_refs"]]
            if not refs or any(value not in allowed_refs for value in refs):
                raise SystemExit(f"Invalid frame_refs: {shot_id}")
            used_refs.update(refs)
            present_entities = [str(value) for value in shot["present_entities"]]
            if not present_entities or len(present_entities) != len(set(present_entities)):
                raise SystemExit(f"Invalid present_entities: {shot_id}")
            if any(value not in asset_map for value in present_entities):
                raise SystemExit(f"Unknown present entity: {shot_id}")
            shot["scene"] = validate_generation_text(shot["scene"], f"{shot_id}.scene")
            beats = shot["action_beats"]
            if not isinstance(beats, list) or not beats:
                raise SystemExit(f"Missing action_beats: {shot_id}")
            for beat in beats:
                missing = [key for key in BEAT_REQUIRED if key not in beat]
                if missing:
                    raise SystemExit(f"{shot_id} action beat missing: {', '.join(missing)}")
                for key in ("subject", "action", "object_or_target", "spatial_relation", "motion_rhythm", "physical_feedback"):
                    beat[key] = validate_generation_text(beat[key], f"{shot_id}.action_beats.{key}")
                if beat["evidence_status"] not in EVIDENCE:
                    raise SystemExit(f"Invalid action evidence_status: {shot_id}.{beat['beat_id']}")
                subject_asset_id = str(beat["subject_asset_id"])
                actor_type = str(beat["actor_type"])
                if actor_type in {"character", "creature"} and not subject_asset_id.startswith("CHAR"):
                    raise SystemExit(f"Character performance must bind a CHAR asset: {shot_id}.{beat['beat_id']}")
                if subject_asset_id not in {"CAMERA", "GRAPHICS", "ENVIRONMENT"} and subject_asset_id not in present_entities:
                    raise SystemExit(f"Cross-shot subject pollution: {shot_id}.{beat['beat_id']} -> {subject_asset_id} is not visible")
                object_ids = [str(value) for value in beat["object_asset_ids"]]
                if any(value not in present_entities for value in object_ids):
                    raise SystemExit(f"Cross-shot object pollution: {shot_id}.{beat['beat_id']}")
                performance = beat.get("performance_chain")
                if actor_type in {"character", "creature"}:
                    if not isinstance(performance, dict):
                        raise SystemExit(f"Visible performance chain missing: {shot_id}.{beat['beat_id']}")
                    missing_performance = [key for key in PERFORMANCE_REQUIRED if key not in performance]
                    if missing_performance:
                        raise SystemExit(f"Performance chain missing: {shot_id}.{beat['beat_id']} -> {', '.join(missing_performance)}")
                    for key in PERFORMANCE_REQUIRED:
                        performance[key] = validate_generation_text(performance[key], f"{shot_id}.{beat['beat_id']}.performance_chain.{key}")
                elif performance is not None:
                    raise SystemExit(f"Performance chain assigned to non-character: {shot_id}.{beat['beat_id']}")
                beat_start, beat_end = map(float, (beat["start"], beat["end"]))
                if beat_start < 0 or beat_end <= beat_start or beat_end > duration + 0.05:
                    raise SystemExit(f"Invalid action beat range: {shot_id}.{beat['beat_id']}")
                chain_id = beat.get("interaction_chain_id")
                chain_fields = (
                    beat.get("interaction_kind"), beat.get("interaction_object_ids"),
                    beat.get("interaction_phase"), beat.get("state_in"), beat.get("state_out"),
                )
                if chain_id is not None or any(value is not None for value in chain_fields):
                    interaction_kind = str(beat.get("interaction_kind") or "")
                    interaction_objects = [str(value) for value in (beat.get("interaction_object_ids") or [])]
                    interaction_phase = str(beat.get("interaction_phase") or "")
                    if (
                        not re.fullmatch(r"X\d{3,}", str(chain_id or ""))
                        or interaction_kind not in INTERACTION_KINDS
                        or not interaction_objects
                        or len(interaction_objects) != len(set(interaction_objects))
                        or interaction_phase not in INTERACTION_PHASES
                        or not str(beat.get("state_in") or "").strip()
                        or not str(beat.get("state_out") or "").strip()
                    ):
                        raise SystemExit(f"Incomplete interaction chain fields: {shot_id}.{beat['beat_id']}")
                    bound_assets = {subject_asset_id, *object_ids}
                    if any(value not in bound_assets for value in interaction_objects):
                        raise SystemExit(f"Interaction object is not bound to action beat: {shot_id}.{beat['beat_id']}")
                    for key in ("state_in", "state_out"):
                        beat[key] = validate_generation_text(beat[key], f"{shot_id}.{beat['beat_id']}.{key}")
                    if beat.get("timeline_required") is not True:
                        raise SystemExit(f"Interaction chain phase must enter timeline: {shot_id}.{beat['beat_id']}")
                    interaction_chains.setdefault(str(chain_id), []).append({
                        "start": beat_start,
                        "end": beat_end,
                        "shot_id": shot_id,
                        "phase": interaction_phase,
                        "kind": interaction_kind,
                        "objects": tuple(interaction_objects),
                        "state_in": str(beat["state_in"]),
                        "state_out": str(beat["state_out"]),
                    })
                register_source(beat, "beat_id", "action_beats", shot_id, shot_rel_start, shot_rel_end)

            appearances = shot["first_appearance_events"]
            if not isinstance(appearances, list):
                raise SystemExit(f"first_appearance_events must be an array: {shot_id}")
            for event in appearances:
                missing = [key for key in APPEARANCE_REQUIRED if key not in event]
                if missing:
                    raise SystemExit(f"{shot_id} appearance event missing: {', '.join(missing)}")
                asset_id = str(event["asset_id"])
                if asset_id not in present_entities or not asset_id.startswith("CHAR"):
                    raise SystemExit(f"Invalid first appearance asset: {shot_id}.{asset_id}")
                for key in (
                    "prior_visibility", "source_space", "reveal_trigger", "entry_direction", "frame_region",
                    "first_visible_part", "initial_pose_state", "emergence_motion", "first_visible_action",
                    "completion_state", "observer_reaction",
                ):
                    event[key] = validate_generation_text(event[key], f"{shot_id}.{event['event_id']}.{key}")
                evidence_refs = [str(value) for value in event.get("evidence_frame_refs", [])]
                if len(evidence_refs) < 2 or len(evidence_refs) != len(set(evidence_refs)) or any(value not in refs for value in evidence_refs):
                    raise SystemExit(f"First appearance requires at least two owner-shot evidence frames: {shot_id}.{event['event_id']}")
                if asset_id in first_appearances_in_segment:
                    raise SystemExit(f"Duplicate first appearance for asset: {segment_id}.{asset_id}")
                first_appearances_in_segment.add(asset_id)
                register_source(event, "event_id", "first_appearance_events", shot_id, shot_rel_start, shot_rel_end)

            layers = shot["layer_events"]
            if not isinstance(layers, list):
                raise SystemExit(f"layer_events must be an array: {shot_id}")
            for event in layers:
                missing = [key for key in LAYER_REQUIRED if key not in event]
                if missing:
                    raise SystemExit(f"{shot_id} layer event missing: {', '.join(missing)}")
                for key in ("content", "appearance", "placement_depth"):
                    event[key] = validate_generation_text(event[key], f"{shot_id}.{event['event_id']}.{key}")
                if event.get("layer_type") not in {"diegetic_display", "editorial_title", "environment_vfx", "ui_overlay", "transition_vfx"}:
                    raise SystemExit(f"Invalid layer_type: {shot_id}.{event['event_id']}")
                register_source(event, "event_id", "layer_events", shot_id, shot_rel_start, shot_rel_end)

            impacts = shot["impact_events"]
            if not isinstance(impacts, list):
                raise SystemExit(f"impact_events must be an array: {shot_id}")
            for event in impacts:
                missing = [key for key in IMPACT_REQUIRED if key not in event]
                if missing:
                    raise SystemExit(f"{shot_id} impact event missing: {', '.join(missing)}")
                if event["causal_verdict"] == "REJECTED" and event["timeline_required"]:
                    raise SystemExit(f"Rejected impact cannot enter timeline: {shot_id}.{event['event_id']}")
                for key in ("source_asset_id", "target_asset_id", "audio_cue", "visible_cause", "visible_effect"):
                    event[key] = validate_generation_text(event[key], f"{shot_id}.{event['event_id']}.{key}")
                source_time = float(event["source_time"])
                dense = sorted({float(value) for value in event["dense_keyframe_times"]})
                if len(dense) < 3 or not any(value < source_time for value in dense) or not any(value > source_time for value in dense):
                    raise SystemExit(f"Impact dense frames must bracket the event: {shot_id}.{event['event_id']}")
                if any(min(abs(value - keyframe) for keyframe in times) > 0.015 for value in dense):
                    raise SystemExit(f"Impact dense frame missing from segment keyframes: {shot_id}.{event['event_id']}")
                register_source(event, "event_id", "impact_events", shot_id, shot_rel_start, shot_rel_end)
            camera = shot["camera"]
            if not isinstance(camera, dict):
                raise SystemExit(f"Invalid camera: {shot_id}")
            missing = [key for key in CAMERA_REQUIRED if key not in camera]
            if missing:
                raise SystemExit(f"{shot_id} camera missing: {', '.join(missing)}")
            for key in CAMERA_REQUIRED:
                camera[key] = validate_generation_text(camera[key], f"{shot_id}.camera.{key}")
            for key in ("lighting_color", "sound", "edit_instruction"):
                shot[key] = validate_generation_text(shot[key], f"{shot_id}.{key}")
            shot["shot_prompt"] = validate_generation_text(build_shot_prompt(shot), f"{shot_id}.shot_prompt")
        if seen_shots != shot_ids:
            raise SystemExit(f"shot_prompts order/id mismatch: {segment_id}")
        if abs(prior_shot_end - end) > 0.05:
            raise SystemExit(f"Shot prompts do not cover segment end: {segment_id}")
        if used_refs != allowed_refs:
            raise SystemExit(f"Not every keyframe maps to a shot: {segment_id}")
        for chain_id, phases in interaction_chains.items():
            if len(phases) < 2:
                raise SystemExit(f"Interaction chain must contain at least two linked phases: {segment_id}.{chain_id}")
            if any(phases[index]["start"] > phases[index + 1]["start"] for index in range(len(phases) - 1)):
                raise SystemExit(f"Interaction chain phases out of time order: {segment_id}.{chain_id}")
            kinds = {phase["kind"] for phase in phases}
            objects = {phase["objects"] for phase in phases}
            if len(kinds) != 1 or len(objects) != 1:
                raise SystemExit(f"Interaction chain changes kind or tracked objects: {segment_id}.{chain_id}")
            for previous, current in zip(phases, phases[1:]):
                if canonical_state(previous["state_out"]) != canonical_state(current["state_in"]):
                    raise SystemExit(
                        f"Interaction chain state discontinuity: {segment_id}.{chain_id} -> "
                        f"{previous['state_out']!r} != {current['state_in']!r}"
                    )
            if phases[0]["kind"] == "ownership_transfer":
                phase_names = {phase["phase"] for phase in phases}
                if len(phases) < 4 or any(not (phase_names & group) for group in OWNERSHIP_PHASE_GROUPS):
                    raise SystemExit(
                        f"Ownership-transfer chain must include launch, capture/transfer, carry/return, "
                        f"and observer/result phases: {segment_id}.{chain_id}"
                    )
                causal_stages = [OWNERSHIP_PHASE_STAGE[phase["phase"]] for phase in phases]
                if causal_stages != sorted(causal_stages) or causal_stages[0] > 1 or causal_stages[-1] != 4:
                    raise SystemExit(f"Ownership-transfer phases out of causal order: {segment_id}.{chain_id}")

        first_visible_now = {
            entity
            for shot in shot_prompts
            for entity in shot["present_entities"]
            if entity.startswith("CHAR") and entity not in seen_visible_characters
        }
        if first_visible_now != first_appearances_in_segment:
            missing_events = sorted(first_visible_now - first_appearances_in_segment)
            extra_events = sorted(first_appearances_in_segment - first_visible_now)
            raise SystemExit(f"First appearance mismatch: {segment_id}; missing={missing_events}; extra={extra_events}")
        seen_visible_characters.update(first_visible_now)

        prior_event_start = -1.0
        max_event_end = 0.0
        used_source_refs: list[str] = []
        for event_index, event in enumerate(timeline_events):
            if not isinstance(event, dict):
                raise SystemExit(f"Invalid timeline event: {segment_id}[{event_index}]")
            missing = [key for key in TIMELINE_EVENT_REQUIRED if key not in event]
            if missing:
                raise SystemExit(f"{segment_id} timeline event missing: {', '.join(missing)}")
            event_start, event_end = map(float, (event["start"], event["end"]))
            if event_start < 0 or event_end <= event_start or event_end > duration + 0.05 or event_start < prior_event_start:
                raise SystemExit(f"Invalid timeline event range/order: {segment_id}[{event_index}]")
            refs = [str(value) for value in event["source_refs"]]
            if not refs or len(refs) != len(set(refs)) or any(value not in source_facts for value in refs):
                raise SystemExit(f"Invalid timeline source_refs: {segment_id}[{event_index}]")
            used_source_refs.extend(refs)
            owner_ids = {source_owners[value] for value in refs}
            if len(owner_ids) != 1:
                raise SystemExit(f"Timeline event mixes source facts from different shots: {segment_id}[{event_index}] -> {sorted(owner_ids)}")
            owner_shot_id = next(iter(owner_ids))
            owner_shot = shot_map[owner_shot_id]
            owner_rel_start = float(owner_shot["start"]) - start
            owner_rel_end = float(owner_shot["end"]) - start
            if event_start < owner_rel_start - 0.02 or event_end > owner_rel_end + 0.02:
                raise SystemExit(
                    f"Timeline event/source shot mismatch: {segment_id}[{event_index}] uses {owner_shot_id} "
                    f"({owner_rel_start:.2f}-{owner_rel_end:.2f}) at {event_start:.2f}-{event_end:.2f}"
                )
            for source_id in refs:
                source = source_facts[source_id]
                overlap = min(event_end, float(source["end"])) - max(event_start, float(source["start"]))
                if overlap <= 0.001:
                    raise SystemExit(
                        f"Timeline event does not overlap source fact: {segment_id}[{event_index}] -> {source_id}"
                    )
            event["shot_id"] = owner_shot_id
            facts = join_timeline_facts([source_facts[value]["timeline_fact"] for value in refs])
            camera_fact = camera_sentence(owner_shot["camera"]).rstrip("。")
            event["text"] = validate_timeline_text(
                f"{facts}；摄影：{camera_fact}",
                f"{segment_id}.timeline_events[{event_index}].text",
            )
            prior_event_start = event_start
            max_event_end = max(max_event_end, event_end)
        required_refs = {source_id for source_id, item in source_facts.items() if item["timeline_required"]}
        if set(used_source_refs) != required_refs or len(used_source_refs) != len(set(used_source_refs)):
            missing_refs = sorted(required_refs - set(used_source_refs))
            duplicate_refs = sorted({value for value in used_source_refs if used_source_refs.count(value) > 1})
            extra_refs = sorted(set(used_source_refs) - required_refs)
            raise SystemExit(f"Timeline source coverage failed: {segment_id}; missing={missing_refs}; duplicate={duplicate_refs}; extra={extra_refs}")
        if float(timeline_events[0]["start"]) > 0.05 or abs(max_event_end - duration) > 0.05:
            raise SystemExit(f"Timeline events do not cover segment bounds: {segment_id}")
        full_prompt = validate_generation_text(
            build_full_prompt(segment, asset_map, visual_master), f"{segment_id}.full_prompt"
        )
        validate_prompt_structure(full_prompt, f"{segment_id}.full_prompt")
        segment["full_prompt"] = validate_prompt_redundancy(full_prompt, f"{segment_id}.full_prompt")
        previous_end = end

    if abs(previous_end - source_duration) > 0.05:
        raise SystemExit(f"Segments do not cover source end: {previous_end:.3f}s != {source_duration:.3f}s")
    for asset_id, frame_ref in pending_asset_refs:
        if frame_ref not in all_frame_refs:
            raise SystemExit(f"Unknown asset frame_ref: {asset_id} -> {frame_ref}")
    for name, prompt in data["repair_prompts"].items():
        data["repair_prompts"][name] = validate_generation_text(prompt, f"repair_prompts.{name}")

    data["segments"] = segments
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.emit_markdown:
        write_markdown(data, args.output.parent)
    print(f"Wrote normalized prompt data for {len(segments)} story segments to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
