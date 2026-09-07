#!/usr/bin/env python3
"""Probe a video, detect shot candidates, and flag short audio impacts."""

from __future__ import annotations

import argparse
from array import array
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
from fractions import Fraction
from pathlib import Path


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)


def require(binary: str) -> None:
    if shutil.which(binary) is None:
        raise SystemExit(f"Required executable not found: {binary}")


def rate(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None


def probe(video: Path) -> dict:
    result = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)])
    if result.returncode:
        raise SystemExit(result.stderr.strip() or "ffprobe failed")
    raw = json.loads(result.stdout)
    vstream = next((s for s in raw.get("streams", []) if s.get("codec_type") == "video"), None)
    if not vstream:
        raise SystemExit("No video stream found")
    duration = float(vstream.get("duration") or raw.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise SystemExit("Could not determine video duration")
    return {
        "path": str(video.resolve()),
        "duration": round(duration, 6),
        "width": int(vstream.get("width") or 0),
        "height": int(vstream.get("height") or 0),
        "fps": rate(vstream.get("avg_frame_rate") or vstream.get("r_frame_rate")),
        "codec": vstream.get("codec_name"),
        "pixel_format": vstream.get("pix_fmt"),
        "has_audio": any(s.get("codec_type") == "audio" for s in raw.get("streams", [])),
    }


def scene_cuts(video: Path, threshold: float) -> list[float]:
    filt = f"select=gt(scene\\,{threshold}),showinfo"
    result = run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", filt, "-an", "-f", "null", "-"])
    return sorted(set(float(v) for v in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", result.stderr)))


def merge_short_shots(boundaries: list[float], duration: float, minimum: float) -> list[tuple[float, float]]:
    clean = [0.0] + [x for x in boundaries if 0 < x < duration] + [duration]
    shots: list[tuple[float, float]] = []
    start = clean[0]
    for end in clean[1:]:
        if end - start < minimum and end < duration:
            continue
        shots.append((start, end))
        start = end
    if start < duration:
        if shots and duration - start < minimum:
            shots[-1] = (shots[-1][0], duration)
        else:
            shots.append((start, duration))
    return shots


def candidate_times(start: float, end: float) -> list[float]:
    length = end - start
    pad = min(0.12, max(0.02, length * 0.04))
    if length < 2.0:
        return [round((start + end) / 2, 6)]
    return [round(start + pad, 6), round((start + end) / 2, 6), round(end - pad, 6)]


def pcm_mono(video: Path, sample_rate: int) -> array:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
            "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return array("h")
    samples = array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def dense_times(center: float, duration: float, radius: float) -> list[float]:
    offsets = (-radius, -radius / 2, 0.0, radius / 2, radius)
    return sorted({round(min(duration, max(0.0, center + offset)), 6) for offset in offsets})


def audio_transients(
    video: Path,
    duration: float,
    *,
    radius: float,
    minimum_gap: float,
    z_threshold: float,
    rise_db_threshold: float,
    max_events: int,
) -> list[dict]:
    """Return conservative audio-impact candidates for human causal review.

    The detector intentionally reports candidates rather than claiming a gunshot,
    collision, or other semantic event. It uses 20 ms mono PCM energy windows,
    robust median/MAD scoring, and a positive-energy-rise test.
    """
    sample_rate = 16000
    samples = pcm_mono(video, sample_rate)
    window_samples = max(1, round(sample_rate * 0.02))
    if len(samples) < window_samples * 3:
        return []
    energies: list[float] = []
    for offset in range(0, len(samples) - window_samples + 1, window_samples):
        chunk = samples[offset : offset + window_samples]
        energies.append(sum(abs(value) for value in chunk) / len(chunk))
    baseline = statistics.median(energies)
    mad = statistics.median(abs(value - baseline) for value in energies)
    robust_scale = max(1.0, mad * 1.4826)
    raw_candidates: list[tuple[int, float, float, float]] = []
    for index in range(2, len(energies) - 1):
        value = energies[index]
        prior = statistics.mean(energies[max(0, index - 3) : index])
        robust_z = (value - baseline) / robust_scale
        rise_db = 20.0 * math.log10((value + 1.0) / (prior + 1.0))
        is_local_peak = value >= energies[index - 1] and value >= energies[index + 1]
        strong_level = robust_z >= z_threshold
        sharp_rise = rise_db >= rise_db_threshold and value >= max(200.0, baseline * 2.0)
        if is_local_peak and (strong_level or sharp_rise):
            raw_candidates.append((index, value, robust_z, rise_db))

    ranked = sorted(raw_candidates, key=lambda item: (item[1], item[2], item[3]), reverse=True)
    selected: list[tuple[int, float, float, float]] = []
    for item in ranked:
        event_time = (item[0] + 0.5) * 0.02
        if all(abs(event_time - (other[0] + 0.5) * 0.02) >= minimum_gap for other in selected):
            selected.append(item)
        if len(selected) >= max_events:
            break
    selected.sort(key=lambda item: item[0])
    events = []
    for event_index, (index, value, robust_z, rise_db) in enumerate(selected, 1):
        event_time = min(duration, (index + 0.5) * 0.02)
        events.append(
            {
                "candidate_id": f"AT{event_index:03d}",
                "time": round(event_time, 6),
                "analysis_window": [round(max(0.0, event_time - radius), 6), round(min(duration, event_time + radius), 6)],
                "dense_keyframe_times": dense_times(event_time, duration, radius),
                "energy": round(value, 3),
                "robust_z": round(robust_z, 3),
                "rise_db": round(rise_db, 3),
                "status": "CANDIDATE_REQUIRES_CAUSAL_REVIEW",
            }
        )
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path, help="Output manifest JSON")
    parser.add_argument("--scene-threshold", type=float, default=0.32)
    parser.add_argument("--minimum-shot", type=float, default=0.35)
    parser.add_argument("--impact-window", type=float, default=0.20, help="Dense-frame radius around audio transients")
    parser.add_argument("--impact-min-gap", type=float, default=0.25)
    parser.add_argument("--impact-z", type=float, default=12.0)
    parser.add_argument("--impact-rise-db", type=float, default=7.5)
    parser.add_argument("--max-impact-candidates", type=int, default=120)
    args = parser.parse_args()
    require("ffprobe")
    require("ffmpeg")
    if not args.video.is_file():
        raise SystemExit(f"Video not found: {args.video}")
    media = probe(args.video)
    cuts = scene_cuts(args.video, args.scene_threshold)
    segments = merge_short_shots(cuts, media["duration"], args.minimum_shot)
    transients = []
    if media["has_audio"]:
        transients = audio_transients(
            args.video,
            media["duration"],
            radius=max(0.05, args.impact_window),
            minimum_gap=max(0.05, args.impact_min_gap),
            z_threshold=max(1.0, args.impact_z),
            rise_db_threshold=max(1.0, args.impact_rise_db),
            max_events=max(1, args.max_impact_candidates),
        )
    shots = []
    for index, (start, end) in enumerate(segments, 1):
        shot_transients = [
            event
            for event in transients
            if start <= float(event["time"]) < end
            or (end == media["duration"] and start <= float(event["time"]) <= end)
        ]
        times = candidate_times(start, end)
        for event in shot_transients:
            times.extend(value for value in event["dense_keyframe_times"] if start <= value <= end)
        shots.append({
            "shot_id": f"D{index:03d}",
            "start": round(start, 6),
            "end": round(end, 6),
            "duration": round(end - start, 6),
            "keyframe_times": sorted(set(times)),
            "audio_transient_candidates": [event["candidate_id"] for event in shot_transients],
        })
    payload = {
        "schema_version": "3.0",
        "media": media,
        "detected_shots": shots,
        "audio_transients": transients,
        "impact_review_rule": "Inspect dense frames within approximately ±0.20 s; confirm visible cause, target, reaction, physical result, and audio timing before assigning semantics.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(shots)} shot candidates and {len(transients)} audio-impact candidates to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
