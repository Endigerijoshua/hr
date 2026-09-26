"""
Lip-sync consistency check.

Wraps the pretrained SyncNet model (Chung & Zisserman, joonson/syncnet_python)
via subprocess, using its own face-tracking + audio-visual sync pipeline
(demo_syncnet.py) rather than a hand-tuned heuristic. Confirmed working
locally via:

    python demo_syncnet.py --videofile data/example.avi --tmp_dir tmp

which printed (among other things):

    AV offset:        3
    Min dist:         5.358
    Confidence:       10.081

This module shells out to that same script for each candidate's submission
video and parses "Confidence:" from its combined stdout/stderr (SyncNet logs
via Python's `logging` module, which defaults to stderr).

Same convention as gaze.py / audio.py: score in [0, 1], 1.0 = consistent/honest.

Requires the SYNCNET_REPO_DIR environment variable to point at a local
checkout of joonson/syncnet_python (the one this was tested against; other
forks may log in a different format and could break the regex below).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import logging

logger = logging.getLogger(__name__)

# --- NOT empirically validated. ---
# These are placeholder thresholds based on eyeballing the single test clip
# (example.avi -> confidence 10.081, presumed in-sync). SyncNet's own paper
# and repo don't publish a single universal pass/fail confidence cutoff --
# it depends on clip length, face size, video quality, etc. Before trusting
# these in the paper or in production scoring, run demo_syncnet.py against
# a handful of known-honest and known-gamed clips and tune against real
# numbers. Do not present these as validated.
MIN_CONFIDENCE_FOR_ZERO_SCORE = 2.0   # commonly cited rough floor for "out of sync" in SyncNet literature/discussions
MAX_CONFIDENCE_FOR_FULL_SCORE = 9.0   # below the 10.081 we observed on a clean known-good clip; leaves headroom

# Matches "Confidence:       10.081" (SyncNet's own logging format, one or
# more spaces, float). Confirmed against real output above.
_CONFIDENCE_RE = re.compile(r"Confidence:\s+([\d.]+)")

_DEMO_SCRIPT = "demo_syncnet.py"
_DEFAULT_TIMEOUT_SECONDS = 300


class LipSyncError(RuntimeError):
    """Raised when the SyncNet subprocess fails or its output can't be parsed."""


def _repo_dir() -> str:
    repo_dir = os.environ.get("SYNCNET_REPO_DIR")
    if not repo_dir:
        raise LipSyncError(
            "SYNCNET_REPO_DIR is not set. Point it at your local "
            "joonson/syncnet_python checkout, e.g. "
            r'$env:SYNCNET_REPO_DIR = "C:\Users\localadmin\hr\syncnet_python"'
        )
    if not os.path.isdir(repo_dir):
        raise LipSyncError(f"SYNCNET_REPO_DIR does not exist: {repo_dir}")
    return repo_dir


def _run_demo_syncnet(video_path: str, tmp_dir: str, repo_dir: str) -> str:
    """Runs demo_syncnet.py and returns combined stdout+stderr as text."""
    cmd = [
        "python",
        _DEMO_SCRIPT,
        "--videofile", os.path.abspath(video_path),
        "--tmp_dir", os.path.abspath(tmp_dir),
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise LipSyncError(
            f"demo_syncnet.py timed out after {_DEFAULT_TIMEOUT_SECONDS}s on {video_path}"
        ) from exc
    except FileNotFoundError as exc:
        raise LipSyncError(
            f"Could not find/run {_DEMO_SCRIPT} in {repo_dir} -- check SYNCNET_REPO_DIR"
        ) from exc

    combined = (result.stdout or "") + "\n" + (result.stderr or "")

    if result.returncode != 0:
        raise LipSyncError(
            f"demo_syncnet.py exited with code {result.returncode} on {video_path}.\n"
            f"--- output ---\n{combined}"
        )

    return combined


def _parse_confidence(output: str) -> float:
    matches = _CONFIDENCE_RE.findall(output)
    if not matches:
        raise LipSyncError(
            "Could not find 'Confidence:' in demo_syncnet.py output -- "
            "output format may not match this repo/fork.\n"
            f"--- output ---\n{output}"
        )
    # If multiple faces/tracks were detected, demo_syncnet.py can print more
    # than one confidence line. Take the last one (final/summary track) --
    # revisit this if candidate videos ever have multiple people in frame.
    return float(matches[-1])


def _confidence_to_score(confidence: float) -> float:
    if confidence <= MIN_CONFIDENCE_FOR_ZERO_SCORE:
        return 0.0
    if confidence >= MAX_CONFIDENCE_FOR_FULL_SCORE:
        return 1.0
    span = MAX_CONFIDENCE_FOR_FULL_SCORE - MIN_CONFIDENCE_FOR_ZERO_SCORE
    return (confidence - MIN_CONFIDENCE_FOR_ZERO_SCORE) / span


def score_lipsync(video_path: str) -> dict:
    """
    video_path: submission video with an embedded audio track. demo_syncnet.py
        extracts both video frames and audio from this one file internally --
        no separate audio_path needed (unlike the old MAR-heuristic version).

    Returns dict with:
        score: float in [0, 1], 1.0 = consistent/honest
        confidence: raw SyncNet confidence value, or None if scoring failed
        note: present only on a non-fatal fallback (e.g. couldn't parse output)
    """
    repo_dir = _repo_dir()
    tmp_dir = tempfile.mkdtemp(prefix="syncnet_")

    try:
        output = _run_demo_syncnet(video_path, tmp_dir, repo_dir)
        confidence = _parse_confidence(output)
    except LipSyncError as exc:
        logger.warning("lipsync scoring failed for %s: %s", video_path, exc)
        # Fail toward "flagged for human review", not toward "pass" or
        # "auto-fail" -- consistent with the architecture contract's
        # nothing-auto-rejects rule. 0.5 keeps this signal neutral so
        # fusion.py doesn't let a scoring bug alone sink the candidate.
        return {"score": 0.5, "confidence": None, "note": f"scoring failed: {exc}"}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    score = _confidence_to_score(confidence)
    return {"score": round(score, 3), "confidence": round(confidence, 3)}
