#!/usr/bin/env python3
"""Render an asset-first, shot-linked HTML storyboard from prompt data 4.0."""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def relative_uri(path: Path, html_path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), html_path.parent.resolve())).as_posix()


def resolve_frame(root: Path, frame_ref: str, prefer_clean: bool = False) -> Path:
    folders = ("clean", "annotated") if prefer_clean else ("annotated", "clean")
    for folder in folders:
        path = root / folder / f"{frame_ref}.png"
        if path.is_file():
            return path
    raise FileNotFoundError(f"Missing storyboard frame: {frame_ref}")


def find_frames(root: Path, segment_id: str) -> list[Path]:
    base = root / "annotated" if (root / "annotated").is_dir() else root / "clean"
    return sorted(base.glob(f"{segment_id}-*.png"))


def figures(refs: list[str], frame_root: Path, output_html: Path, prefer_clean: bool = False) -> str:
    result = []
    for ref in refs:
        frame = resolve_frame(frame_root, ref, prefer_clean=prefer_clean)
        result.append(
            f'<figure><img src="{esc(relative_uri(frame, output_html))}" alt="{esc(ref)}">'
            f'<figcaption>{esc(ref)}</figcaption></figure>'
        )
    return "".join(result)


def field(label: str, value: object) -> str:
    return f'<div class="field"><strong>{esc(label)}</strong>{esc(value) or "—"}</div>'


def action_text(beats: list[dict]) -> str:
    lines = []
    for index, beat in enumerate(beats, 1):
        performance = beat.get("performance_chain")
        performance_text = ""
        if performance:
            performance_text = (
                f"；表演链：情绪意图{performance['emotion_intent']}，表情{performance['visible_expression']}，"
                f"视线{performance['gaze_target']}，预备{performance['preparation']}，执行{performance['execution']}，"
                f"延续{performance['follow_through']}，收势{performance['settle']}"
            )
        interaction_text = ""
        if beat.get("interaction_chain_id"):
            interaction_text = (
                f"；微事件链：{beat['interaction_chain_id']} / {beat['interaction_kind']} / "
                f"对象{', '.join(beat['interaction_object_ids'])} / {beat['interaction_phase']}，"
                f"进入状态{beat['state_in']}，离开状态{beat['state_out']}"
            )
        lines.append(
            f"{index}. {beat['subject']}（{beat['subject_asset_id']}）在{beat['spatial_relation']}，"
            f"以{beat['motion_rhythm']}的节奏{beat['action']}，作用于{beat['object_or_target']}"
            f"{performance_text}{interaction_text}；物理反馈：{beat['physical_feedback']}"
        )
    return "\n".join(lines)


def event_lines(events: list[dict], event_type: str) -> str:
    if not events:
        return "本镜未识别到此类事件。"
    if event_type == "layer":
        labels = {"diegetic_display": "画内面屏", "editorial_title": "后期标题", "environment_vfx": "环境VFX", "ui_overlay": "UI叠层", "transition_vfx": "转场VFX"}
        return "\n".join(
            f"{labels[event['layer_type']]}｜{event['start']:.2f}–{event['end']:.2f}s｜{event['content']}；{event['appearance']}；{event['placement_depth']}"
            for event in events
        )
    if event_type == "appearance":
        return "\n".join(
            f"{event['asset_id']}｜{event['appearance_type']}｜{event['start']:.2f}–{event['end']:.2f}s｜此前{event['prior_visibility']}；"
            f"来源空间{event['source_space']}；由{event['reveal_trigger']}触发，从{event['entry_direction']}进入{event['frame_region']}；"
            f"最先露出{event['first_visible_part']}，初态{event['initial_pose_state']}；揭示动作{event['emergence_motion']}；"
            f"首个动作{event['first_visible_action']}；完整建立{event['completion_state']}；观察者反应{event['observer_reaction']}；"
            f"证据帧{'、'.join(event['evidence_frame_refs'])}"
            for event in events
        )
    return "\n".join(
        f"{event['event_type']}｜源时码{event['source_time']:.2f}s｜声音{event['audio_cue']}｜原因{event['visible_cause']}｜"
        f"结果{event['visible_effect']}｜因果{event['causal_verdict']}"
        for event in events
    )


