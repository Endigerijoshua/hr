"""
Turn the Kaggle "OEP" (Online Exam Proctoring) dataset into the
labeled-clip set that ml/verification/evaluate.py expects.

Expected input layout (as documented for the Kaggle dataset):
    data/oep/subject1/subject1_1.avi
    data/oep/subject1/gt.txt
    data/oep/subject2/subject2_1.avi
    data/oep/subject2/gt.txt
    ...

IMPORTANT: the dataset's gt.txt format isn't fully documented anywhere I
could verify. Before running this for real:
    1. Open one gt.txt and look at it.
    2. Compare it to the two formats _parse_gt() below already handles.
    3. If it doesn't match either, add a third branch — the parser is
       intentionally isolated in one small function so that's a five-line
       fix, not a rewrite.

What this script does per subject:
    1. Parses gt.txt into a list of (start_sec, end_sec) "cheating" intervals.
    2. Gets the video's total duration via ffprobe.
    3. Builds the complement: everything NOT in a cheating interval is an
       "honest" interval.
    4. Cuts each interval (skipping ones shorter than MIN_CLIP_SECONDS —
       too short to score meaningfully) into its own .mp4 clip + a matching
       .wav audio file.
    5. Writes labels.json with {"video", "audio", "label"} entries, ready
       to hand to `python -m ml.verification.evaluate labels.json`.

Run:
    python -m ml.verification.oep_adapter --input data/oep --output data/oep_clips
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

MIN_CLIP_SECONDS = 3.0


def _ffprobe_duration(video_path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def _parse_gt(gt_path: Path) -> list[tuple[float, float]]:
    """
    Returns cheating intervals as (start_seconds, end_seconds).
    Handles two likely formats; add a branch if neither matches your file:
      Format A: "start_sec end_sec" per line, e.g. "12.5 18.0"
      Format B: "start_sec,end_sec,label" per line, label==1 means cheating
    """
    intervals = []
    text = gt_path.read_text().strip()
    if not text:
        return intervals

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) == 2:
            start, end = float(parts[0]), float(parts[1])
            intervals.append((start, end))
        elif len(parts) == 3:
            start, end, label = float(parts[0]), float(parts[1]), parts[2]
            if label in ("1", "cheating", "True", "true"):
                intervals.append((start, end))
        else:
            raise ValueError(
                f"Unrecognized gt.txt line format in {gt_path}: {line!r} — "
                f"inspect the file and add a parsing branch to _parse_gt()."
            )
    return sorted(intervals)


def _complement(intervals: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    honest = []
    cursor = 0.0
    for start, end in intervals:
        if start > cursor:
            honest.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        honest.append((cursor, duration))
    return honest


def _cut_clip(video_path: Path, start: float, end: float, out_dir: Path, tag: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_path = out_dir / f"{tag}.mp4"
    audio_path = out_dir / f"{tag}.wav"

    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", str(video_path),
         "-c:v", "libx264", "-c:a", "aac", str(clip_path)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(clip_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", str(audio_path)],
        check=True, capture_output=True,
    )
    return clip_path, audio_path


def build_labels(input_dir: Path, output_dir: Path) -> list[dict]:
    entries = []
    subject_dirs = sorted(p for p in input_dir.iterdir() if p.is_dir())

    for subject_dir in subject_dirs:
        gt_path = subject_dir / "gt.txt"
        videos = sorted(subject_dir.glob("*.avi")) + sorted(subject_dir.glob("*.mp4"))
        if not gt_path.exists() or not videos:
            print(f"skipping {subject_dir} (missing gt.txt or video)")
            continue

        video_path = videos[0]
        duration = _ffprobe_duration(video_path)
        cheating_intervals = _parse_gt(gt_path)
        honest_intervals = _complement(cheating_intervals, duration)

        subject_out = output_dir / subject_dir.name

        for i, (start, end) in enumerate(cheating_intervals):
            if end - start < MIN_CLIP_SECONDS:
                continue
            clip, audio = _cut_clip(video_path, start, end, subject_out, f"gamed_{i}")
            entries.append({"video": str(clip), "audio": str(audio), "label": "gamed"})

        for i, (start, end) in enumerate(honest_intervals):
            if end - start < MIN_CLIP_SECONDS:
                continue
            clip, audio = _cut_clip(video_path, start, end, subject_out, f"honest_{i}")
            entries.append({"video": str(clip), "audio": str(audio), "label": "honest"})

        print(f"{subject_dir.name}: {len(cheating_intervals)} gamed / {len(honest_intervals)} honest intervals")

    return entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="path to extracted OEP dataset root")
    parser.add_argument("--output", required=True, help="where to write cut clips + labels.json")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    labels = build_labels(input_dir, output_dir)
    labels_path = output_dir / "labels.json"
    labels_path.write_text(json.dumps(labels, indent=2))
    print(f"\nwrote {len(labels)} labeled clips to {labels_path}")
    print(f"next: python -m ml.verification.evaluate {labels_path}")
