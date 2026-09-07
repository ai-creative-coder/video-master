from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_prompt_data.py"
VALIDATOR_SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_outputs.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("v3_validate_outputs", VALIDATOR_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def camera() -> dict:
    return {
        "equipment_name": "RECREATION_SPEC｜虚拟电影摄影机",
        "lens_name": "35mm电影定焦镜头",
        "focal_length": "35mm",
        "aperture": "T4",
        "camera_height_angle": "1.0米侧面平视",
        "composition": "主体居中偏左",
        "movement": "连续侧向跟拍",
        "focus_depth": "焦点锁定驾驶者，中等景深",
    }


def draft() -> dict:
    return {
        "project_title": "V3回归测试",
        "source_duration": 4.67,
        "global_consistency": "同一驾驶者、同一长桥和同一行驶方向。",
        "visual_master": {
            "core_style": "近未来载具广告与写实公路电影融合，工业材质可信。",
            "visual_tone": "冷静、精确、速度感强，道路透视建立秩序。",
            "color_system": "冷灰环境为主体，朱红载具作为高饱和强调色。",
            "tonal_structure": "中高对比，黑位不压死，阴天高光柔和滚降。",
        },
        "asset_library": {
            "characters": [{
                "asset_id": "CHAR001", "name": "驾驶者", "frame_refs": ["P001-node-01"],
                "description_prompt": "短黑发成年男性，穿深色短袖。", "narrative_function": "驾驶载具。",
                "continuity_lock": "固定脸、发型和服装。", "evidence_status": "OBSERVED",
            }],
            "props": [{
                "asset_id": "PROP001", "name": "摩托", "frame_refs": ["P001-node-03"],
                "description_prompt": "朱红全包围运动摩托。", "narrative_function": "承载驾驶动作。",
                "continuity_lock": "车轮持续接地。", "evidence_status": "OBSERVED",
            }],
            "locations": [{
                "asset_id": "LOC001", "name": "长桥", "frame_refs": ["P001-node-05"],
                "description_prompt": "阴天跨水多车道长桥，路面微湿。", "narrative_function": "提供行驶空间。",
                "continuity_lock": "天气和车道方向固定。", "evidence_status": "OBSERVED",
            }],
        },
        "repair_prompts": {},
        "segments": [{
            "segment_id": "P001", "title": "瞬态事件", "start": 0.0, "end": 4.67, "duration": 4.67,
            "shot_ids": ["SH001"], "keyframe_times": [0.0, 1.8, 2.0, 2.2, 4.66],
            "assets_used": ["CHAR001", "PROP001", "LOC001"], "aspect_ratio": "16:9横屏、30fps",
            "summary": "驾驶者在长桥上驾驶摩托，UI出现并发生一次可见冲击反馈。",
            "segment_consistency": "驾驶者身份、道路轴线和摩托接地点固定。",
            "avoid": "禁止换脸、车辆悬空和文字乱码。",
            "timeline_events": [
                {"start": 0.0, "end": 0.2, "source_refs": ["A001"], "text": "故意篡改，构建器必须覆盖"},
                {"start": 0.2, "end": 1.2, "source_refs": ["L001"]},
                {"start": 1.2, "end": 2.3, "source_refs": ["I001"]},
                {"start": 2.3, "end": 4.67, "source_refs": ["B001"]},
            ],
            "timeline_continuity": "保持连续侧向跟拍，事件前后道路方向和主体速度一致。",
            "shot_prompts": [{
                "shot_id": "SH001", "start": 0.0, "end": 4.67, "duration": 4.67,
                "frame_refs": ["P001-node-01", "P001-node-02", "P001-node-03", "P001-node-04", "P001-node-05"],
                "present_entities": ["CHAR001", "PROP001", "LOC001"],
                "scene": "阴天长桥，微湿路面沿远方延伸。",
                "action_beats": [{
                    "beat_id": "B001", "subject_asset_id": "CHAR001", "subject": "驾驶者", "actor_type": "character",
                    "object_asset_ids": ["PROP001", "LOC001"], "start": 0.0, "end": 4.67,
                    "action": "双手握把驱动摩托沿车道直线前进", "object_or_target": "摩托与前方车道",
                    "spatial_relation": "身体位于摩托座位，车轮位于两条车道线之间", "motion_rhythm": "稳定持续",
                    "physical_feedback": "车轮持续旋转接地，悬挂轻微响应路面",
                    "performance_chain": {
                        "emotion_intent": "专注控车", "visible_expression": "眉眼收紧且嘴部放松", "gaze_target": "前方车道",
                        "preparation": "身体前倾并握紧车把", "execution": "保持低重心直线行驶",
                        "follow_through": "肩臂随路面细微起伏", "settle": "姿态回到稳定前倾",
                    },
                    "timeline_fact": "驾驶者双手握把沿车道前进，视线锁定道路，车轮持续接地旋转。",
                    "timeline_required": True, "evidence_status": "OBSERVED",
                }],
                "first_appearance_events": [{
                    "event_id": "A001", "asset_id": "CHAR001", "appearance_type": "initial_presence", "start": 0.0, "end": 0.2,
                    "prior_visibility": "画面开始前不可见", "source_space": "画面外起始状态", "reveal_trigger": "首帧直接建立",
                    "entry_direction": "画面起始位置", "frame_region": "左中部", "first_visible_part": "完整头部与上身",
                    "initial_pose_state": "身体前倾坐在摩托上", "emergence_motion": "首帧直接显示完整坐姿",
                    "first_visible_action": "双手握住车把", "completion_state": "驾驶姿态完整建立",
                    "observer_reaction": "无其他可见人物", "evidence_frame_refs": ["P001-node-01", "P001-node-02"],
                    "timeline_fact": "画面开始即建立驾驶者位于左中部、前倾握把的初始状态。",
                    "timeline_required": True, "evidence_status": "OBSERVED",
                }],
                "layer_events": [{
                    "event_id": "L001", "layer_type": "ui_overlay", "start": 0.2, "end": 1.2,
                    "content": "白色圆角卡片与黄色按钮", "appearance": "卡片淡入，按钮短促增亮后复原",
                    "placement_depth": "固定在屏幕右侧安全区，不属于场景实体",
                    "timeline_fact": "白色圆角UI卡片在屏幕右侧出现，黄色按钮短促增亮后复原。",
                    "timeline_required": True, "evidence_status": "OBSERVED",
                }],
                "impact_events": [{
                    "event_id": "I001", "event_type": "other", "start": 1.8, "end": 2.2, "source_time": 2.0,
                    "source_asset_id": "PROP001", "target_asset_id": "PROP001", "audio_cue": "短促金属冲击声",
                    "visible_cause": "摩托前轮压过路面接缝", "visible_effect": "前悬挂快速压缩后回弹",
                    "causal_verdict": "CONFIRMED", "dense_keyframe_times": [1.8, 2.0, 2.2],
                    "timeline_fact": "摩托前轮压过接缝时响起短促冲击声，前悬挂立即压缩并回弹。",
                    "timeline_required": True, "evidence_status": "OBSERVED",
                }],
                "camera": camera(), "lighting_color": "阴天冷白漫射光，朱红摩托为视觉锚点。",
                "sound": "电子音乐与道路底床连续，冲击声位于2.00秒。", "edit_instruction": "保持连续侧向跟拍，无可见硬切。",
            }],
        }],
    }


def build(payload: dict, should_pass: bool) -> tuple[subprocess.CompletedProcess[str], dict | None]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = root / "draft.json"
        output = root / "pack" / "prompt-data.json"
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(source), str(output)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if should_pass:
            assert result.returncode == 0, result.stderr + result.stdout
            return result, json.loads(output.read_text(encoding="utf-8"))
        assert result.returncode != 0
        return result, None


def main() -> None:
    _, built = build(draft(), True)
    assert built is not None
    segment = built["segments"][0]
    assert built["schema_version"] == "4.0"
    assert segment["timeline_events"][0]["text"].startswith(segment["shot_prompts"][0]["first_appearance_events"][0]["timeline_fact"].rstrip("。"))
    assert segment["timeline_events"][0]["text"].endswith("对焦与景深：焦点锁定驾驶者，中等景深")
    assert "摄影方案" not in segment["full_prompt"].split("【氛围质感】", 1)[1].split("【时间轴】", 1)[0]
    assert segment["full_prompt"].count("摄影：RECREATION_SPEC") == len(segment["timeline_events"])
    validator = load_validator()
    assert validator.repeated_prompt_clause(segment["full_prompt"]) is None
    atmosphere = segment["full_prompt"].split("【氛围质感】", 1)[1].split("【时间轴】", 1)[0]
    assert validator.atmosphere_has_camera(atmosphere) is False
    assert validator.atmosphere_has_camera(atmosphere + " 摄影方案：RECREATION_SPEC｜设备：测试摄影机") is True
    assert "故意篡改" not in segment["full_prompt"]
    assert segment["full_prompt"].count("摩托前轮压过接缝时响起短促冲击声") == 1

    polluted = draft()
    polluted["segments"][0]["shot_prompts"][0]["action_beats"][0]["subject_asset_id"] = "CHAR999"
    result, _ = build(polluted, False)
    assert "pollution" in result.stderr + result.stdout

    omitted = draft()
    omitted["segments"][0]["timeline_events"] = omitted["segments"][0]["timeline_events"][:-1]
    omitted["segments"][0]["timeline_events"][-1]["end"] = 4.67
    result, _ = build(omitted, False)
    assert "coverage failed" in result.stderr + result.stdout

    no_appearance = draft()
    no_appearance["segments"][0]["shot_prompts"][0]["first_appearance_events"] = []
    no_appearance["segments"][0]["timeline_events"] = [event for event in no_appearance["segments"][0]["timeline_events"] if "A001" not in event["source_refs"]]
    no_appearance["segments"][0]["timeline_events"][0]["start"] = 0.0
    result, _ = build(no_appearance, False)
    assert "First appearance mismatch" in result.stderr + result.stdout

    misplaced_appearance = draft()
    appearance = misplaced_appearance["segments"][0]["shot_prompts"][0]["first_appearance_events"][0]
    appearance["start"], appearance["end"] = 1.3, 1.5
    result, _ = build(misplaced_appearance, False)
    assert "does not overlap source fact" in result.stderr + result.stdout

    incomplete_interaction = draft()
    beat = incomplete_interaction["segments"][0]["shot_prompts"][0]["action_beats"][0]
    beat.update({
        "interaction_chain_id": "X001", "interaction_kind": "ownership_transfer",
        "interaction_object_ids": ["PROP001"], "interaction_phase": "launch",
        "state_in": "目标在地面", "state_out": "目标进入空中",
    })
    result, _ = build(incomplete_interaction, False)
    assert "at least two linked phases" in result.stderr + result.stdout

    linked_interaction = draft()
    first = linked_interaction["segments"][0]["shot_prompts"][0]["action_beats"][0]
    first.update({
        "interaction_chain_id": "X001", "interaction_kind": "ownership_transfer",
        "interaction_object_ids": ["PROP001"], "interaction_phase": "launch",
        "state_in": "目标在地面", "state_out": "目标进入空中",
    })
    phases = [
        ("B002", 2.30, 2.80, "capture", "目标进入空中", "目标被飞行动物脚爪抓住", "飞行动物用脚爪抓住空中目标", "飞行动物在空中用脚爪准确抓住目标。"),
        ("B003", 2.80, 3.50, "return", "目标被飞行动物脚爪抓住", "飞行动物携带目标返回", "飞行动物抓着目标飞回", "飞行动物用脚爪抓着目标沿原方向飞回。"),
        ("B004", 3.50, 4.67, "observer_response", "飞行动物携带目标返回", "观看者目光持续追踪", "抬头追踪携物飞行动物", "驾驶者抬头追踪携带目标飞回的飞行动物。"),
    ]
    for beat_id, start, end, phase, state_in, state_out, action, fact in phases:
        linked_beat = copy.deepcopy(first)
        linked_beat.update({
            "beat_id": beat_id, "start": start, "end": end, "action": action,
            "object_or_target": "被转移的目标", "interaction_phase": phase,
            "state_in": state_in, "state_out": state_out, "timeline_fact": fact,
        })
        linked_interaction["segments"][0]["shot_prompts"][0]["action_beats"].append(linked_beat)
        linked_interaction["segments"][0]["timeline_events"][-1]["source_refs"].append(beat_id)
    _, linked = build(linked_interaction, True)
    assert linked is not None and "用脚爪准确抓住目标" in linked["segments"][0]["full_prompt"]

    missing_capture = copy.deepcopy(linked_interaction)
    beats = missing_capture["segments"][0]["shot_prompts"][0]["action_beats"]
    beats[:] = [item for item in beats if item["beat_id"] != "B002"]
    refs = missing_capture["segments"][0]["timeline_events"][-1]["source_refs"]
    refs.remove("B002")
    result, _ = build(missing_capture, False)
    assert "state discontinuity" in result.stderr + result.stdout or "Ownership-transfer chain" in result.stderr + result.stdout

    wrong_order = copy.deepcopy(linked_interaction)
    wrong_order_beats = wrong_order["segments"][0]["shot_prompts"][0]["action_beats"]
    for beat, phase in zip(wrong_order_beats, ("observer_response", "capture", "return", "launch")):
        beat["interaction_phase"] = phase
    result, _ = build(wrong_order, False)
    assert "causal order" in result.stderr + result.stdout

    print("V3 evidence-lock regression passed")


if __name__ == "__main__":
    main()