def camera_text(camera: dict) -> str:
    return (
        f"RECREATION_SPEC｜设备：{camera['equipment_name']}；镜头：{camera['lens_name']}；"
        f"焦段：{camera['focal_length']}；光圈：{camera['aperture']}；机位：{camera['camera_height_angle']}；"
        f"构图：{camera['composition']}；运镜：{camera['movement']}；对焦与景深：{camera['focus_depth']}"
    )


def render_asset_library(data: dict, frame_root: Path, output_html: Path) -> str:
    labels = (("characters", "人物资产表"), ("props", "主要道具资产表"), ("locations", "主要场景资产表"))
    sections = ['<h2 class="section-title">视频资产表</h2>']
    for key, label in labels:
        sections.append(f'<h2 class="section-title">{esc(label)}</h2><div class="asset-grid">')
        items = data["asset_library"].get(key, [])
        if not items:
            sections.append('<article class="asset"><div class="asset-head"><h3>未识别到可确认资产</h3></div></article>')
        for asset in items:
            detail = "".join([
                field("叙事功能", asset["narrative_function"]),
                field("连续性锁定", asset["continuity_lock"]),
                field("证据等级", asset["evidence_status"]),
            ])
            sections.append(
                '<article class="asset">'
                f'<div class="asset-head"><h3>{esc(asset["asset_id"])}｜{esc(asset["name"])}</h3></div>'
                f'<div class="asset-frames">{figures(asset["frame_refs"], frame_root, output_html, prefer_clean=True)}</div>'
                f'<div class="details">{detail}</div>'
                f'<div class="prompt"><strong>资产详细生成提示词</strong><pre>{esc(asset["description_prompt"])}</pre></div>'
                '</article>'
            )
        sections.append('</div>')
    return "".join(sections)


def render_shot(shot: dict, frame_root: Path, output_html: Path) -> str:
    details = "".join([
        field("场景与画面", shot["scene"]),
        field("本镜可见实体", "、".join(shot["present_entities"])),
        field("完整动作关系", action_text(shot["action_beats"])),
        field("人物首次登场事件", event_lines(shot["first_appearance_events"], "appearance")),
        field("摄影实现方案", camera_text(shot["camera"])),
        field("光影与色彩", shot["lighting_color"]),
        field("分层文字与 VFX", event_lines(shot["layer_events"], "layer")),
        field("短促冲击与因果链", event_lines(shot["impact_events"], "impact")),
        field("声音", shot["sound"]),
        field("片段内部剪辑", shot["edit_instruction"]),
    ])
    return (
        '<article class="shot-block">'
        f'<div class="shot-head"><h3>{esc(shot["shot_id"])}｜源时间码 {float(shot["start"]):.2f}s–{float(shot["end"]):.2f}s｜{float(shot["duration"]):.2f}s</h3></div>'
        f'<div class="shot-frames">{figures(shot["frame_refs"], frame_root, output_html)}</div>'
        f'<div class="details">{details}</div>'
        '</article>'
    )


def render_segment(segment: dict, frame_root: Path, output_html: Path) -> str:
    shots = "".join(render_shot(shot, frame_root, output_html) for shot in segment["shot_prompts"])
    asset_pills = "".join(f'<span class="pill">{esc(value)}</span>' for value in segment["assets_used"])
    return (
        '<section class="segment">'
        f'<div class="segment-head"><h2>{esc(segment["segment_id"])}｜{esc(segment["title"])}</h2></div>'
        f'<div class="segment-meta"><span class="pill">分析时间码 {float(segment["start"]):.2f}s–{float(segment["end"]):.2f}s</span>'
        f'<span class="pill">生成时长 {float(segment["duration"]):.2f}s</span>{asset_pills}'
        f'<p>{esc(segment["summary"])}</p><p><strong>全段具体一致性：</strong>{esc(segment["segment_consistency"])}</p></div>'
        f'{shots}'
        f'<div class="prompt"><strong>Seedance 2.5 整段完整提示词（可直接复制）</strong><pre>{esc(segment["full_prompt"])}</pre></div>'
        '</section>'
    )


def render_repairs(data: dict) -> str:
    repairs = data.get("repair_prompts", {})
    sections = ['<h2 class="section-title">常见失败修复提示词</h2>']
    if not repairs:
        sections.append(
            '<section class="segment"><div class="segment-meta">本片无需额外专项修复提示词。</div></section>'
        )
        return "".join(sections)
    sections.append('<div class="asset-grid">')
    for name, prompt in repairs.items():
        sections.append(
            '<article class="asset">'
            f'<div class="asset-head"><h3>{esc(name)}</h3></div>'
            f'<div class="prompt"><strong>可直接复制的自包含修复提示词</strong><pre>{esc(prompt)}</pre></div>'
            '</article>'
        )
    sections.append('</div>')
    return "".join(sections)


def overview(segments: list[dict], frame_root: Path, destination: Path) -> None:
    items = []
    thumb_w, thumb_h = 420, 260
    font = ImageFont.load_default(size=18)
    for segment in segments:
        frames = find_frames(frame_root, segment["segment_id"])
        if not frames:
            continue
        image = Image.open(frames[(len(frames) - 1) // 2]).convert("RGB")
        fitted = ImageOps.contain(image, (thumb_w, thumb_h))
        tile = Image.new("RGB", (thumb_w, thumb_h + 42), "white")
        tile.paste(fitted, ((thumb_w - fitted.width) // 2, (thumb_h - fitted.height) // 2))
        draw = ImageDraw.Draw(tile)
        draw.text((10, thumb_h + 9), f"{segment['segment_id']}  {float(segment['start']):.2f}-{float(segment['end']):.2f}s", fill="#172033", font=font)
        items.append(tile)
    if not items:
        raise RuntimeError("No storyboard frames found")
    columns = 3
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + 42)), "#dfe5ec")
    for index, tile in enumerate(items):
        sheet.paste(tile, ((index % columns) * thumb_w, (index // columns) * (thumb_h + 42)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG")


def print_pdf(html_path: Path, pdf_path: Path) -> bool:
    candidates = [
        shutil.which("msedge"), shutil.which("chrome"), shutil.which("chromium"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    browser = next((Path(value) for value in candidates if value and Path(value).is_file()), None)
    if not browser:
        return False
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="recreate-video-edge-", ignore_cleanup_errors=True) as profile:
        command = [
            str(browser), "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
            f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode == 0 and pdf_path.is_file()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt_data", type=Path)
    parser.add_argument("frame_root", type=Path)
    parser.add_argument("output_html", type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--overview", type=Path)
    parser.add_argument("--pdf", type=Path)
    args = parser.parse_args()
    data = json.loads(args.prompt_data.read_text(encoding="utf-8"))
    if data.get("schema_version") != "4.0":
        raise SystemExit("Storyboard renderer requires prompt-data schema 4.0")
    template = args.template or Path(__file__).resolve().parents[1] / "assets" / "storyboard-template.html"
    raw = template.read_text(encoding="utf-8")
    assets_html = render_asset_library(data, args.frame_root, args.output_html)
    story_html = '<h2 class="section-title">逐镜分镜故事板</h2>' + "".join(
        render_segment(segment, args.frame_root, args.output_html) for segment in data["segments"]
    ) + render_repairs(data)
    title = data.get("project_title") or "视频复刻分镜故事板"
    rendered = raw.replace("{{TITLE}}", esc(title)).replace("{{ASSET_LIBRARY}}", assets_html).replace("{{STORY_CARDS}}", story_html)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.write_text(rendered, encoding="utf-8")
    if args.overview:
        overview(data["segments"], args.frame_root, args.overview)
    if args.pdf and not print_pdf(args.output_html, args.pdf):
        print("Warning: PDF browser unavailable or print failed", file=sys.stderr)
    print(f"Rendered storyboard to {args.output_html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
